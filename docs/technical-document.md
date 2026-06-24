# Technical Document

This document outlines the architecture and technical implementation details of the AI-driven DfM Tool.

## 1. System Architecture

The application follows a modern client-server architecture:

### 1.1 Backend (Python / FastAPI)
- **Framework**: FastAPI is used to expose the RESTful endpoint (`/analyze`).
- **Geometry Kernel**: OpenCASCADE (via the `cadquery` wrapper and direct `OCP` bindings). This handles all STEP file parsing, topological operations, and raycasting physics.
- **Role**: The backend receives a STEP file, parses the geometry, executes the DfM algorithms (mold direction search, undercut detection, draft analysis, parting line extraction), and returns a JSON payload containing the analysis results and tessellated geometry data for rendering.

### 1.2 Frontend (React / Vite)
- **Framework**: React.js bundled via Vite.
- **3D Engine**: `three.js` wrapped with `@react-three/fiber` and `@react-three/drei`.
- **Role**: The frontend provides a responsive user interface to upload files, displays the calculated metrics in a sidebar, and renders the 3D geometry and parting lines using the tessellated vertex data provided by the backend.

## 2. Core DfM Algorithms

### 2.1 Mold Opening Direction Optimization
(`core/mold_direction.py`)
To find the optimal direction to open the two mold halves, the system tests 12 candidate directions: the 6 primary cartesian axes (±X, ±Y, ±Z) and 6 diagonal directions. For each direction, it runs the undercut detection algorithm and selects the direction that results in the lowest combination of undercut area and undercut face count.

### 2.2 Physical Raycast Undercut Detection
(`core/undercut_detector.py`)
Determining if a face is trapped requires simulating a physical mold pull.
1. All faces are merged into a single `TopoDS_Compound`.
2. An `IntCurvesFace_ShapeIntersector` is loaded with this compound geometry.
3. For each face, a ray is fired from its center, slightly offset along its outward normal. The ray is fired in the chosen pull direction.
4. If the intersector registers a hit against another part of the geometry, and that hit is beyond a minimum thickness threshold (2.0mm), the face is flagged as a true undercut.
5. **Vertical Walls**: Faces that are near-perpendicular to the pull direction (dot product near 0) use a consistent tiebreaker direction for the raycast. This resolves floating-point asymmetry bugs where mirror-symmetric vertical walls would randomly test opposite directions.

### 2.3 Draft Angle Analysis
(`core/draft_angle.py`)
Each face's draft angle is computed relative to the mold half it belongs to.
- The dot product between the face's outward normal and the pull direction is calculated.
- The absolute value of this dot product is used to compute the angle from the opening vector.
- Faces with a draft angle between 0° and 1° are flagged as "Warning" faces, indicating potential ejection friction.

### 2.4 Parting Line Extraction
(`core/parting_line.py`)
The parting line represents the boundary where the core and cavity mold halves meet.
1. The backend iterates through all edges in the STEP file (`TopoDS_Edge`).
2. For each edge, it identifies the two adjoining faces.
3. If one face is classified as "Core" and the other as "Cavity", the edge is identified as a parting line segment.
4. The backend then tessellates these edges and groups them into contiguous loops to present a clean geometric wireframe to the frontend.

## 3. Manufacturability Scoring
(`core/models.py`)
The `compute_score` function generates a 0-100 score using a penalty-based formula. The formula factors in both the area and the count of problem faces to ensure sensitivity to different design topologies:
- **Undercut Area**: Up to 30 points penalty.
- **Undercut Count**: Up to 20 points penalty.
- **Warning Area**: Up to 15 points penalty.
- **Warning Count**: Up to 5 points penalty.

## 4. API Endpoints
- `POST /analyze`: Accepts a multipart form data file (`.stp` or `.step`). Returns a JSON object containing the `score`, `best_direction`, metrics counts, and a `geometry` object containing tessellated `vertices`, `triangles`, and `parting_lines`.
