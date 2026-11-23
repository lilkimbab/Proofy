"""
4가지 모듈화 개선 사항 통합 스모크 테스트:
  1) pipeline trace
  2) reload_config()
  3) SEARCH_MODE=vector 일 때 FTS 인덱스 생략
  4) SearchPipeline / Stage 가 동작하는지
"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

tmp_db = tempfile.mkdtemp(prefix="modtest_db_")
tmp_img = tempfile.mkdtemp(prefix="modtest_img_")
tmp_prof = tempfile.mkdtemp(prefix="modtest_prof_")
tmp_docs = tempfile.mkdtemp(prefix="modtest_docs_")

os.environ["LANCEDB_PATH"] = tmp_db
os.environ["IMAGE_STORE_PATH"] = tmp_img
os.environ["USER_PROFILE_DIR"] = tmp_prof
os.environ.setdefault("EMBED_MODEL", "local")
os.environ["RERANK_ENABLED"] = "false"      # 테스트 가속 (모델 로드 회피)
os.environ["SEARCH_MODE"] = "hybrid"
os.environ["PERSONALIZATION_ENABLED"] = "true"

try:
    body = (
        "스케줄링 알고리즘에는 FCFS, SJF, RR 이 있다. "
        "페이지 교체 알고리즘으로 LRU, FIFO 가 대표적이다. "
        "fork() 시스템 콜은 프로세스를 복제한다. " * 6
    )
    p = os.path.join(tmp_docs, "doc.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)

    from vector_db import VectorDBManager, SearchPipeline, Stage

    db = VectorDBManager()
    db.add_document(file_path=p, title="cs")

    # ───────────── 1) pipeline trace ─────────────
    hits = db.search(query="페이지 교체", title="cs", top_k=3, user_id="u_test")
    assert len(hits) > 0
    assert all("pipeline" in h for h in hits), "pipeline 필드 없음"
    pipeline = hits[0]["pipeline"]
    assert any(s.startswith("retrieve:") for s in pipeline), f"retrieve stage 누락: {pipeline}"
    assert "personal_boost" in pipeline, f"personal_boost 누락: {pipeline}"
    assert "query_record" in pipeline, f"query_record 누락: {pipeline}"
    # rerank 비활성이므로 trace 에 없어야 함
    assert "rerank" not in pipeline, f"rerank 비활성인데 trace 에 존재: {pipeline}"
    print(f"[OK] #1 pipeline trace: {pipeline}")

    # user_id 미전달 시 personal stage 가 빠져야 함
    hits_anon = db.search(query="LRU", title="cs", top_k=3)
    pl_anon = hits_anon[0]["pipeline"]
    assert "personal_boost" not in pl_anon, f"anon 에 personal_boost: {pl_anon}"
    assert "query_record" not in pl_anon, f"anon 에 query_record: {pl_anon}"
    print(f"[OK] #1 anon trace: {pl_anon}")

    # ───────────── 2) reload_config() ─────────────
    # SEARCH_MODE 를 런타임에 변경하고 reload 호출
    os.environ["SEARCH_MODE"] = "vector"
    cfg = db.reload_config()
    assert cfg["search_mode"] == "vector", f"reload 후 모드 미반영: {cfg}"
    print(f"[OK] #2 reload_config → {cfg}")

    hits_v = db.search(query="페이지 교체", title="cs", top_k=3)
    pl_v = hits_v[0]["pipeline"]
    assert "retrieve:vector" in pl_v, f"vector 모드 미반영: {pl_v}"
    print(f"[OK] #2 vector 모드 동작: {pl_v}")

    # ───────────── 3) SEARCH_MODE=vector 일 때 FTS 인덱스 미생성 ─────────────
    # 새 테이블에 add_document 시 FTS 인덱스가 생성되지 않는지 확인
    p2 = os.path.join(tmp_docs, "doc2.txt")
    with open(p2, "w", encoding="utf-8") as f:
        f.write("새 문서 컨텐츠. " * 30)
    # SEARCH_MODE=vector 상태로 add
    db.add_document(file_path=p2, title="cs_vector_only")

    table = db._store.get_table("cs_vector_only")
    indices = table.list_indices() if hasattr(table, "list_indices") else []
    has_fts = False
    try:
        # LanceDB 버전별 차이가 있어 fts 검색 시도로 검증
        list(table.search("새 문서", query_type="fts").limit(1).to_list())
        has_fts = True
    except Exception:
        has_fts = False
    assert not has_fts, "SEARCH_MODE=vector 인데 FTS 인덱스가 생성됨"
    print("[OK] #3 SEARCH_MODE=vector → FTS 인덱스 생성 안 됨")

    # 명시적 ensure_fts_index 호출 시 생성되어야 함
    rebuilt = db._store.ensure_fts_index("cs_vector_only")
    assert "cs_vector_only" in rebuilt, f"ensure_fts_index 실패: {rebuilt}"
    print(f"[OK] #3 ensure_fts_index 수동 호출 동작: {rebuilt}")

    # ───────────── 4) Pipeline 패턴 ─────────────
    # 커스텀 stage 를 추가해서 단계 확장이 자유로운지 확인
    class TagStage(Stage):
        name = "tag"
        def apply(self, ctx):
            for r in ctx.results:
                r["custom_tag"] = "smoke"
            ctx.trace.append("tag")

    # hybrid 로 다시 돌려놓고
    os.environ["SEARCH_MODE"] = "hybrid"
    db.reload_config()
    db._store.ensure_fts_index("cs")  # vector-only 로 운영했던 cs 도 다시 인덱싱

    db._pipeline.stages.append(TagStage())
    hits_tag = db.search(query="LRU", title="cs", top_k=2, user_id="u_test")
    assert all(h.get("custom_tag") == "smoke" for h in hits_tag), "커스텀 stage 미적용"
    assert "tag" in hits_tag[0]["pipeline"], f"tag stage trace 누락: {hits_tag[0]['pipeline']}"
    print(f"[OK] #4 커스텀 stage 적용: {hits_tag[0]['pipeline']}")

    print()
    print("=== MODULARITY UPGRADE TEST PASSED ===")

finally:
    shutil.rmtree(tmp_db, ignore_errors=True)
    shutil.rmtree(tmp_img, ignore_errors=True)
    shutil.rmtree(tmp_prof, ignore_errors=True)
    shutil.rmtree(tmp_docs, ignore_errors=True)
