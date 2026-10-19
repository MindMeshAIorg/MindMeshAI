"""MindMesh AI Main Application Entrypoint

FastAPI server runner and entrypoint for MindMesh AI.
Re-exports `app` from `app.py` so running `uvicorn main:app` or `python main.py`
starts the full MindMesh AI platform (dashboard, authentication, chatbot, connectors).
"""
import sys
from pathlib import Path

# Set base project directory
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import app, create_flow, SCOPES

__all__ = ["app", "create_flow", "SCOPES"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
