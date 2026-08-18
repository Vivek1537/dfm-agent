"""
core/analyzer.py — Orchestrates the backend DfM analysis pipeline.

    STEP file
        |
    parse faces + surface samples        step_parser
        |
    generate candidate pull directions   pull_direction
        |
    measure accessibility per direction  accessibility
        |
    evaluate + select the best axis      direction_evaluation
        |
    draft angles for that axis           draft_angle
        |
    classify mold regions                face_classifier
        |
    group trapped faces into features    undercut_regions
        |
    derive the parting line              parting/
        |
    AnalysisResult

The parting line comes LAST and depends on everything above it, which is the
point: it is an output of mold accessibility and region classification, not an
edge-selection heuristic run alongside them.
"""

import math
from typing import Optional, Tuple

from core.accessibility import AccessibilityAnalyzer
from core.delegation import EMPTY_PLAN, ToolingPlan, plan_for_part
from core.direction_evaluation import evaluate_pull_direction
from core.models import AnalysisResult, DirectionCandidate
from core.step_parser import parse_step
from core.mold_direction import find_best_mold_direction
# Aliased: `override_direction` is also this module's parameter name, and the
# parameter must keep that spelling because callers pass it by keyword.
from core.pull_direction import override_direction as make_override_direction
from core.draft_angle import compute_draft_angles
from core.face_classifier import classify_mold_regions, build_analysis_result
from core.parting_line import find_all_parting_lines
from core.tolerances import AnalysisConfig, resolve
from core.undercut_regions import find_undercut_regions


