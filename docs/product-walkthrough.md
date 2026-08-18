# Product Walkthrough

Welcome to the AI-driven DfM Tool. This walkthrough will guide you through the process of analyzing a CAD part for injection molding manufacturability.

## 1. Getting Started
1. Windows: double-click `app.bat`. macOS/Linux: run `./app.sh`. Either starts the backend and frontend together.
2. Open your browser and navigate to the frontend URL (typically `http://localhost:5173`).

## 2. Uploading a Part
1. On the left sidebar, click the **Upload New Part** button.
2. Select a `.stp` or `.step` file from your local machine.
3. The backend will automatically begin processing the file. You will see a loading state while the raycasting and geometric analysis occurs.

## 3. Reviewing the Metrics
Once the analysis is complete, the left sidebar will populate with key metrics:
- **Score**: A manufacturability score out of 100. Higher is better.
- **Total Faces**: The number of geometric faces processed.
- **Best Pull Dir**: The optimal mold opening direction discovered by the algorithm (e.g., `Z- axis`).
- **Undercuts**: The number of trapped FEATURES (side-action regions) and the axis they retract on; the raw trapped-face count is shown underneath. Part 3 reads *2 regions on 1 side-action axis · 88 faces*.
- **Main Parting Line**: the single closed loop where core and cavity surfaces meet (planar on both reference parts), with its edge count.
- **Pull direction override**: pick any ranked candidate from the dropdown or type a custom `x,y,z` vector; the whole analysis recomputes for it. *Reset* returns to the auto-detected direction.
- **Side Cores & Lifters**: each undercut region with its mechanism (side-action slider / lifter / collapsible core), retraction axis and area.

Below the metrics, you will find a breakdown of the faces (Core, Cavity, Warning).

## 4. Interacting with the 3D Viewer
The main window displays a premium 3D visualization of your part.
- **Rotate**: Left-click and drag to rotate the model.
- **Pan**: Right-click and drag (or two-finger drag on trackpad) to move the model around the screen.
- **Zoom**: Scroll up or down to zoom in and out.

**Color Legend**:
- **Blue**: Core faces. **Amber/gold**: Cavity faces (toggle *Core* / *Cavity* to explode the halves apart along the pull axis).
- **Red**: Undercut faces (trapped geometry).
- **Orange (Warning)**: low-draft faces — walls at 0° draft; Bosch adds draft later, so these are warnings, not defects.
- **Cyan**: The main parting line looping around the model.

