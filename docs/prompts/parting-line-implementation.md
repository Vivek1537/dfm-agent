# Build a Geometry-Driven Parting Line Generation System

You are working inside an existing DFM / injection-molding analysis codebase.

Your task is to **inspect the existing architecture and implement or refactor the parting-line generation pipeline**.

Do not blindly rewrite the project. First understand the current geometry representation, CAD kernel/library, existing draft analysis, undercut logic, face/edge data structures, visualization pipeline, and API contracts.

---

# 1. Core Problem

The current parting-line logic must **not** work by simply:

1. finding arbitrary candidate edges,
2. selecting an edge because of its orientation,
3. coloring that edge as the parting line.

That approach is geometrically unreliable.

The correct objective is:

> Given a 3D solid and one or more possible mold opening directions, determine the mold pull direction that minimizes or eliminates undercuts, classify the geometry into core-side and cavity-side regions, and derive the parting line from the boundary separating those regions.

The system must be geometry-driven rather than edge-driven.

The desired pipeline is:

```text
CAD Solid
    │
    ▼
Geometry Analysis
    │
    ▼
Generate Candidate Pull Directions
    │
    ▼
Evaluate Mold Accessibility
    │
    ├── Detect Undercuts
    ├── Measure Undercut Severity
    └── Classify Accessible Regions
    │
    ▼
Optimize / Select Pull Direction
    │
    ▼
Classify Faces into Core / Cavity / Neutral
    │
    ▼
Extract Boundaries Between Mold Regions
    │
    ▼
Trace Connected Edge Chains
    │
    ▼
Generate Closed 3D Parting Loops
    │
    ▼
Validate
    │
    ├── Closedness
    ├── Continuity
    ├── Undercut Reduction
    └── Manufacturability
    │
    ▼
Visualization + API Result
```

---

# 2. First: Inspect the Existing Codebase

Before changing anything:

1. Inspect the project structure.

2. Identify:
   - CAD geometry kernel/library.
   - Solid, face, edge, wire, shell, and normal representations.
   - Existing draft analysis implementation.
   - Existing undercut detection implementation, if any.
   - Existing parting-line generation code.
   - Existing visualization/coloring logic.
   - Existing API response models.
   - Existing tests.

3. Produce a concise implementation plan before making major changes.

Do not introduce a second geometry abstraction if the existing project already has one.

Reuse existing infrastructure wherever possible.

---

# 3. Define the Pull Direction Model

The algorithm must not assume that a fixed global axis such as +X, +Y, or +Z is always correct.

Create or reuse a pull-direction representation:

```python
@dataclass
class PullDirection:
    vector: Vector3D
    source: str
    score: float | None = None
```

The actual types should follow the project's existing conventions.

Generate candidate directions from meaningful geometric information.

At minimum consider:

```text
Global axes:
+X, -X
+Y, -Y
+Z, -Z
```

Also inspect whether the existing geometry allows extraction of:

- principal axes,
- dominant planar face normals,
- cylindrical/conical axes,
- dominant geometric directions.

If practical, add these as additional candidate directions.

Normalize and deduplicate directions.

Important:

`+D` and `-D` may represent the same mold axis with opposite core/cavity assignment, so avoid redundant evaluation unless the implementation requires evaluating orientation separately.

---

# 4. Undercut Detection Must Drive the Optimization

This is the most important part of the implementation.

For each candidate pull direction `D`, determine whether every region of the part can be released along either `+D` or `-D`.

Do not define undercuts using only:

```python
dot(face_normal, D)
```

because face normal alone is insufficient for concave or occluded geometry.

Use a geometry/accessibility-based method compatible with the existing CAD kernel.

The conceptual requirement is:

For a given pull direction:

1. Project or sample the part perpendicular to `D`.
2. For each relevant projected region, inspect geometry along the pull axis.
3. Determine whether geometry blocks another region from being removed along the pull direction.
4. Detect re-entrant or trapped regions that require:
   - side action,
   - slider,
   - lifter,
   - or another non-straight-pull mechanism.

The implementation method may depend on the CAD kernel.

Possible approaches include:

### Preferred approach

Use geometric visibility / ray intersection analysis.

For sampled points or face regions:

