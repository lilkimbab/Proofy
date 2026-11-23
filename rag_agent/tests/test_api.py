"""
FastAPI 엔드포인트 통합 테스트 — pytest + unittest.TestCase 스타일.

검증:
  - POST /add — 정상 파일 업로드 후 200 + {"status": "accepted"} 반환
  - POST /search — ingest 후 검색 결과에 parent_text, score, source 필드 포함
  - GET /titles — ingest한 title이 목록에 포함
  - DELETE /titles/{title} — 삭제 후 /titles에서 사라짐
  - GET /files/{title} — ingest한 파일명 포함
  - DELETE /files/{title}/{file_name} — 파일 삭제 후 목록에서 사라짐
  - 잘못된 요청 (존재하지 않는 title로 검색) → 200 + 빈 리스트

테스트는 숫자 prefix로 의존 순서를 제어한다 (unittest는 알파벳 순 실행).
"""

import os
import shutil
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_env(tmp_db: str, tmp_img: str, tmp_prof: str) -> dict:
    """환경변수를 설정하고 이전 값을 반환한다."""
    old = {k: os.environ.get(k) for k in [
        "LANCEDB_PATH", "IMAGE_STORE_PATH", "USER_PROFILE_DIR",
        "EMBED_MODEL", "RERANK_ENABLED", "SEARCH_MODE",
    ]}
    os.environ["LANCEDB_PATH"] = tmp_db
    os.environ["IMAGE_STORE_PATH"] = tmp_img
    os.environ["USER_PROFILE_DIR"] = tmp_prof
    os.environ["EMBED_MODEL"] = "local"
    os.environ["RERANK_ENABLED"] = "false"
    os.environ["SEARCH_MODE"] = "hybrid"
    return old


