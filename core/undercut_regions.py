"""
Group trapped faces into undercut REGIONS and recommend a mold mechanism.

A B-rep face count is not an engineering answer. CAD kernels shatter a single
physical recess into dozens of faces — Part3's two rib pockets arrive as 88
faces, 56 of which are sub-2mm2 fillet slivers. Every DfM source we work from
reasons in features instead: Qlution's worked example reports "three undercuts"
for a housing with dozens of trapped faces.

This module collapses trapped faces into connected regions and applies the
standard decision tree to each one:

    internal + wraps a full turn  -> collapsible core   (threads, O-ring grooves)
    internal                      -> lifter
    external                      -> side-action slider
    shallow enough + soft resin   -> forced ejection may avoid tooling entirely

Sources:
  - Qlution Mold, "Injection Molding Undercuts: A Practical DFM Guide for
    Engineers" — external/internal split, lifter vs slider vs collapsible
    core, forced-ejection depth limits, the multi-axis warning.
  - Protolabs, "6 Ways to Achieve Undercut Success in Molded Parts" —
    parting-line adjustment and side-action practice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from core.models import FaceData

# A single lateral action frees only surfaces whose normals lie within 90 deg
# of its travel, so it cannot clear a feature sweeping much beyond 180 deg
# about the pull axis. Past that the answer is opposed sliders or split jaws.
SINGLE_ACTION_MAX_SPAN_DEG = 180.0

# A region spanning nearly a full turn about the pull axis cannot be cleared by
# a slider or a lifter travelling in one direction.
FULL_TURN_DEG = 300.0

# Qlution: sliders on three or more axes is "a mold design problem as much as a
# manufacturing cost problem" and should prompt revisiting the part.
MULTI_AXIS_WARNING = 3

# Two side-action directions count as the same axis below this separation.
AXIS_MERGE_DEG = 30.0


@dataclass
class UndercutRegion:
    """One physically connected undercut feature."""

    region_id: int
    face_ids: List[int]
    area: float
    centroid: Tuple[float, float, float]
    is_internal: bool
    side_action_direction: Tuple[float, float, float]
    angular_span_deg: float
    wraps_full_turn: bool
    mechanism: str
    rationale: str
    z_range: Tuple[float, float] = (0.0, 0.0)

    @property
    def face_count(self) -> int:
        return len(self.face_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "face_count": self.face_count,
            "area": round(self.area, 1),
            "centroid": [round(v, 2) for v in self.centroid],
            "is_internal": self.is_internal,
            "kind": "internal" if self.is_internal else "external",
            "side_action_direction": [round(v, 3) for v in self.side_action_direction],
            "angular_span_deg": round(self.angular_span_deg, 1),
            "wraps_full_turn": self.wraps_full_turn,
            "mechanism": self.mechanism,
            "rationale": self.rationale,
            "z_range": [round(v, 2) for v in self.z_range],
        }


# ------------------------------------------------------------------ helpers
def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _build_adjacency(shape, faces: List[FaceData]) -> Dict[int, set]:
    """Face-id adjacency graph from shared edges."""
    by_tshape = {f.face_shape.TShape(): f.face_id for f in faces if f.face_shape}
    adj: Dict[int, set] = {f.face_id: set() for f in faces}

    mapping = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, mapping)
    for i in range(1, mapping.Extent() + 1):
        touching = [by_tshape.get(s.TShape()) for s in mapping.FindFromIndex(i)]
        touching = [t for t in touching if t is not None]
        for a in touching:
            for b in touching:
                if a != b:
                    adj[a].add(b)
    return adj


def _connected_regions(face_ids: set, adj: Dict[int, set]) -> List[List[int]]:
    seen: set = set()
    out: List[List[int]] = []
    for fid in sorted(face_ids):
        if fid in seen:
            continue
        stack, comp = [fid], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            for nb in adj.get(cur, ()):
                if nb in face_ids and nb not in seen:
                    stack.append(nb)
        out.append(sorted(comp))
    return out


def _region_is_internal(
    region_faces: List[FaceData],
    withdraw: Tuple[float, float, float],
    raycaster,
) -> bool:
    """
    External vs internal, by REACHABILITY along the withdrawal direction.

    Qlution's definition is about tool access, not surface concavity:
    external undercuts "sit on the outside of the part, accessible from the
    mold's exterior", while internal ones "exist inside the part geometry:
    no mold action can reach them from the outside". So the test is whether
    an action travelling along the withdrawal direction can escape the part.

    An earlier version asked whether each face's own normal ray re-entered
    material. That marks every hole internal — a ray leaving a bore wall
    always crosses the void and strikes the far wall — and it wrongly
    recommended a lifter for the side holes on PLASTIC BUSH, which the
    reference mold releases with a slide core. Qlution lists "side holes,
    lateral slots" as external explicitly.
    """
    if raycaster is None or withdraw == (0.0, 0.0, 0.0):
        return False
    neg = (-withdraw[0], -withdraw[1], -withdraw[2])
    escaped_w = 0.0
    total_w = 0.0
    for f in region_faces:
        if not f.sample_points:
            continue
        w = f.area / max(len(f.sample_points), 1)
        for p, n in zip(f.sample_points, f.sample_normals):
            total_w += w
            try:
                if not raycaster.is_blocked(p, n, withdraw) or not raycaster.is_blocked(
                    p, n, neg
                ):
                    escaped_w += w
            except Exception:
                escaped_w += w
    # Reachable from outside along the action axis => external.
    return total_w > 0 and (escaped_w / total_w) <= 0.5


def _side_action_direction(
    region_faces: List[FaceData], pull: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """
    Direction a slider or lifter must travel to clear the region.

    For hole- and slot-like features the tool withdraws along the FEATURE
    AXIS, not along the surface normal: the pin forming a side hole retracts
    down the bore. So when the region is dominated by cylinders or cones
    sharing an axis that lies across the pull direction, that axis wins.
    Otherwise fall back to the area-weighted mean outward normal with the
    pull component removed, which suits open pockets and recesses.
    """
    axis_w: Dict[Tuple[int, int, int], List[Any]] = {}
    for f in region_faces:
        if f.surface_type not in ("CYLINDER", "CONE") or f.axis is None:
            continue
        a = _normalize(f.axis)
        if abs(sum(a[i] * pull[i] for i in range(3))) > 0.9:
            continue  # axial feature: released by the main pull, not a side action
        key = tuple(int(round(abs(c) * 20)) for c in a)
        slot = axis_w.setdefault(key, [0.0, a])
        slot[0] += f.area

    if axis_w:
        best = max(axis_w.values(), key=lambda s: s[0])
        total_cyl = sum(s[0] for s in axis_w.values())
        if total_cyl > 0 and best[0] / total_cyl > 0.5:
            return _normalize(best[1])

    acc = [0.0, 0.0, 0.0]
    for f in region_faces:
        if not f.sample_normals:
            continue
        w = f.area / len(f.sample_normals)
        for n in f.sample_normals:
            acc[0] += n[0] * w
            acc[1] += n[1] * w
            acc[2] += n[2] * w
    dot = sum(acc[i] * pull[i] for i in range(3))
    lateral = tuple(acc[i] - dot * pull[i] for i in range(3))
    d = _normalize(lateral)
    return d if d != (0.0, 0.0, 0.0) else _normalize(tuple(acc))


def _angular_span(
    region_faces: List[FaceData], pull: Tuple[float, float, float]
) -> float:
    """Angular extent swept about the pull axis, in degrees."""
    ref = (1.0, 0.0, 0.0) if abs(pull[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _normalize(
        (
            ref[1] * pull[2] - ref[2] * pull[1],
            ref[2] * pull[0] - ref[0] * pull[2],
            ref[0] * pull[1] - ref[1] * pull[0],
        )
    )
    v = (
        pull[1] * u[2] - pull[2] * u[1],
        pull[2] * u[0] - pull[0] * u[2],
        pull[0] * u[1] - pull[1] * u[0],
    )
    angles = []
    for f in region_faces:
        for p in f.sample_points:
            angles.append(
                math.degrees(
                    math.atan2(
                        sum(p[i] * v[i] for i in range(3)),
                        sum(p[i] * u[i] for i in range(3)),
                    )
                )
                % 360.0
            )
    if len(angles) < 2:
        return 0.0
    angles.sort()
    # Largest angular gap; the span is whatever the gap does not cover.
    gap = max(
        [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
        + [angles[0] + 360.0 - angles[-1]]
    )
    return 360.0 - gap


def _recommend(region: UndercutRegion) -> Tuple[str, str]:
    """Apply the published decision tree. Returns (mechanism, rationale).

    Deliberately does NOT attempt the forced-ejection ("bump-off") check.
    That rule is a ratio of recess DEPTH to feature diameter, and measuring
    true recess depth needs the distance at which a ray leaves the solid,
    which the current raycaster does not expose (it answers blocked/not
    blocked). Two attempts at approximating it produced obviously wrong
    figures — 13.8 mm for a 3 mm pocket — so the check is omitted rather
    than reported unreliably. It is also material-dependent, and a STEP file
    carries no resin.
    """
    span = region.angular_span_deg
    if region.is_internal:
        if region.wraps_full_turn:
            return (
                "collapsible core",
                f"internal and continuous around {span:.0f}° of the pull axis — "
                f"the classic thread / O-ring-groove case, where no "
                f"single-direction action can clear the feature",
            )
        return (
            "lifter",
            "internal feature — a slider cannot reach inside the part envelope, "
            "so it is cleared on the ejector stroke",
        )
    if span > SINGLE_ACTION_MAX_SPAN_DEG:
        return (
            "split cavity (jaws) or opposed sliders",
            f"external but sweeping {span:.0f}° about the pull axis. One lateral "
            f"action only frees surfaces within 90° of its travel, so a single "
            f"slider cannot clear more than about 180°",
        )
    return (
        "side-action slider",
        f"external recess spanning {span:.0f}°, reachable laterally from outside "
        f"the part envelope",
    )


# -------------------------------------------------------------------- main
def find_undercut_regions(
    shape,
    faces: List[FaceData],
    pull_direction: Tuple[float, float, float],
    raycaster=None,
) -> List[UndercutRegion]:
    """Cluster trapped faces into features and recommend a mechanism for each."""
    trapped = {f.face_id for f in faces if f.is_undercut}
    if not trapped:
        return []

    by_id = {f.face_id: f for f in faces}
    pull = _normalize(pull_direction)
    adj = _build_adjacency(shape, faces)

    regions: List[UndercutRegion] = []
    for idx, comp in enumerate(
        sorted(
            _connected_regions(trapped, adj),
            key=lambda c: -sum(by_id[i].area for i in c),
        )
    ):
        rf = [by_id[i] for i in comp]
        area = sum(f.area for f in rf)
        cx = sum(f.center[0] * f.area for f in rf) / area if area else 0.0
        cy = sum(f.center[1] * f.area for f in rf) / area if area else 0.0
        cz = sum(f.center[2] * f.area for f in rf) / area if area else 0.0

        direction = _side_action_direction(rf, pull)
        span = _angular_span(rf, pull)
        zs = [f.center[2] for f in rf]

        region = UndercutRegion(
            region_id=idx + 1,
            face_ids=comp,
            area=area,
            centroid=(cx, cy, cz),
            is_internal=_region_is_internal(rf, direction, raycaster),
            side_action_direction=direction,
            angular_span_deg=span,
            wraps_full_turn=span >= FULL_TURN_DEG,
            mechanism="",
            rationale="",
            z_range=(min(zs), max(zs)) if zs else (0.0, 0.0),
        )
        region.mechanism, region.rationale = _recommend(region)
        regions.append(region)

    return regions


def summarize_regions(regions: List[UndercutRegion]) -> Dict[str, Any]:
    """Tooling-level rollup across all regions."""
    axes: List[Tuple[float, float, float]] = []
    for r in regions:
        if r.is_internal or r.side_action_direction == (0.0, 0.0, 0.0):
            continue
        d = r.side_action_direction
        # Opposed sliders travel on one shared axis; merge them.
        if not any(
            abs(sum(d[i] * a[i] for i in range(3))) > math.cos(math.radians(AXIS_MERGE_DEG))
            for a in axes
        ):
            axes.append(d)

    counts: Dict[str, int] = {}
    for r in regions:
        key = r.mechanism.split(" (")[0]
        counts[key] = counts.get(key, 0) + 1

    return {
        "region_count": len(regions),
        "external_count": sum(1 for r in regions if not r.is_internal),
        "internal_count": sum(1 for r in regions if r.is_internal),
        "side_action_axes": len(axes),
        "mechanisms": counts,
        "multi_axis_warning": len(axes) >= MULTI_AXIS_WARNING,
    }
