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
from core.parting_line import compute_parting_line_result


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

    pl = compute_parting_line_result(result.raw_shape, result.faces, result.best_mold_direction if not override else override)
    t2 = time.perf_counter()

    print(f"part               : {result.part_name}")
    print(f"total_faces        : {result.total_faces}")
    print(f"best_direction     : {result.best_mold_direction}")
    print(f"score              : {result.manufacturability_score:.1f}")
    print(f"core_faces         : {result.core_face_count}")
    print(f"cavity_faces       : {result.cavity_face_count}")
    print(f"undercut_faces     : {result.undercut_face_count}")
    print(f"warning_faces      : {result.warning_face_count}")
    print(f"pl_loops           : {pl.total_candidate_count}")
    print(f"pl_primary_edges   : {pl.primary_loop.num_edges}")
    print(f"pl_ambiguous       : {pl.is_ambiguous}")
    print("direction_candidates:")
    for c in sorted(result.direction_candidates, key=lambda c: (c.undercut_area, c.undercut_count)):
        bound = ">" if getattr(c, "pruned", False) else "="
        print(f"  {c.label:6s} undercuts{bound}{c.undercut_count:4d} area{bound}{c.undercut_area:10.1f}")
    print(f"analysis_time      : {t1 - t0:.1f}s")
    print(f"parting_line_time  : {t2 - t1:.1f}s")


if __name__ == "__main__":
    main()
