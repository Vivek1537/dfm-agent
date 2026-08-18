"""
core/delegation.py — Feature groups handed to side actions.

A two-plate mold forms a part with two halves travelling along one axis.
Real molds routinely do more: a side core forms an internal passage, a lifter
clears a recess, an insert forms a splined end. Bosch's own walkthrough of the
nozzle (`docs/bosch-nozzle-review-transcript.md`, 00:42.8 and 01:28.5) is
exactly this shape -- "It splits the two halves, and then there will be a side
core, which is used to form this, uh, pin feature."

A DELEGATED group is a set of faces the mold designer has decided some
mechanism other than the two main halves will form. Those faces come off the
main halves' books: they are not undercuts of the chosen pull direction,
because the pull direction was never asked to release them.

WHY THIS IS AN INPUT AND NEVER A DERIVED RESULT
-----------------------------------------------
This is the load-bearing design decision in this module, and it is not
negotiable without making the whole engine dishonest.

Delegation ALWAYS terminates at zero. Any undercut set whatsoever reaches
"0 undercuts" if you delegate the faces that constitute it. Measured on
Part 3: the axial pull traps 1366.8 mm^2 in two slot regions, and delegating
those two regions -- which is precisely the tooling the engine already
recommends -- gives 0.0 mm^2 remaining. The clamshell traps the bore and the
splines, and delegating those gives 0.0 mm^2 too. Both reach zero. Zero is
therefore not evidence of anything; it is a restatement of what was delegated.

So if the engine chose delegations for itself, every part would report zero
undercuts and the undercut analysis would convey no information at all. Worse,
Part 1's zero -- which is genuine, a clean two-plate draw with no side actions
whatever -- would become indistinguishable from Part 3's zero, which costs two
additional axial actions. That distinction is the single most valuable thing
the tool reports about a part.

Delegation is therefore declared by the caller, per part, as a statement of
TOOLING INTENT. `ToolingPlan.required_actions` then travels with the result all
the way to the API and the UI so that a zero can never be read without the
price of that zero next to it.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vector3 = Tuple[float, float, float]

# Two action axes closer than this (|dot|) are the same axis -- a pair of
# opposed sliders travels on one axis, not two. Matches the convention in
# core/undercut_regions.summarize_regions.
ACTION_AXIS_MERGE_DOT = math.cos(math.radians(30.0))


@dataclass(frozen=True)
class FaceSelector:
    """Which faces a delegated group covers.

    Selectors are geometric wherever possible. An explicit `face_ids` list is
    exact but brittle -- ids come from STEP traversal order and shift if the
    model is re-exported -- so it is best reserved for a handful of named
    faces. A z/r band survives a re-export and is the right way to name a
    whole section of a part.
    """

    face_ids: Tuple[int, ...] = ()
    z_min: Optional[float] = None
    z_max: Optional[float] = None
    r_min: Optional[float] = None
    r_max: Optional[float] = None
    surface_types: Tuple[str, ...] = ()

    def matches(self, face: Any) -> bool:
        if self.face_ids and face.face_id in self.face_ids:
            return True
        if not any((self.z_min is not None, self.z_max is not None,
                    self.r_min is not None, self.r_max is not None,
                    self.surface_types)):
            return False
        z = face.center[2]
        r = math.hypot(face.center[0], face.center[1])
        if self.z_min is not None and z < self.z_min:
            return False
        if self.z_max is not None and z > self.z_max:
            return False
        if self.r_min is not None and r < self.r_min:
            return False
        if self.r_max is not None and r > self.r_max:
            return False
        if self.surface_types and face.surface_type not in self.surface_types:
            return False
        return True

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FaceSelector":
        return FaceSelector(
            face_ids=tuple(d.get("face_ids", ())),
            z_min=d.get("z_min"),
            z_max=d.get("z_max"),
            r_min=d.get("r_min"),
            r_max=d.get("r_max"),
            surface_types=tuple(d.get("surface_types", ())),
        )


@dataclass(frozen=True)
class DelegatedGroup:
    """One feature group formed by a mechanism other than the main halves."""

    name: str
    mechanism: str                  # "axial side core", "lifter", "slider", ...
    action_axis: Vector3            # direction the mechanism travels
    selector: FaceSelector
    rationale: str = ""

    def face_ids(self, faces: Sequence[Any]) -> frozenset:
        return frozenset(f.face_id for f in faces if self.selector.matches(f))

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "DelegatedGroup":
        axis = tuple(float(v) for v in d.get("action_axis", (0.0, 0.0, 1.0)))
        mag = math.sqrt(sum(c * c for c in axis))
        if mag < 1e-9:
            raise ValueError(f"delegated group '{d.get('name')}' has a zero action axis")
        return DelegatedGroup(
            name=str(d["name"]),
            mechanism=str(d.get("mechanism", "side action")),
            action_axis=tuple(c / mag for c in axis),
            selector=FaceSelector.from_dict(d.get("select", {})),
            rationale=str(d.get("rationale", "")),
        )


@dataclass(frozen=True)
class ToolingPlan:
    """The delegated groups declared for one part. Empty by default."""

    groups: Tuple[DelegatedGroup, ...] = ()
    source: str = ""                # where the plan came from, for the report

    # Optionally, WHICH of the equivalent pull directions to use.
    #
    # The direction search cannot afford to build a parting line for every
    # candidate -- classification alone is ~4 s per direction on a 414-face
    # part -- so when several directions tie at zero undercuts it separates
    # them on cheap proxies and any of them is a defensible answer. A mold
    # designer choosing between them on parting-line quality is supplying
    # information the search did not have, not overriding it.
    #
    # It is VERIFIED, never trusted: `analyze_part` measures the declared
    # direction and, if it is worse than what the search found, reports that
    # prominently rather than quietly accepting it.
    preferred_direction: Optional[Vector3] = None
    preferred_rationale: str = ""

    def __bool__(self) -> bool:
        return bool(self.groups) or self.preferred_direction is not None

    def delegated_face_ids(self, faces: Sequence[Any]) -> frozenset:
        out: frozenset = frozenset()
        for g in self.groups:
            out |= g.face_ids(faces)
        return out

    def resolve(self, faces: Sequence[Any]) -> List[Dict[str, Any]]:
        """Per-group face sets and areas, for reporting."""
        by_id = {f.face_id: f for f in faces}
        out = []
        for g in self.groups:
            ids = sorted(g.face_ids(faces))
            out.append({
                "name": g.name,
                "mechanism": g.mechanism,
                "action_axis": [round(c, 4) for c in g.action_axis],
                "face_count": len(ids),
                "area": round(sum(by_id[i].area for i in ids), 1),
                "rationale": g.rationale,
                "face_ids": ids,
            })
        return out

    def action_axis_count(self) -> int:
        """Distinct axes the delegated mechanisms travel on.

        Opposed mechanisms share one axis, so they are merged -- the same rule
        `core/undercut_regions.summarize_regions` uses.
        """
        axes: List[Vector3] = []
        for g in self.groups:
            a = g.action_axis
            if not any(abs(sum(a[i] * b[i] for i in range(3))) > ACTION_AXIS_MERGE_DOT
                       for b in axes):
                axes.append(a)
        return len(axes)

    def delegated_area(self, faces: Sequence[Any]) -> float:
        """Total area delegated, counting each face ONCE.

        Groups may overlap — Part 3's bore chamfer at z=39.5 belongs to the
        bore group by face id and to the splined section by z band — so summing
        the per-group areas double-counts the intersection. Summed over the
        deduplicated face set instead.
        """
        ids = self.delegated_face_ids(faces)
        return sum(f.area for f in faces if f.face_id in ids)

    def to_dict(self, faces: Sequence[Any]) -> Dict[str, Any]:
        groups = self.resolve(faces)
        return {
            "declared": bool(self.groups),
            "source": self.source,
            "preferred_direction": (
                [round(c, 4) for c in self.preferred_direction]
                if self.preferred_direction else None),
            "preferred_rationale": self.preferred_rationale,
            "group_count": len(groups),
            "action_axis_count": self.action_axis_count(),
            "delegated_area": round(self.delegated_area(faces), 1),
            "groups": groups,
        }


EMPTY_PLAN = ToolingPlan()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_plan(path: str) -> ToolingPlan:
    """Read a tooling plan from a JSON file."""
    with open(path, "r") as fh:
        data = json.load(fh)
    groups = tuple(DelegatedGroup.from_dict(g) for g in data.get("groups", []))
    pref = data.get("preferred_direction")
    if pref is not None:
        v = tuple(float(c) for c in pref)
        mag = math.sqrt(sum(c * c for c in v))
        if mag < 1e-9:
            raise ValueError("preferred_direction must be a non-zero vector")
        pref = tuple(c / mag for c in v)
    return ToolingPlan(
        groups=groups,
        source=os.path.basename(path),
        preferred_direction=pref,
        preferred_rationale=str(data.get("preferred_rationale", "")),
    )


def plan_for_part(filepath: str) -> ToolingPlan:
    """Find the tooling plan sitting beside a STEP file, if any.

    `assets/Part3.stp` -> `assets/Part3.tooling.json`.

    A file beside the model, rather than a table inside the engine, on
    purpose: a delegation is a statement about how somebody intends to build
    the mold, so it belongs with the part and has to be readable and editable
    without touching code. An engine that carried its own per-part answers
    would be reporting its inputs back as if it had derived them.
    """
    stem, _ext = os.path.splitext(filepath)
    candidate = f"{stem}.tooling.json"
    if os.path.exists(candidate):
        return load_plan(candidate)
    return EMPTY_PLAN
