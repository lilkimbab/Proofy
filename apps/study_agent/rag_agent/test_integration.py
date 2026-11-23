"""
Vector DB 모듈 전체 통합 스모크 테스트.
전체 PASS 시 "=== ALL TESTS PASSED ===" 출력.
"""

import sys, os, tempfile, shutil

sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')

# 임시 LanceDB 경로 (테스트 후 삭제)
tmp_db = tempfile.mkdtemp(prefix="vectordb_test_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ.setdefault("EMBED_MODEL", "local")

from vector_db import VectorDBManager

def make_txt(content: str) -> str:
    """임시 TXT 파일 생성 후 경로 반환"""
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', delete=False, encoding='utf-8'
    )
    f.write(content)
    f.close()
    return f.name


def test_add_and_search():
    print("[TEST 1] add_document + search")
    db = VectorDBManager()
    content = "운영체제는 프로세스를 관리한다. " * 40
    path = make_txt(content)
    try:
        result = db.add_document(file_path=path, title="OS")
        assert result["status"] == "ok", f"status 오류: {result}"
        assert result["chunks_added"] >= 1, "chunk가 하나도 없음"
        print(f"  add_document OK — {result['chunks_added']} chunks")

        hits = db.search(query="프로세스 관리", title="OS", top_k=3)
        assert isinstance(hits, list), "검색 결과가 list가 아님"
        assert len(hits) > 0, "검색 결과가 비어있음"
        assert all("text" in h and "source" in h and "page" in h and "score" in h for h in hits)
        print(f"  search OK — top score={hits[0]['score']:.4f}")
    finally:
        os.unlink(path)


def test_list_titles():
    print("[TEST 2] list_titles")
    db = VectorDBManager()
    titles = db.list_titles()
    assert "OS" in titles, f"'OS'가 없음: {titles}"
    print(f"  list_titles OK — {titles}")


def test_list_files():
    print("[TEST 3] list_files")
    db = VectorDBManager()
    files = db.list_files("OS")
    assert len(files) >= 1, "파일 목록이 비어있음"
    print(f"  list_files OK — {files}")


def test_search_with_filter():
    print("[TEST 4] search with file_name filter")
    db = VectorDBManager()
    files = db.list_files("OS")
    file_name = files[0]
    hits = db.search(
        query="운영체제", title="OS",
        top_k=5, filter={"file_name": file_name}
    )
    assert isinstance(hits, list)
    assert all(h["source"] == file_name for h in hits), "필터가 동작하지 않음"
    print(f"  search with filter OK — {len(hits)} results for '{file_name}'")


def test_delete_file():
    print("[TEST 5] delete_file")
    db = VectorDBManager()
    # 두 번째 파일 추가
    path2 = make_txt("자료구조는 데이터를 효율적으로 저장하는 방법이다. " * 40)
    db.add_document(file_path=path2, title="OS")
    os.unlink(path2)

    files_before = db.list_files("OS")
    assert len(files_before) == 2, f"파일이 2개여야 함: {files_before}"

    db.delete_file(title="OS", file_name=files_before[0])
    files_after = db.list_files("OS")
    assert len(files_after) == 1, f"삭제 후 파일이 1개여야 함: {files_after}"
    print(f"  delete_file OK — {files_before[0]} 삭제됨")


def test_delete_title():
    print("[TEST 6] delete_title")
    db = VectorDBManager()
    db.delete_title("OS")
    titles = db.list_titles()
    assert "OS" not in titles, f"'OS'가 여전히 존재: {titles}"
    print("  delete_title OK")


def test_empty_search():
    print("[TEST 7] search on nonexistent title")
    db = VectorDBManager()
    hits = db.search(query="아무말", title="없는타이틀")
    assert hits == [], f"빈 리스트여야 함: {hits}"
    print("  empty search OK")


if __name__ == "__main__":
    try:
        test_add_and_search()
        test_list_titles()
        test_list_files()
        test_search_with_filter()
        test_delete_file()
        test_delete_title()
        test_empty_search()
        print()
        print("=== ALL TESTS PASSED ===")
    except Exception as e:
        import traceback
        print()
        print("=== TEST FAILED ===")
        traceback.print_exc()
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)
