import streamlit as st
import os
import tempfile

from gui.analyzer import analyze_part
from gui.visualization import create_interactive_3d, create_3d_snapshot
from gui.report import generate_pdf_report

from core.mold_direction import CANDIDATE_DIRECTIONS

# Streamlit App Configuration
st.set_page_config(page_title="DfM Agent Analysis", layout="wide", page_icon="⚙️")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Headers */
    h1, h2, h3 {
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }
    
    /* Metrics Cards */
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        border-color: var(--primary-color);
        box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
    }
    
    /* Metric Labels */
    div[data-testid="stMetricLabel"] > div > div > p {
        font-size: 1.05rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.8;
    }
    
    /* Download Button */
    .stDownloadButton > button {
        background: linear-gradient(135deg, var(--primary-color), #2563eb);
        color: white !important;
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: 600;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: all 0.3s ease;
        width: 100%;
    }
    .stDownloadButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px rgba(0, 0, 0, 0.2);
    }
    
    /* Image Container */
    [data-testid="stImage"] img {
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

st.title("⚙️ AI-driven DfM Tool")
st.markdown("Upload a STEP file of an injection-molded part to detect undercuts, classify faces, and score its manufacturability.")
# Sidebar Configuration
st.sidebar.header("Upload Part")
uploaded_file = st.sidebar.file_uploader("Upload .stp or .step file", type=["stp", "step"])

st.sidebar.header("Advanced Settings")
direction_labels = ["Auto-Detect Best"] + [f"{label} (Direction: {dir})" for dir, label in CANDIDATE_DIRECTIONS]
selected_dir_label = st.sidebar.selectbox("Mold Open Direction", direction_labels)

override_dir = None
if selected_dir_label != "Auto-Detect Best":
    # Extract just the label name (e.g. "Z+")
    just_label = selected_dir_label.split(" (")[0]
    # Find the corresponding tuple
    override_dir = next((d for d, l in CANDIDATE_DIRECTIONS if l == just_label), None)


if uploaded_file is not None:
    st.info(f"Processing **{uploaded_file.name}**...")
    
    # Save the uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_filepath = tmp_file.name

    try:
        # Run DfM Analysis
        with st.spinner("Parsing geometry and running raycast..."):
            result = analyze_part(tmp_filepath, uploaded_file.name, override_direction=override_dir)
        
        st.success("Analysis Complete!")

        # Layout for Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Score", f"{result.manufacturability_score:.1f}/100", 
                    delta="Optimal" if result.manufacturability_score > 90 else "- Needs Design Changes", delta_color="normal")
        col2.metric("Total Faces", result.total_faces)
        
        # Display Best Direction vs Chosen
        if override_dir:
            col3.metric("Pull Direction", selected_dir_label.split(" (")[0])
        else:
            best_label = next((l for d, l in CANDIDATE_DIRECTIONS if d == result.best_mold_direction), str(result.best_mold_direction))
            col3.metric("Best Pull Direction", best_label)
            
        col4.metric("Undercuts", result.undercut_face_count, 
                    delta=f"{result.undercut_face_count} trapped faces", delta_color="inverse")

        # Layout for Face Breakdown & 3D Visualization
        st.markdown("---")
        row1_col1, row1_col2 = st.columns([1, 2])

        with row1_col1:
            st.subheader("Face Breakdown")
            st.markdown(f"- 🟦 **Core Faces:** {result.core_face_count}")
            st.markdown(f"- 🟩 **Cavity Faces:** {result.cavity_face_count}")
            st.markdown(f"- 🟥 **Undercut Faces:** {result.undercut_face_count}")
            st.markdown(f"- 🟨 **Warning (Low Draft):** {result.warning_face_count}")
            
            # Generate Report
            st.markdown("---")
            st.subheader("Export")
            with st.spinner("Generating PDF & 3D Viewer..."):
                snapshot_path = os.path.join(tempfile.gettempdir(), "dfm_snapshot.png")
                report_path = os.path.join(tempfile.gettempdir(), "dfm_report.pdf")
                
                # Generate static PyVista PNG for the PDF
                create_3d_snapshot(result.faces, result.parting_line_edges, snapshot_path)
                
                # Generate the PDF
                generate_pdf_report(result, snapshot_path, report_path)
                
                # Generate interactive Plotly figure for Streamlit
                fig = create_interactive_3d(result.faces, result.parting_line_edges)

                with open(report_path, "rb") as pdf_file:
                    st.download_button(
                        label="📄 Download PDF Report",
                        data=pdf_file,
                        file_name=f"{result.part_name}_DfM_Report.pdf",
                        mime="application/pdf",
                    )

        with row1_col2:
            st.subheader("3D Visualization")
            if fig:
                st.plotly_chart(fig, use_container_width=True, height=500)
            else:
                st.warning("Visualization engine failed to render the 3D snapshot.")

    except Exception as e:
        st.error(f"Error analyzing part: {str(e)}")

    finally:
        # Cleanup temp file
        os.unlink(tmp_filepath)

else:
    st.info("👈 Upload a STEP file in the sidebar to begin analysis.")
