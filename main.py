"""
Start the KaaS REST API server.

  python main.py
  uvicorn main:app --reload
"""
import uvicorn
from kaas.api.app import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    uvicorn.run("kaas.api.app:app", host="0.0.0.0", port=8000, reload=True)
