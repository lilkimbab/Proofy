import os

from pyngrok import conf, ngrok

from .base import TunnelBackend


class NgrokTunnel(TunnelBackend):
    """pyngrok을 통한 ngrok 터널."""

    def __init__(self) -> None:
        self._tunnel = None
        cfg = conf.get_default()
        auth_token = os.getenv("NGROK_AUTH_TOKEN")
        if auth_token:
            cfg.auth_token = auth_token
        region = os.getenv("NGROK_REGION", "ap")
        cfg.region = region

    def start(self, port: int) -> str:
        self._tunnel = ngrok.connect(port, "http")
        return self._tunnel.public_url

    def stop(self) -> None:
        if self._tunnel:
            ngrok.disconnect(self._tunnel.public_url)
            self._tunnel = None
        ngrok.kill()
