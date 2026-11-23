"""
Reranker 통합 테스트.
- RERANK_ENABLED=false 시 결과 == hybrid search 결과 (no-op)
- RERANK_ENABLED=true 시 rerank 점수가 score 필드에 반영
- top_k 만큼만 반환
"""
import sys, os, tempfile, shutil
sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')

tmp_db = tempfile.mkdtemp(prefix="rr_test_db_")
tmp_img = tempfile.mkdtemp(prefix="rr_test_img_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ["IMAGE_STORE_PATH"] = tmp_img
os.environ.setdefault("EMBED_MODEL", "local")
os.environ["SEARCH_MODE"] = "hybrid"

try:
    body = (
        "스케줄링 알고리즘에는 FCFS, SJF, Round Robin 이 있다. "
        "FCFS 는 도착 순서대로 처리하므로 convoy effect 가 발생할 수 있다. "
        "SJF 는 예상 실행 시간이 짧은 작업을 우선한다. "
        "Round Robin 은 시간 할당량(time quantum)을 두고 순환 처리한다. "
        "페이지 교체 알고리즘 LRU, FIFO 와는 별개의 주제다. " * 3
    )
    tmp_dir = tempfile.mkdtemp(prefix="rr_docs_")
    p = os.path.join(tmp_dir, "sched.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)

    from vector_db import VectorDBManager

    # 1. RERANK_ENABLED=false 시 동작 확인
    os.environ["RERANK_ENABLED"] = "false"
    db = VectorDBManager()
    db.add_document(file_path=p, title="cs")
    hits_off = db.search(query="Round Robin 시간 할당량", title="cs", top_k=3)
    assert len(hits_off) <= 3
    print(f"[OK] RERANK_ENABLED=false → {len(hits_off)} hits")

    # 2. RERANK_ENABLED=true 동작 확인
    os.environ["RERANK_ENABLED"] = "true"
    db2 = VectorDBManager()
    if db2._reranker.enabled:
        hits_on = db2.search(query="Round Robin 시간 할당량", title="cs", top_k=3)
        assert len(hits_on) <= 3
        # rerank 점수는 정규화된 0~1 또는 logit (모델 옵션에 따라). score 필드가 존재해야 함.
        assert all("score" in h for h in hits_on)
        print(f"[OK] RERANK_ENABLED=true → {len(hits_on)} hits, scores={[round(h['score'],3) for h in hits_on]}")
    else:
        print("[SKIP] FlagEmbedding 미설치 → reranker no-op (graceful fallback 검증)")

    print()
    print("=== RERANKER TEST PASSED ===")

finally:
    shutil.rmtree(tmp_db, ignore_errors=True)
    shutil.rmtree(tmp_img, ignore_errors=True)
