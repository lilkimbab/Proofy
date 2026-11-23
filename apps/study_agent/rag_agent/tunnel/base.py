from abc import ABC, abstractmethod


class TunnelBackend(ABC):
    @abstractmethod
    def start(self, port: int) -> str:
        """터널을 열고 외부에서 접근 가능한 public URL을 반환한다."""

    @abstractmethod
    def stop(self) -> None:
        """터널을 닫는다."""
