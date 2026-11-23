from __future__ import annotations

from datetime import datetime, timezone
import threading
import uuid

from app.schemas.learning_contents import LearningContentBase


def _new_content_id() -> str:
    return f"content_{uuid.uuid4().hex}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LearningContentRepository:
    """Local repository boundary for generated learning contents.

    The long-term backing store is the team-owned Content DB. This repository
    keeps Phase 14.4 API behavior testable without taking over that storage
    module.
    """

    def __init__(self):
        self._contents: dict[str, LearningContentBase] = {}
        self._lock = threading.Lock()

    def create_many(self, *, user_id: str, contents: list[LearningContentBase]) -> list[LearningContentBase]:
        saved: list[LearningContentBase] = []
        with self._lock:
            for content in contents:
                content_id = content.id or _new_content_id()
                saved_content = content.model_copy(
                    update={
                        "id": content_id,
                        "user_id": user_id,
                        "created_at": content.created_at or _utcnow(),
                    },
                    deep=True,
                )
                self._contents[content_id] = saved_content
                saved.append(saved_content)
        return saved

    def get(self, content_id: str) -> LearningContentBase | None:
        with self._lock:
            content = self._contents.get(content_id)
            if content is None:
                return None
            return content.model_copy(deep=True)
