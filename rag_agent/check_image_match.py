"""
chunk-image 매칭 진단 스크립트.
add 작업 완료 후 실행해 4단계 검증 결과를 출력한다.

실행:
    python check_image_match.py                        # 전체 타이틀 자동 감지
    python check_image_match.py "Introduction to Algorithms"  # 타이틀 직접 지정
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from vector_db.store import VectorStore

# chunker.py와 동일한 패턴
_EXPLICIT_FIG_RE = re.compile(r'\b(?:Figure|Fig\.?|그림|도표|Table|표)\s*\d+', re.IGNORECASE)
_IMPLICIT_FIG_RE = re.compile(r'(?:위|아래|다음|이전)\s*(?:그림|트리|그래프|다이어그램|힙|배열|표)')

def _has_figure_ref(text: str) -> bool:
    return bool(_EXPLICIT_FIG_RE.search(text) or _IMPLICIT_FIG_RE.search(text))


def _crop_type(path: str) -> str:
    name = Path(path).name
    if re.search(r'page_\d+_vcrop_\d+', name):
        return "vcrop"
    if re.search(r'page_\d+_crop_\d+', name):
        return "raster_crop"
    if re.match(r'page_\d+\.png$', name):
        return "full_page"
    return "unknown"


def run(title: str) -> None:
    store = VectorStore()

    # ── 데이터 로드 ──────────────────────────────────────────────
    chunks = store.get_all_rows(title)
    if not chunks:
        print(f"[ERROR] '{title}' 테이블이 비어있거나 존재하지 않습니다.")
        return

    # page_images 테이블 전체 로드
    pi_table_name = f"pageimg_{title.encode('utf-8').hex()}"
    db_path = os.getenv("LANCEDB_PATH", "./lancedb_store")
    import lancedb
    db = lancedb.connect(db_path)
    if pi_table_name not in db.list_tables().tables:
        print(f"[ERROR] page_images 테이블 없음: {pi_table_name}")
        pi_rows = []
    else:
        pi_rows = db.open_table(pi_table_name).to_arrow().to_pylist()

    # (file_name, page) → [image_path, ...] 인덱스
    pi_index: dict[tuple[str, int], list[str]] = {}
    for r in pi_rows:
        key = (r["file_name"], r["page"])
        pi_index.setdefault(key, []).append(r["image_path"])

    print(f"\n{'='*60}")
    print(f"  진단 대상: {title}")
    print(f"  총 chunk: {len(chunks):,}개  |  page_images 레코드: {len(pi_rows):,}개")
    print(f"{'='*60}\n")

    # ── 1단계: 링크 유효성 (orphan) ──────────────────────────────
    linked_chunks = [c for c in chunks if c.get("image_page", -1) != -1]
    orphan_no_pi = []    # page_images에 레코드 없음
    orphan_no_file = []  # 레코드는 있지만 파일 없음

    for c in linked_chunks:
        key = (c["file_name"], c["image_page"])
        paths = pi_index.get(key)
        if not paths:
            orphan_no_pi.append(c)
        else:
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                orphan_no_file.append({"chunk": c, "missing_files": missing})

    print("[ 1단계 ] 링크 유효성")
    print(f"  image_page != -1 인 chunk : {len(linked_chunks):,}개")
    print(f"  page_images 레코드 없음   : {len(orphan_no_pi):,}개  ", end="")
    print("← 정상" if not orphan_no_pi else "<-- 주의")
    print(f"  파일 누락 (경로만 존재)   : {len(orphan_no_file):,}개  ", end="")
    print("← 정상" if not orphan_no_file else "<-- 주의")
    if orphan_no_pi:
        for c in orphan_no_pi[:5]:
            print(f"    page={c['page']} image_page={c['image_page']} file={c['file_name']}")
        if len(orphan_no_pi) > 5:
            print(f"    ... 외 {len(orphan_no_pi)-5}건")
    if orphan_no_file:
        for item in orphan_no_file[:3]:
            print(f"    {item['missing_files']}")

    # ── 2단계: 누락 연결 (false negative) ────────────────────────
    has_ref_linked = 0
    has_ref_unlinked = []

    for c in chunks:
        if _has_figure_ref(c.get("text", "")):
            if c.get("image_page", -1) != -1:
                has_ref_linked += 1
            else:
                has_ref_unlinked.append(c)

    total_with_ref = has_ref_linked + len(has_ref_unlinked)
    miss_rate = len(has_ref_unlinked) / total_with_ref * 100 if total_with_ref else 0

    print(f"\n[ 2단계 ] 누락 연결 (figure 참조 있는데 image_page=-1)")
    print(f"  figure 참조 chunk 합계  : {total_with_ref:,}개")
    print(f"  image_page 연결됨       : {has_ref_linked:,}개")
    print(f"  image_page 미연결 (miss): {len(has_ref_unlinked):,}개  →  miss율 {miss_rate:.1f}%")
    if has_ref_unlinked:
        print("  미연결 샘플 (최대 5개):")
        for c in has_ref_unlinked[:5]:
            snippet = c["text"][:120].replace("\n", " ")
            print(f"    page={c['page']} | {snippet}")

    # ── 3단계: crop 품질 ──────────────────────────────────────────
    type_counts: dict[str, int] = {"vcrop": 0, "raster_crop": 0, "full_page": 0, "unknown": 0}
    for paths in pi_index.values():
        for p in paths:
            type_counts[_crop_type(p)] += 1

    total_images = sum(type_counts.values())
    print(f"\n[ 3단계 ] crop 품질 ({total_images}개 이미지)")
    for label, key, good in [
        ("벡터 crop (vcrop) ", "vcrop",       True),
        ("래스터 crop       ", "raster_crop",  True),
        ("full-page 폴백    ", "full_page",    False),
        ("분류 불가         ", "unknown",      False),
    ]:
        cnt = type_counts[key]
        pct = cnt / total_images * 100 if total_images else 0
        flag = "← 정상" if good or cnt == 0 else "<-- 폴백 잔존"
        print(f"  {label}: {cnt:4d}개 ({pct:5.1f}%)  {flag}")

    # full-page 페이지 번호 목록
    full_page_pages = sorted({
        int(re.search(r'page_(\d+)', Path(p).name).group(1))
        for paths in pi_index.values() for p in paths
        if _crop_type(p) == "full_page"
    })
    if full_page_pages:
        pages_str = ", ".join(map(str, full_page_pages[:20]))
        suffix = f"... 외 {len(full_page_pages)-20}개" if len(full_page_pages) > 20 else ""
        print(f"  full-page 페이지: {pages_str}{suffix}")

    # ── 4단계: 고아 이미지 ────────────────────────────────────────
    # chunk에서 한 번도 참조되지 않는 (file_name, page) 조합
    referenced_keys = {(c["file_name"], c["image_page"])
                       for c in chunks if c.get("image_page", -1) != -1}
    orphan_image_keys = [k for k in pi_index if k not in referenced_keys]

    print(f"\n[ 4단계 ] 고아 이미지 (이미지는 있지만 어떤 chunk도 참조 안 함)")
    print(f"  page_images 고유 (file,page) : {len(pi_index):,}개")
    print(f"  chunk에서 참조되는 키        : {len(referenced_keys):,}개")
    print(f"  고아 키                      : {len(orphan_image_keys):,}개  ", end="")
    print("← 정상" if not orphan_image_keys else "<-- 커버리지 개선 여지")
    if orphan_image_keys:
        sample = sorted(orphan_image_keys, key=lambda k: k[1])[:10]
        for fn, pg in sample:
            paths = pi_index[(fn, pg)]
            types = "/".join(sorted({_crop_type(p) for p in paths}))
            print(f"    page={pg:4d}  [{types}]  {Path(fn).name}")
        if len(orphan_image_keys) > 10:
            print(f"    ... 외 {len(orphan_image_keys)-10}개")

    # ── 종합 요약 ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  종합 요약")
    print(f"{'='*60}")
    proper_crop_pct = (type_counts["vcrop"] + type_counts["raster_crop"]) / total_images * 100 if total_images else 0
    print(f"  정상 crop 비율  : {proper_crop_pct:.1f}%  (vcrop + raster_crop)")
    print(f"  figure 매칭률   : {100-miss_rate:.1f}%  (figure 참조 chunk 기준)")
    print(f"  고아 이미지     : {len(orphan_image_keys)}개")
    print(f"  orphan chunk    : {len(orphan_no_pi) + len(orphan_no_file)}개")
    print()


if __name__ == "__main__":
    store = VectorStore()
    titles = store.list_tables()

    if sys.argv[1:]:
        title = sys.argv[1]
    elif len(titles) == 1:
        title = titles[0]
    elif titles:
        print("사용 가능한 타이틀:")
        for i, t in enumerate(titles):
            print(f"  [{i}] {t}")
        idx = input("번호 선택: ").strip()
        title = titles[int(idx)]
    else:
        print("[ERROR] DB에 타이틀이 없습니다. add 작업이 완료됐는지 확인하세요.")
        sys.exit(1)

    run(title)
