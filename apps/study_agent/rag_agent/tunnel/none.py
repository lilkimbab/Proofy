from .base import TunnelBackend


class NoTunnel(TunnelBackend):
    """터널 없이 로컬에서만 서비스 (기본값)."""

    def start(self, port: int) -> str:
        return f"http://localhost:{port}"

    def stop(self) -> None:
        pass
