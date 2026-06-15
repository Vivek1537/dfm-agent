import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from core.models import AnalysisResult

def generate_pdf_report(result: AnalysisResult, image_path: str, output_pdf: str = "assets/dfm_report.pdf"):
    """
    Generates a PDF report containing the analysis results and 3D visualization.
    """
    c = canvas.Canvas(output_pdf, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 50, f"DfM Analysis Report")
    
    # Subtitle
    c.setFont("Helvetica", 14)
    c.drawString(50, height - 80, f"Part Name: {result.part_name}")
    
    # Overview metrics
    c.setFont("Helvetica", 12)
    y_pos = height - 120
    c.drawString(50, y_pos, f"Overall Manufacturability Score: {result.manufacturability_score:.1f}/100")
    c.drawString(50, y_pos - 20, f"Total Faces: {result.total_faces}")
    c.drawString(50, y_pos - 40, f"Best Mold Direction: {result.best_mold_direction}")
    
    # Face Breakdown
    y_pos -= 80
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y_pos, "Face Breakdown by Classification")
    c.setFont("Helvetica", 12)
    c.drawString(50, y_pos - 20, f"Core Faces: {result.core_face_count}")
    c.drawString(50, y_pos - 40, f"Cavity Faces: {result.cavity_face_count}")
    c.drawString(50, y_pos - 60, f"Undercut Faces (Trapped): {result.undercut_face_count}")
    c.drawString(50, y_pos - 80, f"Warning Faces (Low Draft): {result.warning_face_count}")
    
    # Include Image
    if os.path.exists(image_path):
        # Place image on the lower half of the page
        c.drawImage(image_path, 50, 100, width=500, preserveAspectRatio=True, mask='auto')
    
    c.showPage()
    c.save()
    
    return output_pdf
