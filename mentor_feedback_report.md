# Mentor Feedback Report: DfM Hackathon (Phase 1 Review)

This report summarizes the key definitions, project review, identified mistakes, and requirements for the next phase of the DfM Hackathon project, based on the mentor's feedback.

## 1. Definitions Explained by the Mentor

The mentor provided clear definitions for fundamental concepts in injection molding design:

*   **Undercut:** Any feature of a part that cannot be released from the mold in the chosen molding direction.
*   **Parting Line (or Parting Curve):** The line or curve where the core and cavity surfaces of a mold meet.
*   **Core Surface:** The internal part of the mold that forms the internal features of the component.
*   **Cavity Surface:** The part of the mold that forms the external features of the component.

## 2. Review of the Current Project Status

The meeting served as the Results Announcement for Phase 1 of the DfM Hackathon. Mentors evaluated solutions from several teams, including Ecliptica, Ahana, Stack, Concier, Mavericks, and Trinity. The evaluation involved testing the submitted code against provided parts and additional parts to assess robustness.

**Key Observations:**

*   **Strengths:** Qualified teams demonstrated proficiency in creating user-friendly Graphical User Interfaces (GUIs) and effective visualizations.
*   **Scoring Criteria:** Teams were ranked based on the following criteria:
    *   Optimal mold direction detection.
    *   Ability to override mold direction.
    *   Main parting line creation.
    *   Core and cavity extraction.
    *   Side core and lifter parting line generation (considered a Level 2 requirement).
    *   Overall quality of the final GUI and visualization.

## 3. What Was Done Wrong (Mistakes)

Several common issues and specific team mistakes were highlighted during the review:

*   **Technical Gaps:** A significant number of teams exhibited a lack of in-depth understanding of mold mechanics, which led to inaccuracies in parting line and undercut detection.
*   **Classification Errors:**
    *   Team **Stack** was noted for incorrectly identifying undercut faces.
    *   Team **Concier** made errors in classifying core surfaces, mistakenly identifying them as both cavity and core.
*   **Suboptimal Solutions:** Most teams failed to identify the 
optimal solution for the provided example (a packaging cap), which would have resulted in zero undercuts.
*   **Logic Issues:** Incorrect classification of surfaces often led to the generation of inaccurate parting lines.

## 4. What Needs to Be Done in the Next Round (Phase 2)

Phase 2 of the hackathon will involve increased complexity and a focus on refinement and robustness:

*   **Increased Complexity:** Teams will be challenged with analyzing a more complex part.
*   **Refinement:** It is crucial for teams to address and rectify the classification and detection issues identified in Phase 1.
*   **Improved Robustness:** The developed software solutions must demonstrate greater robustness to effectively handle a wider variety of geometries.
*   **Mentorship & Q&A:** A dedicated mentorship session will be organized to provide clarification and address any doubts teams may have before the final submission.
*   **Final Presentation:** Teams are required to present their final solutions at the BGSW office.
*   **Individual Participation:** Each team member must be prepared to validate their specific contributions to the project, emphasizing individual accountability.
*   **Strict Timelines:** Adherence to provided deadlines is mandatory, as no extensions will be granted for Phase 2 submissions.
