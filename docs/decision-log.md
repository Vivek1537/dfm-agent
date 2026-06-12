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
**Decision**: We implemented physical raycasting using OpenCASCADE (`IntCurvesFace_ShapeIntersector`). For each face, a ray is cast from its center in its pulling direction. If it hits another part of the geometry beyond a minimum thickness threshold (2mm), it is flagged as an undercut.
**Rationale**: Simple draft angle checks are insufficient for identifying true undercuts (e.g., internal features that might have positive draft but are blocked from above). Raycasting provides a physical simulation of the mold opening.

## 3. Resolving Raycast Symmetry Issues
**Context**: Perfectly vertical walls (dot product near 0 with the pull direction) were occasionally being flagged as undercuts asymmetrically due to floating point noise (e.g., `+0.0000001` vs `-0.0000001`).
**Decision**: We modified the raycaster logic so that near-perpendicular faces (within ~0.6° of the parting plane) always use a consistent tiebreaker direction.
**Rationale**: This completely eliminates the floating-point sign-bit asymmetry, ensuring that mirrored vertical walls are treated identically and accurately.

## 4. Manufacturability Scoring Formula
**Context**: The initial score formula only penalized undercut *area*. Because of this, changing the pull direction often resulted in identical scores even if the *number* of undercut faces drastically increased.
**Decision**: We updated the scoring formula to penalize both undercut/warning **area** AND undercut/warning **count**.
**Rationale**: A part with 1 large undercut is often easier to fix than a part with 20 small scattered undercuts. Factoring in the face count provides a more nuanced, direction-sensitive manufacturability score.

## 5. Parting Line Identification
**Context**: Finding the optimal parting line for complex 3D shapes.
**Decision**: We implemented an algorithm that analyzes the boundary edges between faces classified as "Core" and "Cavity". The backend extracts these edges, tessellates them into line segments, and groups them into contiguous loops.
**Rationale**: Presenting loops instead of raw edges tells a clearer engineering story to the user, identifying exactly how many distinct feature areas require parting line considerations.
