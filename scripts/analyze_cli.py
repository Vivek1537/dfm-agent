"""
scripts/analyze_cli.py — Headless analysis runner for regression checks.

Usage:
    python scripts/analyze_cli.py assets/Part1.stp [--direction x,y,z]

Prints a compact summary of the DfM analysis so results can be compared
before/after algorithm changes.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import analyze_part


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("filepath")
    ap.add_argument("--direction", help="Override pull direction as x,y,z", default=None)
    args = ap.parse_args()

    override = None
    if args.direction:
        override = tuple(float(v) for v in args.direction.split(","))

    t0 = time.perf_counter()
    result = analyze_part(args.filepath, Path(args.filepath).name, override_direction=override)
    t1 = time.perf_counter()

    # The parting line is computed inside analyze_part and read back here. It
    # used to be recomputed at this point from the same inputs.
    pl = result.parting_line
    loop = pl.primary_loop

    print(f"part               : {result.part_name}")
    print(f"total_faces        : {result.total_faces}")
    print(f"best_direction     : {result.best_mold_direction}")
    print(f"score              : {result.manufacturability_score:.1f}")
    print(f"core_faces         : {result.core_face_count}")
    print(f"cavity_faces       : {result.cavity_face_count}")
    print(f"undercut_faces     : {result.undercut_face_count}"
          + ("   <-- MAIN HALVES ONLY; see required_actions below"
             if result.required_actions else ""))
    print(f"undercut_regions   : {len(result.undercut_regions)}")
    print(f"warning_faces      : {result.warning_face_count}")
    print(f"pl_loops           : {len(pl.loops)} closed, {len(pl.open_chains)} open")
    print(f"pl_primary_edges   : {loop.num_edges}")
    print(f"pl_primary_closed  : {loop.is_closed}")
    print(f"pl_primary_planar  : {loop.is_planar}")
    print(f"pl_primary_source  : {loop.source}")
    print(f"pl_branch_points   : {loop.branch_points}")
    print(f"pl_length          : {loop.loop_length:.2f}")
    print(f"pl_projected_area  : {loop.projected_area:.2f}")
    if loop.shutoff_length:
        print(f"pl_shutoff_length  : {loop.shutoff_length:.2f}  "
              f"(side action, not main parting line)")
    print(f"pl_ambiguous       : {pl.is_ambiguous}")
    print(f"pl_valid           : {pl.is_valid}")
    print(f"pl_confidence      : {pl.confidence:.3f}")
    if pl.validation and pl.validation.failures:
        print("pl_failures:")
        for check in pl.validation.failures:
            print(f"  [{check.category}] {check.name}: {check.detail}")
    if result.required_actions:
        # Printed BEFORE the direction ranking and impossible to miss: the
        # undercut count above describes the two main halves only, and this is
        # what that zero costs.
        axes = result.tooling_plan.action_axis_count() if result.tooling_plan else 0
        total = sum(a["area"] for a in result.required_actions)
        print(f"REQUIRED SIDE ACTIONS : {len(result.required_actions)} "
              f"({total:.1f} mm2 on {axes} extra axis/axes) "
              f"[declared in {getattr(result.tooling_plan, 'source', '?')}]")
        for a in result.required_actions:
            ax = a["action_axis"]
            print(f"  - {a['name']:14s} {a['mechanism']:22s} "
                  f"along ({ax[0]:+.2f},{ax[1]:+.2f},{ax[2]:+.2f})  "
                  f"{a['face_count']:3d} faces {a['area']:8.1f} mm2")
        if result.preferred_direction_note:
            print(f"  direction: {result.preferred_direction_note}")
    if result.alternatives:
        print("alternatives:")
        for a in result.alternatives:
            tag = " [axial, no side core needed]" if a["is_axial"] else ""
            print(f"  {a['label']:22s} undercuts={a['undercut_count']:3d} "
                  f"area={a['undercut_area']:8.1f}  main_half={a['main_half_area']:8.1f} "
                  f"({a['main_half_fraction']:.1%}){tag}")
    print("direction_candidates:")
    for c in sorted(result.direction_candidates, key=lambda c: (c.undercut_area, c.undercut_count)):
        bound = ">" if getattr(c, "pruned", False) else "="
        ev = getattr(c, "evaluation", None)
        extra = (
            f"  access={ev.accessibility:.2f} cplx={ev.complexity:.2f} "
            f"regions={ev.region_count} src={ev.direction.source}"
            if ev is not None else ""
        )
        print(f"  {c.label:22s} undercuts{bound}{c.undercut_count:4d} "
              f"area{bound}{c.undercut_area:10.1f}{extra}")
    print(f"analysis_time      : {t1 - t0:.1f}s")


if __name__ == "__main__":
    main()