```text
Sample point
    │
    ▼
Cast along +D and -D
    │
    ▼
Find intersections with the solid
    │
    ├── Accessible from +D
    ├── Accessible from -D
    └── Blocked / undercut / ambiguous
```

For a solid projected onto the plane perpendicular to `D`, analyze intersection intervals along the pull axis.

A simple conceptual model:

```text
Projection cell (u, v)
        │
        ▼
Line parallel to D
        │
        ▼
Find all intersections with solid
        │
        ▼
Analyze entry/exit intervals
```

A simple convex region may have one continuous interval.

Multiple separated or problematic intervals can indicate:

- re-entrant geometry,
- occluded geometry,
- internal cavity,
- possible undercut.

Do not assume that every multiple intersection is automatically an undercut. Account for the actual solid topology and distinguish intended through-holes or internal cavities where possible.

If exact continuous analysis is expensive, implement an adaptive sampling strategy with configurable resolution.

---

# 5. Undercut Scoring

For every candidate pull direction, calculate a score.

The optimization priority must be lexicographic or heavily weighted:

```text
Priority 1: Minimize undercut existence/count
Priority 2: Minimize undercut area/severity
Priority 3: Maximize accessibility
Priority 4: Prefer simpler parting topology
Priority 5: Prefer shorter / cleaner parting loops
```

Do not allow a shorter parting line to beat a direction with significantly fewer undercuts.

Conceptually:

```python
def evaluate_pull_direction(shape, direction):
    undercut_result = detect_undercuts(shape, direction)

    parting_complexity = estimate_parting_complexity(
        shape,
        direction,
        undercut_result
    )

    return DirectionEvaluation(
        direction=direction,
        undercut_count=...,
        undercut_area=...,
        undercut_severity=...,
        accessibility=...,
        complexity=...,
        score=...
    )
```

Prefer a structured result object over loose dictionaries.

The final score should make it effectively impossible for:

```text
Direction A:
0 undercuts

to lose to

Direction B:
many undercuts but a slightly shorter parting line
```

Use explicit weights or lexicographic comparison.

Document the reasoning.

---

# 6. Select the Best Pull Direction

Evaluate every candidate.

Then select the best direction.

Conceptually:

```python
evaluations = [
    evaluate_pull_direction(shape, direction)
    for direction in candidate_directions
]

best = min(
    evaluations,
    key=direction_sort_key
)
```

The selection must be deterministic.

If multiple directions are essentially equivalent:

1. prefer lower undercut area,
2. prefer simpler parting topology,
3. prefer a direction aligned with a dominant geometric axis,
4. use a deterministic final tie-breaker.

Return all candidate evaluations for debugging if appropriate.

This is important for explainability.

Example:

```json
{
  "selected_pull_direction": [0, 0, 1],
  "candidates": [
    {
      "direction": [0, 0, 1],
      "undercut_area": 0.0,
      "score": 0.92
    },
    {
      "direction": [1, 0, 0],
      "undercut_area": 142.5,
      "score": 0.37
    }
  ]
}
```

Adapt this to the existing project's response schema rather than introducing unnecessary API changes.

---

# 7. Classify Geometry into Core and Cavity Regions

After selecting the pull axis `D`, classify geometry according to mold accessibility.

Do not use only raw face normals as the final classifier.

Face normals can provide an initial classification:

```python
alignment = dot(face_normal, D)
```

Conceptually:

```text
alignment > +epsilon
    → likely one mold side

alignment < -epsilon
    → likely opposite mold side

abs(alignment) <= epsilon
    → neutral / near-parting / side wall
```

However, the final classification must be consistent with accessibility.

Create a structured classification such as:

```python
class MoldRegion(Enum):
    CORE = "core"
    CAVITY = "cavity"
    NEUTRAL = "neutral"
    UNDERCUT = "undercut"
    AMBIGUOUS = "ambiguous"
```

For each face or relevant surface region, determine:

```text
Accessible along +D?
Accessible along -D?

+ only  → one mold half
- only  → opposite mold half
both    → ambiguous / neutral / requires topology resolution
neither → undercut
```

Use topology propagation where necessary so that connected regions receive consistent assignments.

Avoid isolated noisy classifications caused by small fillets or numerical tolerances.

---

# 8. Derive the Parting Line from Region Boundaries

This is the critical conceptual change.

Do not start with:

```text
Find candidate edge
```