def analyze_part(
    filepath: str,
    part_name: str,
    override_direction: Optional[Tuple[float, float, float]] = None,
    exact_candidates: bool = True,
    config: Optional[AnalysisConfig] = None,
    tooling_plan: Optional[ToolingPlan] = None,
) -> AnalysisResult:
    """
    Run the full DfM analysis on a STEP file.

    If an override direction is provided, the expensive multi-axis search is
    skipped entirely and the analysis (accessibility, undercuts, draft,
    classification, parting line, score) is computed for that direction only.

    `exact_candidates=False` uses branch-and-bound pruning during the axis
    sweep. The winning direction is identical either way, but the losing
    candidates come back with lower-bound counts instead of exact ones. The
    API uses the fast path so the part renders quickly, then fills in the
    exact ranking from a follow-up request.
    """
    cfg = resolve(config)
    override = override_direction
    preferred_note = ""

    # 1. Parse faces and get the raw shape.
    faces, shape = parse_step(filepath)
    if not faces:
        raise ValueError("No faces found in STEP file.")

    # 1b. Tooling plan: feature groups the CALLER has declared are formed
    #     by side actions rather than by the two main halves. Never
    #     inferred — see core/delegation.py for why that would make every
    #     part report zero undercuts.
    plan = tooling_plan if tooling_plan is not None else plan_for_part(filepath)
    delegated = plan.delegated_face_ids(faces) if plan else frozenset()
    for face in faces:
        face.is_delegated = face.face_id in delegated

    analyzer = AccessibilityAnalyzer(faces, config=cfg, delegated=delegated)

    if override is not None:
        # 2a. User-chosen direction (flash placement, cosmetic surfaces).
        pull = make_override_direction(override)
        direction_to_use = pull.vector
        access = analyzer.analyze(direction_to_use)
        analyzer.apply_to_faces(access)

        best_candidate = DirectionCandidate(
            direction=direction_to_use,
            label=pull.label,
            undercut_count=access.undercut_count,
            undercut_area=access.undercut_area,
        )
        best_candidate.evaluation = evaluate_pull_direction(pull, access)
        best_candidate.accessibility = access
        all_candidates = [best_candidate]
    else:
        # 2b. Full search over fixed + geometry-derived axes.
        best_candidate, all_candidates = find_best_mold_direction(
            faces, analyzer.raycaster, exact_candidates=exact_candidates,
            config=cfg, analyzer=analyzer, shape=shape,
        )
        direction_to_use = best_candidate.direction
        access = best_candidate.accessibility

        # 2c. A declared preferred direction is VERIFIED against what the
        #     search found, never taken on trust. It is accepted only when it
        #     traps no more than the derived winner; otherwise the derived
        #     winner stands and the discrepancy is recorded.
        if plan is not None and plan.preferred_direction is not None:
            pref_access = analyzer.analyze(plan.preferred_direction)
            if pref_access.undercut_area <= access.undercut_area + 1e-9:
                analyzer.apply_to_faces(pref_access)
                direction_to_use = plan.preferred_direction
                access = pref_access
                best_candidate = DirectionCandidate(
                    direction=direction_to_use,
                    label=(f"declared({direction_to_use[0]:.2f},"
                           f"{direction_to_use[1]:.2f},{direction_to_use[2]:.2f})"),
                    undercut_count=pref_access.undercut_count,
                    undercut_area=pref_access.undercut_area,
                )
                best_candidate.accessibility = pref_access
                preferred_note = (
                    f"declared direction accepted: traps "
                    f"{pref_access.undercut_area:.1f} mm², no worse than the "
                    f"derived best")
            else:
                preferred_note = (
                    f"declared direction REJECTED: it traps "
                    f"{pref_access.undercut_area:.1f} mm² against the derived "
                    f"best's {access.undercut_area:.1f} mm²; the derived "
                    f"direction is used instead")

    # 3. Draft angles, worst case per face, relative to the chosen axis.
    compute_draft_angles(faces, direction_to_use)

    # 4. Mold regions: normal voting and reachability, reconciled with
    #    accessibility, then propagated over topology.
    classify_mold_regions(
        faces, direction_to_use, access=access,
        raycaster=analyzer.raycaster, shape=shape, config=cfg,
    )

    # 5. Group trapped faces into physical features. A face count is a
    #    topology artifact; the tooling decision is made per region.
    undercut_regions = find_undercut_regions(
        shape, faces, direction_to_use, analyzer.raycaster
    )

    # 6. Derive the parting line from the region boundaries.
    parting = find_all_parting_lines(
        shape, faces, direction_to_use,
        access=access, undercut_regions=undercut_regions, config=cfg,
        tooling_plan=plan,
    )

    # 7. Assemble the result.
    res = build_analysis_result(part_name, faces, best_candidate, all_candidates)
    res.raw_shape = shape
    res.parting_line_edges = parting.primary_loop.edges
    res.parting_line = parting
    res.is_override = override is not None
    res.undercut_regions = undercut_regions
    res.tooling_plan = plan
    res.preferred_direction_note = preferred_note
    res.required_actions = plan.resolve(faces) if plan else []
    res.alternatives = _alternatives(
        faces, analyzer, all_candidates, direction_to_use, plan, shape=shape
    )
    return res


