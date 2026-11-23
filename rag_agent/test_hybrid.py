"""
Hybrid Search 통합 테스트.
- FTS 인덱스 자동 생성 확인
- 키워드 직접 검색이 hybrid 에서 살아남는지 확인
- vector / fts / hybrid 모드 전환 동작 확인
"""
import sys, os, tempfile, shutil
sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')

tmp_db = tempfile.mkdtemp(prefix="hybrid_test_db_")
tmp_img = tempfile.mkdtemp(prefix="hybrid_test_img_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ["IMAGE_STORE_PATH"] = tmp_img
os.environ.setdefault("EMBED_MODEL", "local")

try:
    # 충분히 길고 다양한 키워드를 포함한 텍스트 파일들 생성
    docs = {
        "os.txt": (
            "운영체제는 프로세스를 관리한다. 스케줄링 알고리즘에는 FCFS, SJF, RR 이 있다. "
            "페이지 교체 알고리즘으로 LRU, FIFO, Optimal 이 대표적이다. "
            "fork() 시스템 콜은 새로운 프로세스를 생성한다. " * 5
        ),
        "net.txt": (
            "네트워크 계층은 IP 라우팅을 담당한다. TCP 는 신뢰성 있는 전송을 제공한다. "
            "UDP 는 비연결형 프로토콜로 빠른 전송을 우선한다. " * 5
        ),
    }
    tmp_dir = tempfile.mkdtemp(prefix="hybrid_docs_")
    paths = []
    for name, body in docs.items():
        p = os.path.join(tmp_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        paths.append(p)

    from vector_db import VectorDBManager

    # 기본 모드 = hybrid
    os.environ["SEARCH_MODE"] = "hybrid"
    db = VectorDBManager()
    for p in paths:
        r = db.add_document(file_path=p, title="cs")
        assert r["status"] == "ok"

    # 키워드 직접 검색 (FTS 가 강한 영역)
    hits = db.search(query="fork()", title="cs", top_k=5)
    assert len(hits) > 0, "hybrid: fork() 검색 결과 없음"
    assert any("fork()" in h["text"] for h in hits), "hybrid: fork() 가 포함된 chunk 가 상위에 없음"
    print(f"[OK] hybrid: fork() 검색 → {len(hits)} hits")

    # vector only 모드
    os.environ["SEARCH_MODE"] = "vector"
    db_v = VectorDBManager()
    hits_v = db_v.search(query="페이지 교체", title="cs", top_k=3)
    assert len(hits_v) > 0
    print(f"[OK] vector: 페이지 교체 → {len(hits_v)} hits")

    # fts only 모드
    os.environ["SEARCH_MODE"] = "fts"
    db_f = VectorDBManager()
    hits_f = db_f.search(query="LRU", title="cs", top_k=3)
    assert len(hits_f) > 0
    print(f"[OK] fts: LRU → {len(hits_f)} hits")

    print()
    print("=== HYBRID SEARCH TEST PASSED ===")

finally:
    shutil.rmtree(tmp_db, ignore_errors=True)
    shutil.rmtree(tmp_img, ignore_errors=True)
