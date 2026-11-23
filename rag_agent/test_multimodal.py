"""
Multimodal 파이프라인 통합 테스트.
이미지가 포함된 페이지가 PNG로 저장되고, 검색 결과에 base64로 인라인 포함되는지 검증.
"""
import sys, os, tempfile, shutil, base64
sys.path.insert(0, '/home/hykiop/on-tutor/study_agent/rag_agent')

import fitz

tmp_db = tempfile.mkdtemp(prefix="mm_test_db_")
tmp_img = tempfile.mkdtemp(prefix="mm_test_img_")
os.environ["LANCEDB_PATH"] = tmp_db
os.environ["IMAGE_STORE_PATH"] = tmp_img
os.environ.setdefault("EMBED_MODEL", "local")

try:
    # 1. 텍스트 페이지 + 이미지 포함 페이지가 있는 PDF 생성
    tmp_pdf = os.path.join(tmp_db, "test.pdf")
    doc = fitz.open()

    # 페이지 0: 텍스트만
    p0 = doc.new_page()
    p0.insert_text((50, 50), "운영체제는 프로세스를 관리한다. " * 10)

    # 페이지 1: 텍스트 + 이미지 (rect를 이미지로 삽입)
    p1 = doc.new_page()
    p1.insert_text((50, 50), "스케줄링 알고리즘 다이어그램")
    # 작은 PNG 바이트를 직접 삽입하여 get_images()가 감지하게 함
    img_doc = fitz.open()
    img_page = img_doc.new_page(width=100, height=100)
    img_page.draw_rect(fitz.Rect(10, 10, 90, 90), color=(1, 0, 0), fill=(1, 0, 0))
    img_bytes = img_page.get_pixmap().tobytes("png")
    img_doc.close()
    p1.insert_image(fitz.Rect(100, 100, 400, 400), stream=img_bytes)

    doc.save(tmp_pdf)
    doc.close()

    # 2. parse_pdf 확인
    from vector_db.parser import parse_pdf
    parsed = parse_pdf(tmp_pdf)
    assert len(parsed) == 2
    assert parsed[0]["image_path"] is None, "텍스트 전용 페이지는 image_path=None이어야 함"
    assert parsed[1]["image_path"] is not None, "이미지 포함 페이지는 image_path가 있어야 함"
    assert os.path.exists(parsed[1]["image_path"]), "PNG 파일이 실제 존재해야 함"
    print(f"[OK] 이미지 감지 및 저장: {parsed[1]['image_path']}")

    # 3. VectorDB 저장 및 검색
    from vector_db import VectorDBManager
    db = VectorDBManager()
    result = db.add_document(file_path=tmp_pdf, title="test")
    assert result["status"] == "ok"
    print(f"[OK] add_document: {result['chunks_added']} chunks")

    hits = db.search(query="프로세스 관리", title="test", top_k=5)
    assert isinstance(hits, list)
    assert all("image" in h for h in hits), "모든 결과에 image 필드 있어야 함"
    assert all("image_path" not in h for h in hits), "image_path는 외부에 노출되면 안 됨"

    text_hits = [h for h in hits if h["image"] is None]
    image_hits = [h for h in hits if h["image"] is not None]
    print(f"[OK] search: {len(hits)} results ({len(text_hits)} 텍스트, {len(image_hits)} 이미지)")

    if image_hits:
        # base64 디코딩 검증
        decoded = base64.b64decode(image_hits[0]["image"])
        assert decoded[:8] == b'\x89PNG\r\n\x1a\n', "유효한 PNG여야 함"
        print(f"[OK] base64 PNG 검증 완료 ({len(decoded)} bytes)")

    print()
    print("=== MULTIMODAL TEST PASSED ===")

finally:
    shutil.rmtree(tmp_db, ignore_errors=True)
    shutil.rmtree(tmp_img, ignore_errors=True)