def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Kept for callers that imported it. Prefer `pull_direction.normalize`."""
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-9:
        raise ValueError("Override direction must be a non-zero vector.")
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _alternatives(faces, analyzer, candidates, chosen, plan, shape=None):
    """Runner-up configurations, so the choice is visible rather than asserted.

    Every entry states the tooling it needs, not only the area it traps. Once
    side actions are on the table, trapped area alone stops discriminating —
    any undercut set reaches zero if the faces that constitute it are
    delegated — so the honest comparison is trapped area TOGETHER WITH the
    surface the two main halves retain and the number of extra motion axes.

    The best AXIAL candidate is always included, even when it ranks poorly on
    trapped area. When a delegation makes a clamshell win, the axial pull is
    the configuration a reader most needs to see next: it is the one that
    needs NO side core for the bore and NO insert for the splines, and its
    higher trapped area is the price of that. Dropping it off a truncated
    list would present the clamshell as though it had no competition.

    An alternative that traps something also gets `if_delegated`: what it
    would look like if ITS OWN trapped regions were handed to the mechanisms
    `undercut_regions` recommends. That is the like-for-like comparison —
    the primary reached zero by delegating, so the alternatives deserve the
    same courtesy — and it is computed, not asserted.
    """
    total = sum(f.area for f in faces) or 1.0
    delegated_area = sum(f.area for f in faces if f.is_delegated)
    axes = plan.action_axis_count() if plan else 0

    def entry(c, acc):
        # Each configuration is scored ON ITS OWN TERMS, and whether it needs
        # the declared plan is MEASURED, not assumed.
        #
        # Every candidate was evaluated with the plan's faces excluded, so a
        # zero says nothing on its own about whether that exclusion mattered.
        # It matters for a clamshell — neither half can form a bore whose axis
        # lies in the parting plane — and not at all for the axial pull, which
        # draws the bore and the splined end cleanly. Charging every
        # alternative for the plan put the axial row at 44% when it is 82%;
        # charging none of them put the clamshell rows at 100% when they are
        # 62%. So the delegated faces are re-measured under each direction.
        # `needs` is filled in after truncation — see below. Probing the
        # delegated faces costs a few thousand rays per direction, and at most
        # four of the dozen candidates survive into the report.
        return {
            "label": c.label,
            "direction": [round(v, 4) for v in c.direction],
            "undercut_count": c.undercut_count,
            "undercut_area": round(c.undercut_area, 1),
            # Provisional; corrected by _finalise() once the list is cut.
            "main_half_area": round(total - acc.undercut_area, 1),
            "main_half_fraction": round((total - acc.undercut_area) / total, 4),
            "delegated_area": 0.0,
            "needs_declared_plan": False,
            "extra_action_axes": 0,
            "is_axial": abs(c.direction[2]) > 0.9,
            "would_need_further_actions": c.undercut_count > 0,
            "if_delegated": None,
            "_acc": acc,
            "_dir": c.direction,
        }

    scored = []
    for c in candidates:
        if all(abs(a - b) < 1e-9 for a, b in zip(c.direction, chosen)):
            continue
        acc = c.accessibility or (
            c.evaluation.accessibility_result if c.evaluation else None)
        if acc is None:
            continue
        scored.append(entry(c, acc))

    # Sorted on the provisional main_half_area, which is safe: undercut_area
    # is the primary key, and before `needs` is known main_half_area is just
    # `total - undercut_area` — a monotonic function of that same key. The
    # order is therefore identical to sorting on the final figures.
    scored.sort(key=lambda a: (a["undercut_area"], -a["main_half_area"]))
    out = scored[:3]

    # Guarantee the best axial candidate is present.
    if not any(a["is_axial"] for a in out):
        axial = [a for a in scored if a["is_axial"]]
        if axial:
            out.append(axial[0])

    # Now that the list is cut, measure whether each surviving row actually
    # needs the declared plan. Doing this before the cut probed a dozen
    # directions to report at most four.
    for a in out:
        needs = _plan_area_needed_by(faces, analyzer, a["_dir"], plan)
        a["delegated_area"] = round(needs, 1)
        a["needs_declared_plan"] = needs > 0.0
        a["extra_action_axes"] = axes if needs > 0.0 else 0
        main_half_area = total - needs - a["_acc"].undercut_area
        a["main_half_area"] = round(main_half_area, 1)
        a["main_half_fraction"] = round(main_half_area / total, 4)

    # Quantify the delegated variant for the best trapping alternative. Only
    # one: grouping trapped faces into regions costs ~4 s on a 414-face part,
    # and it is the axial row a reader actually compares against.
    if shape is not None:
        target = next(
            (a for a in out if a["is_axial"] and a["undercut_count"] > 0),
            next((a for a in out if a["undercut_count"] > 0), None),
        )
        if target is not None:
            target["if_delegated"] = _delegated_variant(
                faces, analyzer, shape, target, total, delegated_area, plan
            )

    for a in out:
        a.pop("_acc", None)
        a.pop("_dir", None)
    return out


def _delegated_variant(faces, analyzer, shape, alt, total, delegated_area, plan):
    """What an alternative looks like if its own trapped regions are delegated.

    Groups the alternative's trapped faces with the same grouper the primary
    path uses, so the recommended mechanisms and their axes come from the
    published decision tree rather than from an assumption.

    Per-face undercut flags are saved and restored around this: they belong to
    the CHOSEN direction, and a comparison must not corrupt the result it is
    being compared against.
    """
    from core.delegation import ACTION_AXIS_MERGE_DOT
    from core.undercut_regions import find_undercut_regions, summarize_regions

    acc, direction = alt["_acc"], alt["_dir"]
    saved = [(f.is_undercut, f.trapped_fraction) for f in faces]
    try:
        for f in faces:
            e = acc.faces.get(f.face_id)
            if e is not None:
                f.is_undercut = e.is_undercut
                f.trapped_fraction = e.trapped_fraction
        regions = find_undercut_regions(shape, faces, direction, analyzer.raycaster)
        summary = summarize_regions(regions)
    finally:
        for f, (uc, frac) in zip(faces, saved):
            f.is_undercut = uc
            f.trapped_fraction = frac

    # Its own regions travel on their own axes, on top of whatever the
    # declared plan already needs.
    own_axes = [r.side_action_direction for r in regions
                if not r.is_internal and r.side_action_direction != (0.0, 0.0, 0.0)]
    merged: list = []
    for a in own_axes:
        if not any(abs(sum(a[i] * b[i] for i in range(3))) > ACTION_AXIS_MERGE_DOT
                   for b in merged):
            merged.append(a)

    # Delegating this configuration's own trapped set moves that area from
    # "trapped" to "formed by a side action". Either way it is off the main
    # halves' books, so their coverage is unchanged — what changes is that the
    # part becomes manufacturable, at the cost of the actions listed here.
    main_half_area = total - alt["delegated_area"] - acc.undercut_area
    return {
        "undercut_area": 0.0,
        "undercut_count": 0,
        "main_half_area": round(main_half_area, 1),
        "main_half_fraction": round(main_half_area / total, 4),
        "region_count": len(regions),
        # Its own axes PLUS the plan's, but only if it actually needs the
        # plan — measured above, not assumed.
        "extra_action_axes": alt["extra_action_axes"] + len(merged),
        "mechanisms": summary["mechanisms"],
        "action_axes": [[round(c, 3) for c in a] for a in merged],
        "delegated_area": round(alt["delegated_area"] + acc.undercut_area, 1),
    }


def _plan_area_needed_by(faces, analyzer, direction, plan):
    """Area of the plan's delegated faces that THIS direction cannot release.

    Candidate directions are all evaluated with the plan's faces excluded, so
    a candidate's zero does not say whether it needed that exclusion. This
    re-measures those faces for one direction, with no exclusion, and returns
    the area still trapped — the area that direction genuinely has to hand to
    a side action.

    Returns 0.0 when no plan is declared, or when the direction releases every
    delegated face on its own.
    """
    if not plan:
        return 0.0
    delegated = [f for f in faces if getattr(f, "is_delegated", False)]
    if not delegated:
        return 0.0
    # A bare analyzer over the same raycaster: same cached rays, no exclusion.
    from core.accessibility import AccessibilityAnalyzer
    probe = AccessibilityAnalyzer(faces, analyzer.raycaster, analyzer.config)
    probe._cache = analyzer._cache          # share the memoised probes
    result = probe.analyze(
        direction,
        max_samples=analyzer.config.sweep_samples_per_face,
        faces=delegated,
        four_way=False,
    )
    return sum(
        f.area for f in delegated
        if result.faces.get(f.face_id) and result.faces[f.face_id].is_undercut
    )
