# DfM Agent Methodology

This document outlines the algorithms and methodology used to perform automated Design for Manufacturability (DfM) analysis on 3D CAD files (.stp).

## 1. Geometry Extraction and Parsing
Using the OpenCASCADE (OCP) kernel via CadQuery, the system loads the `.stp` file and extracts the exact `TopoDS_Shape`. The B-Rep (Boundary Representation) is traversed to extract each `TopoDS_Face`. For every face, we compute:
- **Surface Area**: Using `BRepGProp` for precise mass property evaluation.
- **Surface Normal**: Extracted using `GeomLProp_SLProps` at the UV midpoint of the underlying parameterized surface.

## 2. Automated Mold Direction Detection
To find the optimal mold pulling direction (Core/Cavity separation axis), the system evaluates 12 candidate vectors (e.g., Z+, X-, X+Y-).
For each candidate vector:
- A physical **Raycast Test** is performed across the entire geometry.
- If a ray fired from a face in the pull direction hits another part of the geometry, that face is strictly trapped (an **Undercut**).
- The candidate direction that minimizes the total undercut area is automatically selected as the **Optimal Mold Direction**.

## 3. Face Classification
Once the mold direction is determined (or overridden by the user), every face is classified mathematically:
- **Undercut (Red)**: Failed the raycast test (trapped geometry).
- **Warning (Yellow)**: The draft angle (angle between the face normal and mold direction) is less than 0.5 degrees, posing a risk of friction during ejection.
- **Cavity (Green)**: The dot product of the surface normal and the pull direction is positive.
- **Core (Blue)**: The dot product is negative.

## 4. Parting Line Extraction
The main parting line is the topological boundary separating the Core half of the mold from the Cavity half.
- Using `TopExp.MapShapesAndAncestors`, we map every `TopoDS_Edge` in the raw CAD solid to its adjacent faces.
- We filter for edges that are shared by exactly two faces.
- By cross-referencing these faces with our classification data, we extract only the edges where one adjacent face is classified as `Core` and the other as `Cavity`.
- These edges perfectly trace the main parting line and are tessellated and rendered as glowing cyan tubes in the 3D viewer.

## 5. Scoring and Visualization
A weighted manufacturability score (0-100) is calculated based on the ratio of undercut and low-draft area to the total surface area. The final geometry is tessellated and rendered via a standalone `vtk.js` HTML wrapper (PyVista), allowing for interactive 3D inspection directly within the web dashboard.
