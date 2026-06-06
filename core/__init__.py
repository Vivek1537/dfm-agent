# core/ — Geometry engine for DfM Auto Parting Line
# Person A owns this entire package.
#
# Imports are lazy to avoid pulling in OCP (heavy C++ bindings) when
# only the pure-Python modules (models, mold_direction, etc.) are needed.
# Use explicit imports:  from core.models import FaceData
#                        from core.step_parser import parse_step
