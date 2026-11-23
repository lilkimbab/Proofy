"""
Embedding 설정의 현재 상태를 표현하는 유틸리티 함수 모음.
실제 stale 감지는 각 row의 db_version 필드로 수행하며 외부 파일에 의존하지 않는다.
"""
import hashlib
import os


def current_db_version() -> str:
    """
    현재 embedding 설정을 8자리 해시로 반환한다.
    EMBED_MODEL 변경 시 자동으로, DB_VERSION 변경 시 수동으로 버전이 갱신된다.

    버전을 올려야 하는 경우:
      - EMBED_MODEL 변경 → 자동 반영
      - 그 외 재임베딩이 필요한 구조적 변경 → .env의 DB_VERSION 값을 올린다 (기본 "1")
    """
    model = os.getenv("EMBED_MODEL", "local").lower()
    user_ver = os.getenv("DB_VERSION", "1")
    raw = f"embed_model={model};ver={user_ver}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]