Instead:

```text
CORE REGION
    │
    ├── shared boundary
    │
CAVITY REGION
```

The parting line is derived from the boundary between regions belonging to opposite mold halves.

For every topological edge:

1. Find its adjacent faces.
2. Determine their mold-region classifications.
3. Mark the edge as a candidate if it separates:
   - CORE and CAVITY,
   - or a valid transition through a neutral/near-parting region.

Conceptually:

```python
def is_parting_candidate(edge):
    adjacent = get_adjacent_faces(edge)

    if separates_core_and_cavity(adjacent):
        return True

    if valid_neutral_transition(adjacent):
        return True

    return False
```

Be robust to:

- boundary edges,
- non-manifold edges,
- seams,
- periodic surfaces,
- fillets,
- small sliver faces.

Use configurable geometric tolerances.

---

# 9. Build Continuous Closed Parting Loops

A valid parting line must not simply be:

```text
edge_1
edge_7
edge_12
```

It must be represented as ordered connected geometry.

Build an edge connectivity graph:

```text
Vertex
  │
  ├── Edge A
  ├── Edge B
  └── Edge C
```

Then:

1. connect candidate edges using shared vertices,
2. traverse connected components,
3. order edges into wires/loops,
4. merge geometrically continuous segments where appropriate,
5. detect open chains,
6. detect closed loops.

Conceptually:

```python
def build_parting_loops(candidate_edges):
    graph = build_edge_graph(candidate_edges)

    loops = []

    for component in connected_components(graph):
        ordered_path = trace_component(component)

        if is_closed(ordered_path):
            loops.append(ordered_path)

    return loops
```

The implementation must handle reversed edge orientation correctly.

Do not rely only on edge index order.

---

# 10. Projection / Silhouette Assistance

For difficult geometry, use the silhouette relative to the selected pull direction as an additional signal.

Conceptually:

```text
3D Solid
    │
    │ project along pull direction
    ▼
2D silhouette
    │
    ▼
Outer boundary / visible transitions
    │
    ▼
Map back to corresponding 3D topology
```

The silhouette should not blindly replace topological region classification.

Instead use it to:

- validate candidate boundaries,
- reject internal edges that are not true mold separation boundaries,
- identify outer parting contours,
- assist with ambiguous neutral surfaces.

For a normal two-plate mold, the primary parting line should generally correspond to a continuous boundary separating the geometry that releases to opposite mold halves.

---

# 11. Handle Undercuts Explicitly

If the selected pull direction still produces undercuts, do not silently pretend that a normal parting line solves them.

Return them explicitly.

Example:

```python
@dataclass
class UndercutRegion:
    faces: list[Face]
    area: float
    direction: Vector3D | None
    severity: float
    suggested_action: str
```

Suggested actions can initially be:

```text
NONE
SLIDER_REQUIRED
LIFTER_REQUIRED
SIDE_ACTION_REQUIRED
MANUAL_REVIEW
```

Only assign a specific mechanism when there is enough geometric evidence.

Otherwise use:

```text
MANUAL_REVIEW
```

The parting-line system must distinguish:

```text
Valid straight-pull geometry
```

from:

```text
Geometry that fundamentally requires side actions
```

A parting line cannot magically eliminate a true undercut.

The optimizer should find the pull direction that minimizes undercuts, but it must report unavoidable undercuts honestly.

---

# 12. Parting Line Validation

Implement a validation stage.

Each generated parting result should be checked for:

### A. Topological validity

```text
✓ Connected
✓ Correct edge ordering
✓ Closed loop where required
✓ No broken chains
```

### B. Geometric validity

```text
✓ Lies on the solid boundary
✓ No arbitrary floating segments
✓ No duplicate overlapping segments
✓ No tiny numerical artifacts
```

### C. Mold validity

```text
✓ Separates core and cavity regions
✓ Consistent with selected pull direction
✓ Does not unnecessarily cross unrelated visible faces
✓ Minimizes or eliminates straight-pull undercuts
```

### D. Quality metrics

Calculate:

```text
parting_line_length
number_of_loops
number_of_open_chains
number_of_branch_points
undercut_area_remaining
classification_confidence
```

Create an overall confidence score, but do not hide failure conditions behind a high score.

Example:

