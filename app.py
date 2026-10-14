"""LEZGi AI — точка входа для веб-сервера и облачного развертывания (Render / Docker)."""

import os
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from lezgi.server import app

if __name__ == "__main__":
    host = os.getenv("HOST", os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"))
    port = int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "8765")))
    uvicorn.run(app, host=host, port=port)
