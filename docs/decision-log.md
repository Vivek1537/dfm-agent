# Decision Log

This document records the key architectural and technical decisions made during the development of the AI-driven DfM (Design for Manufacturing) Tool.

## 1. Frontend Architecture: Streamlit vs. React + FastAPI
**Context**: The initial prototype was built using Streamlit (`app.py`) for rapid development and testing of the core python algorithms.
**Decision**: We transitioned to a separated architecture with a **FastAPI backend** and a **React frontend** (Vite + JavaScript).
**Rationale**: 
- Streamlit's 3D visualization capabilities (via PyVista/Trame) were clunky and limited for high-fidelity interactive models. 
- A React frontend using `@react-three/fiber` and `three.js` allows for a much more premium, dynamic, and responsive 3D viewer.
- The separation of concerns allows the backend to focus purely on heavy OpenCASCADE (cadquery) computations while the frontend handles rendering.

## 2. Undercut Detection Algorithm
**Context**: We needed a reliable way to determine if a face is an undercut (trapped) for a given mold pull direction.
**Decision (v2)**: Multi-sample physical raycasting using OpenCASCADE (`IntCurvesFace_ShapeIntersector`). Every face carries up to 15 surface samples (UV grid, `TopAbs_IN`-classified). Per sample: a face-cavity sample must escape along +pull, a face-core sample along −pull, a vertical-wall sample is trapped only if BOTH ways are blocked. A face is an undercut when ≥ 50% of its samples are trapped.
**Rationale**: Simple draft angle checks are insufficient for identifying true undercuts. Single-midpoint rays (v1, Phase 1) misclassified curved faces — a cylinder's midpoint normal misrepresents a surface whose normals span 360°. This was the root cause of the Phase 1 "wrongly marked undercut faces" feedback.

## 3. Tangential-Graze Filtering (replaces the v1 tiebreaker)
**Context**: Rays traveling parallel to vertical walls grazed adjacent blend fillets and reported phantom blockers — 4 false undercuts on the Phase 1 cap whose official answer is zero.
**Decision**: Only ray hits whose transition is `IntCurveSurface_In` (ray entering material) count as blockers; `Out`/`Tangent` hits are ignored. Minimum hit distance 0.1 mm, ray origin offset 0.01 mm.
**Rationale**: A grazing contact is not a physical obstruction to mold opening. After this filter, Part 1 reports exactly the judges' reference answer (0 undercuts).

## 4. Manufacturability Scoring Formula
**Context**: The initial score formula only penalized undercut *area*. Because of this, changing the pull direction often resulted in identical scores even if the *number* of undercut faces drastically increased.
**Decision**: We updated the scoring formula to penalize both undercut/warning **area** AND undercut/warning **count**.
**Rationale**: A part with 1 large undercut is often easier to fix than a part with 20 small scattered undercuts. Factoring in the face count provides a more nuanced, direction-sensitive manufacturability score.

## 5. Parting Line Identification
**Context**: Finding the optimal parting line for complex 3D shapes; Bosch requires ONE closed primary loop ("a discontinuous loop cannot form a surface — it is solid steel").
**Decision**: Extract all core↔cavity boundary edges, group into connected components, chain each component end-to-end with adaptive curve tessellation, verify closure, and rank with a 6-metric weighted score (projected area 40%, outer-boundary confidence 20%, moldability 15%, simplicity 10%, separation quality 10%, length 5%). Open chains are penalized 4× so they can never beat a closed loop. The top closed loop is the single primary parting line.
**Rationale**: Endpoint-only sampling collapsed curved rims (2 semicircular edges → zero-area "polygon") and let tiny feature loops win. Ordered tessellation + shoelace on the chained polygon is valid for non-convex rims and selects the true outer rim.

## 6. Core/Cavity Assignment by Reachability (2026-07-30)
**Context**: Normal-voting cannot decide vertical walls, and the "larger visible area = cavity" sign heuristic mislabeled the interiors of both Bosch parts.
**Decision**: Vertical walls are assigned by reachability raycasts (blocked toward the cavity → core-formed); through-holes go to the core (core-pin convention); the pull sign is chosen so the core sits on the side the part's internal features open toward.
**Rationale**: Matches the judges' cap example exactly ("even the internal surface … will be formed by the core"); validated on Part 1, Part 2, a GrabCAD cup holder, and synthetic ground-truth parts.

## 7. Direction Ranking & Sweep Performance (2026-07-30)
**Context**: Bosch guidance: rank candidate directions by undercut AREA (not count). Full sweeps took ~30 s on the Phase 2 part — too slow for a live demo.
**Decision**: Area-first ranking with count as tie-break; branch-and-bound pruning (biggest faces first, abort an axis once its area exceeds the incumbent best); winner verdicts snapshotted and only trapped-suspect faces re-checked at full resolution. Pruned candidates are displayed as lower bounds (≥ N), never as exact values.
**Rationale**: 2× speedup (Part 2: 29 s → 14 s) with byte-identical verdicts, and honest reporting.
