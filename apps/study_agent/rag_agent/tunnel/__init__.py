from .base import TunnelBackend
from .none import NoTunnel
from .ngrok import NgrokTunnel

_BACKENDS: dict[str, type[TunnelBackend]] = {
    "none": NoTunnel,
    "ngrok": NgrokTunnel,
}


def get_tunnel(backend: str) -> TunnelBackend:
    """
    TUNNEL_BACKEND 환경변수로 백엔드를 선택한다.
    새 터널 방식을 추가할 때는 _BACKENDS에 등록하기만 하면 된다.
    """
    cls = _BACKENDS.get(backend.lower())
    if cls is None:
        supported = ", ".join(_BACKENDS)
        raise ValueError(f"지원하지 않는 터널 백엔드: '{backend}'. 지원 목록: {supported}")
    return cls()