```python
@dataclass
class PartingLineResult:
    pull_direction: Vector3D
    loops: list[PartingLoop]
    undercuts: list[UndercutRegion]
    validation: ValidationResult
    confidence: float
```

Adapt names to the existing architecture if equivalent structures already exist.

---

# 13. Visualization Requirements

Integrate with the existing viewer instead of creating a separate visualization system.

Display:

```text
Selected pull direction
    → visible arrow/vector

Core-side geometry
    → existing visualization mechanism

Cavity-side geometry
    → existing visualization mechanism

Parting line
    → clearly highlighted continuous curve/edge loop

Undercut regions
    → visually distinguishable
```

Most importantly:

**Do not visualize a disconnected collection of edges and call it a parting line.**

The viewer should receive ordered loops/wires.

If the current renderer only supports individual edges, preserve compatibility but also add loop metadata so the frontend can render a continuous polyline/curve.

---

# 14. Numerical Robustness

CAD geometry is noisy.

Add centralized tolerances rather than scattering magic numbers.

Examples:

```python
ANGULAR_TOLERANCE = ...
LINEAR_TOLERANCE = ...
EDGE_MATCH_TOLERANCE = ...
CLASSIFICATION_EPSILON = ...
```

Prefer existing project tolerance configuration if present.

Handle:

- nearly parallel faces,
- nearly perpendicular faces,
- tiny sliver faces,
- fillets,
- chamfers,
- cylindrical surfaces,
- periodic surfaces,
- floating-point errors.

Do not classify geometry based on exact equality.

---

# 15. Performance

The implementation should be suitable for practical CAD parts.

Avoid:

```text
O(number_of_faces × number_of_faces)
```

operations where unnecessary.

For ray/sampling analysis:

- use adaptive resolution,
- cache repeated geometric queries,
- use bounding boxes or spatial acceleration structures if available in the CAD kernel,
- make expensive analysis configurable.

Provide:

```python
AnalysisConfig(
    sampling_resolution=...,
    angular_tolerance=...,
    max_candidate_directions=...,
    ...
)
```

Reuse existing configuration patterns.

---

# 16. Suggested Module Architecture

Adapt this to the current repository instead of forcing this exact folder structure:

```text
parting/
├── analyzer.py
│   └── High-level orchestration
│
├── pull_direction.py
│   ├── candidate generation
│   ├── direction normalization
│   └── scoring
│
├── accessibility.py
│   ├── mold accessibility
│   ├── ray/projection analysis
│   └── visibility checks
│
├── undercut.py
│   ├── undercut detection
│   ├── severity calculation
│   └── undercut regions
│
├── classification.py
│   ├── core/cavity classification
│   └── topology propagation
│
├── boundary.py
│   ├── region boundary extraction
│   └── candidate edge detection
│
├── loop_builder.py
│   ├── edge graph
│   ├── traversal
│   └── closed wire generation
│
├── validation.py
│   └── geometric and mold validation
│
└── models.py
    └── result objects
```

Again:

**Inspect the existing architecture first. Reuse and extend it where possible.**

---

# 17. High-Level Orchestration API

The final flow should conceptually look like:

```python
def analyze_parting_line(shape, config=None):

    geometry = analyze_geometry(shape)

    candidate_directions = generate_candidate_directions(
        geometry
    )

    evaluations = []

    for direction in candidate_directions:

        accessibility = analyze_accessibility(
            shape,
            direction,
            config
        )

        undercuts = detect_undercuts(
            shape,
            direction,
            accessibility,
            config
        )

        evaluations.append(
            evaluate_direction(
                direction,
                accessibility,
                undercuts
            )
        )

    best = select_best_direction(evaluations)

    regions = classify_mold_regions(
        shape,
        best.direction,
        best.accessibility
    )

    candidate_edges = extract_region_boundaries(
        shape,
        regions
    )

    loops = build_parting_loops(
        candidate_edges
    )

    validation = validate_parting_result(
        shape,
        best.direction,
        regions,
        loops,
        best.undercuts
    )

    return PartingLineResult(
        pull_direction=best.direction,
        loops=loops,
        undercuts=best.undercuts,
        validation=validation,
        confidence=calculate_confidence(validation)
    )
```

This is conceptual pseudocode.

Follow the actual codebase's geometry APIs and type system.

---