def _restore_env(old: dict) -> None:
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _wait_for_job(client, job_id: str, timeout: float = 90.0) -> dict:
    """job_id의 상태가 done/failed가 될 때까지 폴링한다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200, f"job 조회 실패: {resp.status_code}"
        job = resp.json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.3)
    raise TimeoutError(f"job {job_id}이 {timeout}s 내에 완료되지 않음")


class TestApiEndpoints(unittest.TestCase):
    """
    module-scoped 공유 클라이언트 + 숫자 prefix로 실행 순서를 보장한다.
    setUpClass에서 앱과 클라이언트를 초기화하고 tearDownClass에서 정리한다.
    """

    TITLE = "api_test_title"

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp_db = tempfile.mkdtemp(prefix="api_db_")
        cls.tmp_img = tempfile.mkdtemp(prefix="api_img_")
        cls.tmp_prof = tempfile.mkdtemp(prefix="api_prof_")
        cls.tmp_docs = tempfile.mkdtemp(prefix="api_docs_")

        cls._old_env = _setup_env(cls.tmp_db, cls.tmp_img, cls.tmp_prof)

        from fastapi.testclient import TestClient
        from api.main import app
        cls._test_client_ctx = TestClient(app)
        cls.client = cls._test_client_ctx.__enter__()

        # 테스트용 문서 파일 준비
        cls.sample_path = os.path.join(cls.tmp_docs, "sample.txt")
        with open(cls.sample_path, "w", encoding="utf-8") as f:
            f.write(
                "운영체제는 프로세스를 관리한다. 스케줄링 알고리즘에는 FCFS, SJF, RR 이 있다. "
                "페이지 교체 알고리즘으로 LRU, FIFO 가 있다. " * 20
            )

    @classmethod
    def tearDownClass(cls):
        cls._test_client_ctx.__exit__(None, None, None)
        _restore_env(cls._old_env)
        shutil.rmtree(cls.tmp_db, ignore_errors=True)
        shutil.rmtree(cls.tmp_img, ignore_errors=True)
        shutil.rmtree(cls.tmp_prof, ignore_errors=True)
        shutil.rmtree(cls.tmp_docs, ignore_errors=True)

    # ── 1. POST /add ──────────────────────────────────────────────────────────

    def test_1_add_document_accepted(self):
        """POST /add — 정상 파일 업로드 후 status=accepted와 job_id 반환."""
        with open(self.sample_path, "rb") as f:
            resp = self.client.post(
                "/add",
                files={"file": ("sample.txt", f, "text/plain")},
                data={"title": self.TITLE},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "accepted")
        self.assertIn("job_id", body)
        self.assertIn("parents", body)

        job = _wait_for_job(self.client, body["job_id"])
        self.assertEqual(job["status"], "done", f"job 실패: {job}")
        self.assertGreater(job["chunks_added"], 0)

    # ── 2. GET /titles ────────────────────────────────────────────────────────

    def test_2_titles_contains_ingested_title(self):
        """GET /titles — ingest한 title이 목록에 포함된다."""
        resp = self.client.get("/titles")
        self.assertEqual(resp.status_code, 200)
        titles = resp.json()["titles"]
        self.assertIn(self.TITLE, titles)

    # ── 3. GET /files/{title} ─────────────────────────────────────────────────

    def test_3_files_contains_uploaded_filename(self):
        """GET /files/{title} — 업로드한 파일명이 목록에 포함된다."""
        resp = self.client.get(f"/files/{self.TITLE}")
        self.assertEqual(resp.status_code, 200)
        files = resp.json()["files"]
        self.assertIn("sample.txt", files)

    # ── 4. POST /search ───────────────────────────────────────────────────────

    def test_4a_search_returns_required_fields(self):
        """POST /search — 결과에 parent_text, score, source 필드 포함."""
        resp = self.client.post("/search", json={
            "query": "운영체제 프로세스",
            "title": self.TITLE,
            "top_k": 3,
        })
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("parent_text", r)
            self.assertIn("score", r)
            self.assertIn("source", r)

    def test_4b_search_score_descending(self):
        """검색 결과 score가 내림차순이어야 한다."""
        resp = self.client.post("/search", json={
            "query": "스케줄링 알고리즘",
            "title": self.TITLE,
            "top_k": 5,
        })
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        if len(results) >= 2:
            scores = [r["score"] for r in results]
            self.assertEqual(scores, sorted(scores, reverse=True),
                             f"score 내림차순 미보장: {scores}")

    def test_4c_search_top_k_respected(self):
        """top_k=2 요청 시 2개 이하가 반환되어야 한다."""
        resp = self.client.post("/search", json={
            "query": "LRU 페이지 교체",
            "title": self.TITLE,
            "top_k": 2,
        })
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertLessEqual(len(results), 2)

    def test_4d_search_nonexistent_title_returns_empty(self):
        """존재하지 않는 title로 검색 시 200 + 빈 리스트가 반환되어야 한다."""
        resp = self.client.post("/search", json={
            "query": "아무 쿼리",
            "title": "존재하지않는타이틀_xyz",
            "top_k": 5,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    # ── 5. POST /reload ───────────────────────────────────────────────────────

    def test_5_reload_returns_config(self):
        """POST /reload — 200 + config dict 반환."""
        resp = self.client.post("/reload")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("config", body)
        self.assertIn("search_mode", body["config"])

    # ── 6. GET /jobs/{job_id} ─────────────────────────────────────────────────

    def test_6_job_status_not_found(self):
        """존재하지 않는 job_id 조회 시 404가 반환되어야 한다."""
        resp = self.client.get("/jobs/nonexistent-job-id-xyz")
        self.assertEqual(resp.status_code, 404)

    # ── 7. DELETE /files/{title}/{file_name} ──────────────────────────────────

    def test_7_delete_file_removes_from_list(self):
        """DELETE /files/{title}/{file_name} — 삭제 후 /files에서 사라진다."""
        second_path = os.path.join(self.tmp_docs, "second.txt")
        with open(second_path, "w", encoding="utf-8") as f:
            f.write("두 번째 문서입니다. 자료구조와 알고리즘. " * 20)

        with open(second_path, "rb") as f:
            add_resp = self.client.post(
                "/add",
                files={"file": ("second.txt", f, "text/plain")},
                data={"title": self.TITLE},
            )
        self.assertEqual(add_resp.status_code, 200)
        _wait_for_job(self.client, add_resp.json()["job_id"])

        files_before = self.client.get(f"/files/{self.TITLE}").json()["files"]
        self.assertIn("second.txt", files_before)

        del_resp = self.client.delete(f"/files/{self.TITLE}/second.txt")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["status"], "ok")

        files_after = self.client.get(f"/files/{self.TITLE}").json()["files"]
        self.assertNotIn("second.txt", files_after)

    # ── 8. DELETE /titles/{title} ─────────────────────────────────────────────

    def test_8_delete_title_removes_from_list(self):
        """DELETE /titles/{title} — 삭제 후 /titles에서 사라진다."""
        resp = self.client.delete(f"/titles/{self.TITLE}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

        titles = self.client.get("/titles").json()["titles"]
        self.assertNotIn(self.TITLE, titles)
