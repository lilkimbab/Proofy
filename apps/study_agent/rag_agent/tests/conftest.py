import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def make_txt(tmp_path):
    """임시 .txt 파일 생성 callable을 반환한다. tmp_path가 테스트 종료 후 자동 삭제된다."""
    def _make(content: str, name: str = "doc.txt") -> str:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _make


@pytest.fixture
def tmp_db_env(tmp_path):
    """LANCEDB_PATH를 임시 디렉터리로 설정하고 teardown에서 복원한다."""
    db_path = str(tmp_path / "lancedb")
    os.makedirs(db_path, exist_ok=True)
    old = os.environ.get("LANCEDB_PATH")
    os.environ["LANCEDB_PATH"] = db_path
    yield db_path
    if old is None:
        os.environ.pop("LANCEDB_PATH", None)
    else:
        os.environ["LANCEDB_PATH"] = old


@pytest.fixture
def tmp_img_env(tmp_path):
    """IMAGE_STORE_PATH를 임시 디렉터리로 설정하고 teardown에서 복원한다."""
    img_path = str(tmp_path / "images")
    os.makedirs(img_path, exist_ok=True)
    old = os.environ.get("IMAGE_STORE_PATH")
    os.environ["IMAGE_STORE_PATH"] = img_path
    yield img_path
    if old is None:
        os.environ.pop("IMAGE_STORE_PATH", None)
    else:
        os.environ["IMAGE_STORE_PATH"] = old


@pytest.fixture
def tmp_prof_env(tmp_path):
    """USER_PROFILE_DIR를 임시 디렉터리로 설정하고 teardown에서 복원한다."""
    prof_path = str(tmp_path / "profiles")
    os.makedirs(prof_path, exist_ok=True)
    old = os.environ.get("USER_PROFILE_DIR")
    os.environ["USER_PROFILE_DIR"] = prof_path
    yield prof_path
    if old is None:
        os.environ.pop("USER_PROFILE_DIR", None)
    else:
        os.environ["USER_PROFILE_DIR"] = old


@pytest.fixture
def make_db(tmp_db_env, tmp_img_env, tmp_prof_env):
    """EMBED_MODEL=local을 보장하며 새 VectorDBManager 인스턴스를 반환한다."""
    os.environ["EMBED_MODEL"] = "local"
    os.environ["RERANK_ENABLED"] = "false"
    os.environ["SEARCH_MODE"] = "hybrid"
    from vector_db import VectorDBManager
    return VectorDBManager()