# 18. Acceptance Criteria

The implementation is successful only if:

### Test 1 — Simple box

A rectangular box should:

```text
- identify a valid principal pull axis,
- have zero undercuts,
- produce a simple continuous parting boundary.
```

### Test 2 — Cylinder / flange

A cylindrical part with a flange should:

```text
- select an appropriate axis,
- produce a closed loop around the relevant separation boundary,
- avoid arbitrary internal edges.
```

### Test 3 — Re-entrant feature

A part containing a true side undercut should:

```text
- detect the undercut,
- not falsely claim that a normal parting line eliminates it,
- report that side action or manual review may be required.
```

### Test 4 — Complex part

For the current test part:

```text
- evaluate multiple pull directions,
- select the direction with minimum undercut severity,
- classify core/cavity geometry consistently,
- generate a continuous ordered parting loop,
- avoid selecting random internal edges,
- expose remaining unavoidable undercuts.
```

---

# 19. Required Tests

Add or update tests for:

```text
✓ candidate direction generation
✓ direction normalization
✓ direction scoring
✓ zero-undercut geometry
✓ obvious undercut geometry
✓ core/cavity classification
✓ adjacent-face boundary detection
✓ edge graph construction
✓ edge orientation
✓ closed-loop detection
✓ open-chain rejection
✓ deterministic direction selection
✓ tolerance edge cases
```

If the repository has CAD fixtures or sample STEP files, use them.

Do not create fake geometry abstractions for tests if the project already has a proper test utility.

---

# 20. Important Non-Goals

Do not:

- rewrite unrelated parts of the DFM system,
- replace the CAD kernel,
- break existing API contracts without a migration,
- introduce heavy dependencies unless necessary,
- assume every part can be manufactured with a simple two-plate mold,
- hide undercuts by forcing a visually plausible line,
- select arbitrary edges just because their normals are perpendicular to the pull direction,
- treat disconnected edge fragments as a finished parting line.

---

# 21. Implementation Strategy

Work in this order:

## Phase 1 — Understand

Inspect:

- current parting-line code,
- geometry data structures,
- draft analysis,
- undercut logic,
- visualization,
- tests.

Report the proposed change plan.

## Phase 2 — Foundation

Implement:

```text
candidate pull directions
→ direction evaluation
→ undercut/accessibility analysis
→ best direction selection
```

Test this before proceeding.

## Phase 3 — Classification

Implement:

```text
accessibility-aware
core/cavity/neutral/undercut classification
```

Test on simple solids.

## Phase 4 — Boundary Extraction

Implement:

```text
adjacent-face analysis
→ candidate boundary edges
→ filtering
```

## Phase 5 — Loop Construction

Implement:

```text
edge connectivity graph
→ ordered traversal
→ closed loops
```

## Phase 6 — Validation

Implement geometric and manufacturing validation.

## Phase 7 — Integration

Connect the result to:

- existing API,
- existing visualization,
- existing DFM analysis output.

---

# 22. Final Deliverable

After implementation, provide a concise report containing:

1. Files changed.
2. Existing architecture reused.
3. New pipeline.
4. How pull direction is selected.
5. How undercuts are detected.
6. How core/cavity classification works.
7. How the parting line is extracted.
8. What validation was added.
9. Tests added and their results.
10. Known limitations.

Also explicitly state:

```text
Can this implementation guarantee zero undercuts?

If no:
- explain whether the limitation is due to part geometry,
- candidate direction search,
- sampling resolution,
- CAD kernel limitations,
- or ambiguity requiring human review.
```

---

# Critical Principle

The implementation must follow this reasoning:

```text
DO NOT:

Part
  ↓
Pick edge
  ↓
Call it parting line


DO:

Part
  ↓
Generate candidate mold pull directions
  ↓
Analyze accessibility
  ↓
Detect undercuts
  ↓
Select the best mold axis
  ↓
Classify core and cavity regions
  ↓
Find boundaries between those regions
  ↓
Trace connected boundaries
  ↓
Validate closed loops
  ↓
Generate the parting line
```

The parting line is therefore an **output of mold accessibility and geometry classification**, not an arbitrary input or edge-selection heuristic.

Prioritize correctness, robustness, deterministic behavior, and integration with the existing DFM codebase over adding a large amount of disconnected new code.
