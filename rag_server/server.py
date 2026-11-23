from __future__ import annotations

import os
import sys

import uvicorn
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ROOT)

load_dotenv()
sys.path.insert(0, os.path.join(REPO_ROOT, "rag_agent"))

from api.main import app  # noqa: E402


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8001))
    uvicorn.run(app, host=host, port=port, reload=False)
