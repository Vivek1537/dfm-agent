# Product Walkthrough

Welcome to the AI-driven DfM Tool. This walkthrough will guide you through the process of analyzing a CAD part for injection molding manufacturability.

## 1. Getting Started
1. Start the backend server by running the FastAPI app (e.g., `uvicorn api:app --reload`).
2. Start the frontend React app (e.g., `npm run dev` in the `frontend/` directory).
3. Open your browser and navigate to the frontend URL (typically `http://localhost:5173`).

## 2. Uploading a Part
1. On the left sidebar, click the **Upload New Part** button.
2. Select a `.stp` or `.step` file from your local machine.
3. The backend will automatically begin processing the file. You will see a loading state while the raycasting and geometric analysis occurs.

## 3. Reviewing the Metrics
Once the analysis is complete, the left sidebar will populate with key metrics:
- **Score**: A manufacturability score out of 100. Higher is better.
- **Total Faces**: The number of geometric faces processed.
- **Best Pull Dir**: The optimal mold opening direction discovered by the algorithm (e.g., `Z- axis`).
- **Undercuts**: The number of faces that are physically trapped and cannot be molded without side-actions.
- **Parting Lines**: The number of continuous parting line loops and individual edges separating the core and cavity halves.

Below the metrics, you will find a breakdown of the faces (Core, Cavity, Warning).

## 4. Interacting with the 3D Viewer
The main window displays a premium 3D visualization of your part.
- **Rotate**: Left-click and drag to rotate the model.
- **Pan**: Right-click and drag (or two-finger drag on trackpad) to move the model around the screen.
- **Zoom**: Scroll up or down to zoom in and out.

**Color Legend**:
- **Grey**: Standard core and cavity faces.
- **Red**: Undercut faces (trapped geometry).
- **Cyan**: The parting line wireframe looping around the model.

## 5. Exporting the Results
If you need to share the analysis with your team or a manufacturer:
1. Click the **Download PDF Report** button at the bottom of the left sidebar.
2. The backend will generate a PDF containing the metric breakdown and a static snapshot of the 3D model.
3. The PDF will automatically download to your device.
