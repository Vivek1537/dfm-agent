"""
core/parting/loops.py — Edge graph and loop tracing (specification section 9).

A parting line is not a set of edges, it is ordered connected geometry. This
module builds a real graph over the candidate boundary edges — vertices keyed
by tolerance-matched endpoints, edges carrying their own orientation — and
traverses it into ordered chains.

WHAT THE PREVIOUS IMPLEMENTATION GOT WRONG
------------------------------------------
It grouped edges into connected COMPONENTS and then walked each component
greedily, declaring the result closed only if the walk happened to consume
every edge and return to its start. Three failures follow from that:

  * A component containing a branch point (a vertex where three or more
    candidate edges meet, which any part with a side feature produces) can
    never consume all its edges in one walk, so a perfectly good rim with one
    spur attached was reported as a single OPEN chain.
  * A component that is genuinely two disjoint closed loops sharing no vertex
    -- an outer rim and a concentric inner rim, say -- was likewise reported
    as one open chain.
  * Branching was never counted, so nothing downstream could tell a clean
    loop from a tangle.

Here, components are decomposed properly: the traversal walks vertex to
vertex, and at a branch point it prefers the continuation that keeps the
chain smooth (smallest turn), which is what follows a rim past an incidental
spur instead of turning up it. Every closed loop found is emitted separately,
leftover edges become open chains, and branch points are counted and reported.

ORIENTATION
-----------
Edge direction in a B-rep is a property of the edge's use in a face, not of
the curve, so an edge's stored parametrisation may run either way relative to
the loop. Every edge is tessellated into an ordered polyline and reversed on
use when needed; nothing relies on edge index order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from core.parting.models import (
    EDGE_SHUTOFF,
    BoundaryEdge,
    PartingLoop,
    dot,
    norm,
)
from core.tolerances import COORD_KEY_DECIMALS, AnalysisConfig, resolve

Vector3 = Tuple[float, float, float]
VertexKey = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Tessellation
# ---------------------------------------------------------------------------

def edge_polyline(edge: Any, n: int = 8) -> List[Vector3]:
    """Sample an edge into n+1 ordered points along its curve.

    Curved edges carry the loop's real shape between their endpoints.
    Endpoint-only sampling collapses a circular rim made of two semicircular
    edges into a two-point "polygon" of zero area, which is what made the old
    area metric useless on round parts.
    """
    try:
        curve = BRepAdaptor_Curve(edge)
        t0, t1 = curve.FirstParameter(), curve.LastParameter()
        pts: List[Vector3] = []
        for i in range(n + 1):
            t = t0 + (t1 - t0) * i / n
            p = curve.Value(t)
            pts.append((p.X(), p.Y(), p.Z()))
        return pts
    except Exception:
        return edge_endpoints(edge)


def edge_endpoints(edge: Any) -> List[Vector3]:
    """Both endpoint coordinates of an edge, in topological order."""
    coords: List[Vector3] = []
    exp = TopExp_Explorer(edge, TopAbs_VERTEX)
    while exp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current()))
        coords.append((p.X(), p.Y(), p.Z()))
        exp.Next()
    return coords


def vertex_key(p: Vector3, decimals: int = COORD_KEY_DECIMALS) -> VertexKey:
    """Quantised coordinate key. Two endpoints within tolerance share one."""
    return (round(p[0], decimals), round(p[1], decimals), round(p[2], decimals))


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@dataclass
class GraphEdge:
    """A candidate edge with its tessellation and its two graph vertices."""

    index: int
    boundary: BoundaryEdge
    points: List[Vector3]
    start: VertexKey
    end: VertexKey

    @property
    def is_loop_edge(self) -> bool:
        """True when the edge closes on itself (a full circle, say)."""
        return self.start == self.end

    def oriented(self, from_key: VertexKey) -> List[Vector3]:
        """Points ordered so the polyline leaves `from_key`."""
        if from_key == self.start:
            return self.points
        return self.points[::-1]

    def other(self, key: VertexKey) -> VertexKey:
        return self.end if key == self.start else self.start


@dataclass
class EdgeGraph:
    """Undirected graph over candidate boundary edges."""

    edges: List[GraphEdge] = field(default_factory=list)
    incident: Dict[VertexKey, List[int]] = field(default_factory=dict)

    def degree(self, key: VertexKey) -> int:
        return len(self.incident.get(key, ()))

    @property
    def branch_vertices(self) -> List[VertexKey]:
        """Vertices where three or more candidate edges meet."""
        return [k for k, refs in self.incident.items() if len(refs) > 2]

    @property
    def endpoint_vertices(self) -> List[VertexKey]:
        """Vertices with a single edge — the loose ends of an open chain."""
        return [k for k, refs in self.incident.items() if len(refs) == 1]


def build_edge_graph(
    boundary_edges: Sequence[BoundaryEdge],
    config: Optional[AnalysisConfig] = None,
) -> EdgeGraph:
    """Build the connectivity graph for a set of candidate edges."""
    cfg = resolve(config)
    graph = EdgeGraph()

    for edge in boundary_edges:
        # Density scales with how few edges the loop has: one full-circle rim
        # needs many points to describe its shape, forty short segments do not.
        density = max(8, 64 // max(len(boundary_edges), 1))
        pts = edge_polyline(edge.edge, density)
        if len(pts) < 2:
            continue
        ge = GraphEdge(
            index=len(graph.edges),
            boundary=edge,
            points=pts,
            start=vertex_key(pts[0]),
            end=vertex_key(pts[-1]),
        )
        graph.edges.append(ge)
        graph.incident.setdefault(ge.start, []).append(ge.index)
        if not ge.is_loop_edge:
            graph.incident.setdefault(ge.end, []).append(ge.index)

    return graph


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------

@dataclass
class Chain:
    """One traced path: the edges used, the ordered points, and closure."""

    edge_indices: List[int] = field(default_factory=list)
    points: List[Vector3] = field(default_factory=list)
    is_closed: bool = False
    branch_points: int = 0


def _incoming_tangent(points: List[Vector3]) -> Vector3:
    """Unit direction the chain is travelling as it arrives at its last point."""
    if len(points) < 2:
        return (0.0, 0.0, 1.0)
    a, b = points[-2], points[-1]
    return norm((b[0] - a[0], b[1] - a[1], b[2] - a[2]))


def _outgoing_tangent(points: List[Vector3]) -> Vector3:
    """Unit direction a candidate continuation leaves its first point."""
    if len(points) < 2:
        return (0.0, 0.0, 1.0)
    a, b = points[0], points[1]
    return norm((b[0] - a[0], b[1] - a[1], b[2] - a[2]))


def _trace_from(
    graph: EdgeGraph,
    start_key: VertexKey,
    start_edge: int,
    used: Set[int],
) -> Chain:
    """Walk from one vertex along one edge until the path closes or ends.

    At a vertex with more than one unused continuation the walk takes the
    SMOOTHEST one — the continuation whose direction best matches the way the
    chain is already travelling. On a rim with an incidental spur that keeps
    the trace on the rim, which is the curve a mold designer means, instead of
    turning up the spur and stranding the rest of the rim as a separate chain.
    """
    chain = Chain()
    ge = graph.edges[start_edge]
    chain.points = list(ge.oriented(start_key))
    chain.edge_indices.append(start_edge)
    used.add(start_edge)

    current = ge.other(start_key) if not ge.is_loop_edge else ge.start

    while True:
        if current == start_key and len(chain.edge_indices) >= 1:
            chain.is_closed = True
            break

        options = [i for i in graph.incident.get(current, ()) if i not in used]
        if not options:
            break

        if len(graph.incident.get(current, ())) > 2:
            chain.branch_points += 1

        if len(options) == 1:
            nxt = options[0]
        else:
            incoming = _incoming_tangent(chain.points)
            nxt = max(
                options,
                key=lambda i: (
                    round(dot(incoming, _outgoing_tangent(
                        graph.edges[i].oriented(current))), 9),
                    # Deterministic tie-break: never let dict order decide.
                    -i,
                ),
            )

        nge = graph.edges[nxt]
        chain.points.extend(nge.oriented(current)[1:])
        chain.edge_indices.append(nxt)
        used.add(nxt)
        current = nge.other(current) if not nge.is_loop_edge else current

    return chain


def trace_chains(
    graph: EdgeGraph,
    config: Optional[AnalysisConfig] = None,
) -> List[Chain]:
    """Decompose the graph into closed loops and leftover open chains.

    Closed loops are extracted first, starting from vertices of degree 2 so a
    clean rim is never entered through a junction. Whatever edges remain are
    then traced from their loose ends into open chains. Seeds are visited in
    sorted key order so the decomposition is reproducible.
    """
    resolve(config)
    used: Set[int] = set()
    chains: List[Chain] = []

    # Self-closing single edges (full circles) are loops on their own.
    for ge in graph.edges:
        if ge.index in used or not ge.is_loop_edge:
            continue
        used.add(ge.index)
        chains.append(
            Chain(
                edge_indices=[ge.index],
                points=list(ge.points),
                is_closed=True,
            )
        )

    # Pass 1: closed loops, seeded from ordinary degree-2 vertices.
    for key in sorted(graph.incident):
        if len(graph.incident[key]) != 2:
            continue
        for idx in sorted(graph.incident[key]):
            if idx in used:
                continue
            trial_used: Set[int] = set(used)
            chain = _trace_from(graph, key, idx, trial_used)
            if chain.is_closed:
                used = trial_used
                chains.append(chain)
            break

    # Pass 2: whatever a closed walk did not claim becomes an open chain.
    #
    # LOOSE ENDS FIRST. Seeding from a degree-1 vertex walks the whole path in
    # one go; seeding from a vertex in the MIDDLE of a path walks only one
    # half and strands the other as a second chain. Taking an edge off a
    # four-edge rim, for instance, should leave one three-edge chain — seeded
    # from the middle it came back as a one-edge chain plus a two-edge chain,
    # which reports two gaps in the parting line where there is one.
    for key in sorted(graph.endpoint_vertices):
        for idx in sorted(graph.incident[key]):
            if idx in used:
                continue
            chains.append(_trace_from(graph, key, idx, used))

    # Anything still unclaimed has no loose end at all — an isolated ring the
    # closed-loop pass could not seed, or a fully-branched component. Traced
    # from wherever is left.
    for key in sorted(graph.incident):
        for idx in sorted(graph.incident[key]):
            if idx in used:
                continue
            chains.append(_trace_from(graph, key, idx, used))

    return chains


# ---------------------------------------------------------------------------
# Loop assembly
# ---------------------------------------------------------------------------

def build_parting_loops(
    boundary_edges: Sequence[BoundaryEdge],
    pull_dir: Vector3,
    config: Optional[AnalysisConfig] = None,
) -> Tuple[List[PartingLoop], List[PartingLoop], EdgeGraph]:
    """Turn candidate boundary edges into ordered loops.

    Returns (closed_loops, open_chains, graph). Loops are not yet ranked or
    scored — that is the validation stage's job.
    """
    cfg = resolve(config)
    graph = build_edge_graph(boundary_edges, cfg)
    if not graph.edges:
        return [], [], graph

    chains = trace_chains(graph, cfg)

    closed: List[PartingLoop] = []
    open_chains: List[PartingLoop] = []

    for chain in chains:
        members = [graph.edges[i] for i in chain.edge_indices]
        loop = PartingLoop(
            candidate_id=0,                       # assigned after ranking
            edges=[ge.boundary.edge for ge in members],
            num_edges=len(members),
            loop_length=sum(ge.boundary.length for ge in members),
            vertex_coords=chain.points,
            is_closed=chain.is_closed,
            branch_points=chain.branch_points,
            face_ids=tuple(sorted({
                fid for ge in members for fid in ge.boundary.face_ids if fid >= 0
            })),
            # The mold halves this loop has on either side of it. Halves, not
            # regions: a parting line separates steel, and a neutral face is
            # still made of one half's steel.
            separates=tuple(sorted({
                h for ge in members for h in ge.boundary.halves if h
            })),
            source="silhouette" if any(
                ge.boundary.source == "silhouette" for ge in members
            ) else "topology",
            shutoff_length=sum(
                ge.boundary.length for ge in members
                if ge.boundary.kind == EDGE_SHUTOFF
            ),
        )
        loop.axial_spread = _axial_spread(chain.points, pull_dir)
        # A rim that lies in one plane normal to the pull is the ideal
        # two-plate parting line. Judged against the loop's own size so the
        # test is scale-free.
        extent = max(_axial_spread(chain.points, a) for a in _basis(pull_dir))
        loop.is_planar = extent <= 0.0 or loop.axial_spread <= 0.01 * extent

        (closed if chain.is_closed else open_chains).append(loop)

    return closed, open_chains, graph


def _basis(pull_dir: Vector3) -> List[Vector3]:
    from core.parting.models import perpendicular_axes
    u, v = perpendicular_axes(norm(pull_dir))
    return [norm(pull_dir), u, v]


def _axial_spread(points: Sequence[Vector3], axis: Vector3) -> float:
    """Extent of a point set measured along a unit axis."""
    if not points:
        return 0.0
    projections = [dot(p, axis) for p in points]
    return max(projections) - min(projections)
