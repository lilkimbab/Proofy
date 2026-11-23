import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from dotenv import load_dotenv

from tunnel import get_tunnel

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    tunnel_backend = os.getenv("TUNNEL_BACKEND", "none")

    tunnel = get_tunnel(tunnel_backend)
    public_url = tunnel.start(port)
    print(f"[server] public URL: {public_url}")

    try:
        uvicorn.run("api.main:app", host=host, port=port, reload=False)
    finally:
        tunnel.stop()
