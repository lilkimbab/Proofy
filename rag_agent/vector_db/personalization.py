import json
import math
import os
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_LOCK = threading.Lock()


def _profile_dir() -> Path:
    p = Path(os.getenv("USER_PROFILE_DIR", "./user_profiles"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _empty_profile(user_id: str) -> dict:
    return {"user_id": user_id, "queries": [], "chunk_signals": {}}


def _load(user_id: str) -> dict:
    f = _profile_dir() / f"{user_id}.json"
    if not f.exists():
        return _empty_profile(user_id)
    try:
        with f.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        # 손상 파일을 덮어쓰기 전에 백업 → 추후 복구 시도 가능
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        corrupt = f.with_suffix(f".corrupt-{ts}.json")
        try:
            os.replace(str(f), str(corrupt))
            print(f"[WARN] 프로파일 손상 감지 ({user_id}): {e}. 백업 → {corrupt.name}")
        except OSError as rename_err:
            print(f"[WARN] 프로파일 손상 ({user_id}) 백업 실패: {rename_err}")
        return _empty_profile(user_id)


def _save(profile: dict) -> None:
    """원자 쓰기: tmp 에 dump → flush+fsync → os.replace 로 교체."""
    f = _profile_dir() / f"{profile['user_id']}.json"
    tmp = f.with_suffix(f".tmp-{os.getpid()}.json")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(str(tmp), str(f))


class PersonalizationStore:
    """
    검색 호출마다 query 를 기록하고, 명시적 feedback (chunk_id, signal) 을 누적한다.
    boost(user_id, title, chunk_id) 는 가중치 곱셈 인자(>=1.0)를 반환.
    """

    def __init__(self):
        self._enabled = os.getenv("PERSONALIZATION_ENABLED", "true").lower() == "true"
        self._max_queries = int(os.getenv("USER_QUERY_HISTORY_MAX", "200"))
        self._view_weight = float(os.getenv("PERSONAL_VIEW_WEIGHT", "0.05"))
        self._useful_weight = float(os.getenv("PERSONAL_USEFUL_WEIGHT", "0.15"))
        self._max_boost = float(os.getenv("PERSONAL_MAX_BOOST", "1.5"))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_query(self, user_id: str, title: str, query: str) -> None:
        if not self._enabled or not user_id:
            return
        with _LOCK:
            prof = _load(user_id)
            prof["queries"].append({
                "query": query,
                "title": title,
                "ts": datetime.utcnow().isoformat(),
            })
            if len(prof["queries"]) > self._max_queries:
                prof["queries"] = prof["queries"][-self._max_queries:]
            _save(prof)

    def record_signal(self, user_id: str, title: str, chunk_id: str,
                      kind: str = "view") -> None:
        """kind: "view" | "useful" """
        if not self._enabled or not user_id or not chunk_id:
            return
        with _LOCK:
            prof = _load(user_id)
            t = prof["chunk_signals"].setdefault(title, {})
            entry = t.setdefault(chunk_id, {"views": 0, "useful": 0})
            if kind == "useful":
                entry["useful"] += 1
            else:
                entry["views"] += 1
            _save(prof)

    def boost(self, user_id: str, title: str, chunk_id: str) -> float:
        if not self._enabled or not user_id:
            return 1.0
        prof = _load(user_id)
        entry = prof.get("chunk_signals", {}).get(title, {}).get(chunk_id)
        if not entry:
            return 1.0
        raw = (
            self._view_weight * math.log1p(entry.get("views", 0))
            + self._useful_weight * math.log1p(entry.get("useful", 0))
        )
        return min(1.0 + raw, self._max_boost)
