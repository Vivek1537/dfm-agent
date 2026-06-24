# Product Document

## Overview
The AI-driven Design for Manufacturing (DfM) Tool is a specialized software application designed to automatically analyze 3D CAD models (STEP files) for injection molding manufacturability. It provides instant, automated feedback on part design, reducing the time and cost associated with manual DfM reviews.

## Target Audience
- **Mechanical Engineers**: To quickly validate their part designs before sending them to tooling.
- **Tooling/Mold Designers**: To rapidly identify potential pain points (undercuts, lack of draft) before beginning the mold design process.
- **Manufacturing Quotation Teams**: To automatically assess the complexity of a part to generate more accurate tooling quotes.

## Key Features

### 1. Automated Undercut Detection
The tool uses a physical raycasting simulation to identify faces that are "trapped" and cannot be cleanly ejected from a two-part mold. By simulating the mold opening process, it accurately detects complex internal undercuts that simple draft-angle checks would miss.

### 2. Optimal Pull Direction Search
The system automatically tests multiple candidate mold opening directions (e.g., Z+, Z-, X+, diagonal vectors) to find the orientation that results in the fewest undercuts and the highest manufacturability score.

### 3. Draft Angle Analysis & Face Classification
Every face on the 3D model is analyzed and classified:
- **Core Faces**: Faces assigned to the core (moving) half of the mold.
- **Cavity Faces**: Faces assigned to the cavity (stationary) half of the mold.
- **Warning Faces**: Faces with a draft angle of less than 1°, indicating potential ejection issues.
- **Undercut Faces**: Faces that are completely trapped.

### 4. Parting Line Generation
The backend extracts the exact boundary edges separating the Core and Cavity faces. These edges are grouped into continuous loops, representing the parting line(s) where the two mold halves will meet. 

### 5. Manufacturability Scoring
A comprehensive score from 0 to 100 is generated based on a weighted penalty formula that considers both the area and the count of undercut and low-draft faces.

### 6. Interactive 3D Visualization
The frontend features a high-fidelity, interactive 3D viewer built with React Three Fiber. Users can rotate, pan, and zoom their model. The faces are color-coded based on their DfM classification (e.g., bright red for undercuts, grey for core/cavity), and the parting line is highlighted with a vivid cyan wireframe.


## Future Roadmap
- Support for complex side-actions (sliders and lifters) in the undercut detection algorithm.
- Wall thickness analysis to detect overly thick/thin sections.
- Multi-cavity layout optimization.
- Native integration with popular CAD software via plugins.
