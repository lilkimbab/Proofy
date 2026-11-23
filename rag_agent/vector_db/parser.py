import hashlib
import logging
import os
from pathlib import Path

import fitz
import pymupdf4llm
from docx import Document
from dotenv import load_dotenv

from .ocr import get_ocr_provider
from .utils import timed

logger = logging.getLogger(__name__)

load_dotenv()

IMAGE_STORE_PATH = os.getenv("IMAGE_STORE_PATH", "./image_store")


def _image_dir(file_path: str) -> Path:
    """파일 경로 기반 이미지 저장 디렉토리.
    같은 stem 의 서로 다른 파일이 page_i.png 를 덮어쓰는 충돌을 방지하기 위해
    file_path sha1 의 앞 8자를 stem 뒤에 붙여 격리한다.
    """
    file_stem = Path(file_path).stem
    path_hash = hashlib.sha1(file_path.encode("utf-8")).hexdigest()[:8]
    return Path(IMAGE_STORE_PATH) / f"{file_stem}_{path_hash}"


_MIN_DRAWING_COUNT = int(os.getenv("MIN_DRAWING_COUNT", 5))
_MIN_DRAWING_AREA_RATIO = float(os.getenv("MIN_DRAWING_AREA_RATIO", 0.10))
# get_images() 튜플의 index 2=width, 3=height (픽셀 단위 고유 해상도).
# 두 변 모두 이 값 이상이어야 의미 있는 이미지로 판단한다.
_IMAGE_MIN_EDGE = int(os.getenv("IMAGE_MIN_EDGE", 32))
# 크롭 면적이 페이지 면적의 이 비율 미만이면 장식용 소형 이미지로 판단해 스킵한다.
_CROP_MIN_AREA_RATIO = float(os.getenv("CROP_MIN_AREA_RATIO", 0.02))
# 크롭 bbox가 표 bbox와 이 비율 이상 겹치면 표 내부 이미지로 판단해 스킵한다.
_CROP_TABLE_OVERLAP_THRESHOLD = float(os.getenv("CROP_TABLE_OVERLAP_THRESHOLD", 0.70))
# 두 raster rect 사이의 거리(pt)가 이 값 이하면 같은 figure로 묶는다.
_RASTER_CLUSTER_GAP_PT = float(os.getenv("RASTER_CLUSTER_GAP_PT", 20.0))
# 벡터 드로잉 crop 시 text label 누락 방지용 패딩 (포인트)
_VECTOR_CROP_PADDING_PT = float(os.getenv("VECTOR_CROP_PADDING_PT", 8.0))
# 벡터 드로잉 2단계 super-clustering 갭: fine 클러스터 union bbox끼리 이 거리 이내면 동일 figure로 묶음
_VECTOR_SUPER_CLUSTER_GAP_PT = float(os.getenv("VECTOR_SUPER_CLUSTER_GAP_PT", 200.0))
# fine 클러스터의 면적이 페이지의 이 비율 미만이면 장식 요소로 판단해 super-clustering 제외
# 0.0005(0.05%): 막대그래프 개별 막대(~0.07%)는 통과, 점·hairline(<0.01%)은 제외
# super-cluster 단계의 _should_skip_crop(2%)이 최종 걸름망 역할을 한다
_VECTOR_MIN_CLUSTER_AREA_RATIO = float(os.getenv("VECTOR_MIN_CLUSTER_AREA_RATIO", 0.0005))
# figure bbox 텍스트 확장: 이 거리 이내의 word를 반복 흡수 (body text와의 여백이 이보다 크면 자동 중단)
_VECTOR_TEXT_GAP_PT = float(os.getenv("VECTOR_TEXT_GAP_PT", 15.0))

# 스캔 페이지 감지: 텍스트가 이 글자 수 미만이면서 대형 래스터가 있으면 스캔으로 판단
_OCR_SCANNED_TEXT_THRESHOLD = int(os.getenv("OCR_SCANNED_TEXT_THRESHOLD", 50))
# 페이지 면적 대비 이 비율 이상을 차지하는 래스터가 있으면 스캔 페이지 후보
_OCR_SCANNED_COVERAGE_RATIO = float(os.getenv("OCR_SCANNED_COVERAGE_RATIO", 0.5))
# OCR용 렌더링 해상도 배율 (2.0 = 144dpi, 일반 텍스트 인식에 충분)
_OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", 2.0))


# ---------------------------------------------------------------------------
# Raster rect 클러스터링 헬퍼
# ---------------------------------------------------------------------------

def _rect_gap(r1: fitz.Rect, r2: fitz.Rect) -> float:
    """두 rect 사이의 Chebyshev 거리. 겹치거나 맞닿으면 0."""
    dx = max(0.0, max(r1.x0, r2.x0) - min(r1.x1, r2.x1))
    dy = max(0.0, max(r1.y0, r2.y0) - min(r1.y1, r2.y1))
    return max(dx, dy)


def _cluster_rects(rects: list[fitz.Rect], gap: float) -> list[list[fitz.Rect]]:
    """gap(pt) 이하로 가까운 rect들을 Union-Find로 연결 컴포넌트 클러스터링."""
    n = len(rects)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if _rect_gap(rects[i], rects[j]) <= gap:
                parent[find(i)] = find(j)

    clusters: dict[int, list[fitz.Rect]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(rects[i])
    return list(clusters.values())


def _union_rect(rects: list[fitz.Rect]) -> fitz.Rect:
    """여러 rect의 union bounding box."""
    return fitz.Rect(
        min(r.x0 for r in rects),
        min(r.y0 for r in rects),
        max(r.x1 for r in rects),
        max(r.y1 for r in rects),
    )


# ---------------------------------------------------------------------------
# 핵심 파이프라인: 후보 rect 수집 → 클러스터링 → 유효 crop rect 목록
# ---------------------------------------------------------------------------

def _collect_candidate_rects(page: fitz.Page) -> list[fitz.Rect]:
    """페이지에서 픽셀 해상도 필터를 통과한 raster 이미지의 렌더링 rect 목록."""
    candidates: list[fitz.Rect] = []
    for img in page.get_images():
        if img[2] < _IMAGE_MIN_EDGE or img[3] < _IMAGE_MIN_EDGE:
            continue
        try:
            rects = page.get_image_rects(img[0])
        except Exception:
            continue
        for rect in rects:
            if not rect.is_empty and rect.width > 0 and rect.height > 0:
                candidates.append(rect)
    return candidates


def _get_valid_cluster_rects(page: fitz.Page) -> list[fitz.Rect]:
    """클러스터링 후 필터를 통과한 union bbox 목록.

    _has_significant_visuals()와 _crop_raster_images() 양쪽이 이 함수를
    공유하므로 "감지는 True인데 crop 결과가 빈 리스트"인 불일치가 발생하지 않는다.
    """
    candidates = _collect_candidate_rects(page)
    if not candidates:
        return []
    clusters = _cluster_rects(candidates, _RASTER_CLUSTER_GAP_PT)
    valid: list[fitz.Rect] = []
    for cluster in clusters:
        union = _union_rect(cluster)
        if not _should_skip_crop(union, page):
            valid.append(union)
    return valid


# ---------------------------------------------------------------------------
# 시각 요소 감지 / 필터
# ---------------------------------------------------------------------------

def _has_significant_visuals(page: fitz.Page) -> bool:
    """유효한 raster 클러스터 또는 의미 있는 벡터 드로잉이 존재하는지 판단.

    raster 판단은 _get_valid_cluster_rects()와 동일 파이프라인을 사용해
    감지 결과와 실제 crop 결과가 항상 일치하도록 보장한다.
    """
    if _get_valid_cluster_rects(page):
        return True
    drawings = page.get_drawings()
    if len(drawings) < _MIN_DRAWING_COUNT:
        return False
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False
    xs = [d["rect"].x0 for d in drawings] + [d["rect"].x1 for d in drawings]
    ys = [d["rect"].y0 for d in drawings] + [d["rect"].y1 for d in drawings]
    union_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    return (union_area / page_area) >= _MIN_DRAWING_AREA_RATIO


def _should_skip_crop(rect: fitz.Rect, page: fitz.Page) -> bool:
    """크롭 영역을 스킵해야 하는지 판단.

    스킵 조건 1: 면적이 페이지의 CROP_MIN_AREA_RATIO 미만 — 로고·아이콘 등 장식 요소.
    스킵 조건 2: 표 bbox와 CROP_TABLE_OVERLAP_THRESHOLD 이상 겹침 — 표 내부 래스터.
    """
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return True
    crop_area = rect.width * rect.height
    if crop_area <= 0 or crop_area / page_area < _CROP_MIN_AREA_RATIO:
        return True
    try:
        for table in page.find_tables().tables:
            inter = rect & fitz.Rect(table.bbox)
            if inter.is_empty:
                continue
            inter_area = inter.width * inter.height
            if inter_area / crop_area >= _CROP_TABLE_OVERLAP_THRESHOLD:
                return True
    except Exception:
        pass
    return False


def _expand_figure_bbox_with_text(page: fitz.Page, bbox: fitz.Rect, gap: float) -> fitz.Rect:
    """drawing 기반 figure bbox를 근처 텍스트 word를 반복 흡수해 확장한다.

    figure 내부 라벨(수식, 노드 이름 등)은 drawing bbox에 인접해 있으므로 gap pt 이내에서
    자연스럽게 흡수된다. body text 단락은 figure 아래/위에 여백을 두고 배치되므로 gap보다
    멀어지는 시점에서 자동으로 확장이 멈춘다.

    안전장치: 확장 후 bbox 면적이 페이지의 75%를 초과하면 해당 word는 건너뛴다.
    """
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    if page_area == 0:
        return bbox

    current = fitz.Rect(bbox)
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)

    for _ in range(20):  # 수렴할 때까지 반복 (보통 2~3회면 충분)
        changed = False
        for w in words:
            wr = fitz.Rect(w[0], w[1], w[2], w[3])
            if _rect_gap(current, wr) > gap:
                continue
            new = current | wr
            if new == current:
                continue
            if page_area > 0 and new.width * new.height / page_area > 0.75:
                continue  # 페이지 대부분을 차지하면 body text일 가능성 높음
            current = new
            changed = True
        if not changed:
            break

    return current


def _crop_vector_drawings(page: fitz.Page, img_dir: Path, page_idx: int) -> list[str]:
    """벡터 드로잉을 2단계 클러스터링으로 crop 저장. 유효한 경로 목록 반환.

    1단계(fine, 20pt): 개별 path rect를 묶어 tight 클러스터 형성.
    2단계(super, 200pt): fine 클러스터의 union bbox끼리 묶어 '하나의 figure' 단위로 그룹화.
    → 트리 다이어그램처럼 원소가 넓게 분산된 figure도 하나의 crop으로 묶인다.

    각 super-cluster union은 _VECTOR_CROP_PADDING_PT만큼 확장해 텍스트 레이블 누락 방지.
    """
    drawings = page.get_drawings()
    if not drawings:
        return []

    # is_empty=True인 zero-width/zero-height 선(트리 가지, 축 등)도 포함한다.
    # 이 선들이 클러스터를 연결하는 핵심 역할을 하므로 point rect(w=0, h=0)만 제외.
    rects = [fitz.Rect(d["rect"]) for d in drawings
             if fitz.Rect(d["rect"]).width > 0 or fitz.Rect(d["rect"]).height > 0]
    if not rects:
        return []

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height

    # 1단계: fine clustering으로 tight 원소 그룹화
    fine_clusters = _cluster_rects(rects, _RASTER_CLUSTER_GAP_PT)

    # fine 클러스터 union bbox 중 장식 요소(0.5% 미만)를 제외한 것만 수집
    significant_union_rects: list[fitz.Rect] = []
    for cluster in fine_clusters:
        union = _union_rect(cluster)
        if page_area > 0 and union.width * union.height / page_area >= _VECTOR_MIN_CLUSTER_AREA_RATIO:
            significant_union_rects.append(union)

    if not significant_union_rects:
        return []

    # 2단계: super-clustering — 분산된 figure 원소들을 하나의 figure bbox로 합산
    super_clusters = _cluster_rects(significant_union_rects, _VECTOR_SUPER_CLUSTER_GAP_PT)

    paths: list[str] = []
    img_dir.mkdir(parents=True, exist_ok=True)

    for super_cluster in super_clusters:
        union = _union_rect(super_cluster)
        # 1) 초기 패딩 (drawing bbox 경계 margin)
        padded = fitz.Rect(
            max(union.x0 - _VECTOR_CROP_PADDING_PT, page_rect.x0),
            max(union.y0 - _VECTOR_CROP_PADDING_PT, page_rect.y0),
            min(union.x1 + _VECTOR_CROP_PADDING_PT, page_rect.x1),
            min(union.y1 + _VECTOR_CROP_PADDING_PT, page_rect.y1),
        )
        # 2) figure 내부 텍스트 라벨(수식, 노드명 등)까지 bbox 확장
        #    body text 단락은 figure와의 여백이 _VECTOR_TEXT_GAP_PT보다 크므로 자동 제외
        padded = _expand_figure_bbox_with_text(page, padded, _VECTOR_TEXT_GAP_PT)
        # 3) 페이지 경계 재적용
        padded = fitz.Rect(
            max(padded.x0, page_rect.x0),
            max(padded.y0, page_rect.y0),
            min(padded.x1, page_rect.x1),
            min(padded.y1, page_rect.y1),
        )
        if _should_skip_crop(padded, page):
            continue
        crop_path = str(img_dir / f"page_{page_idx}_vcrop_{len(paths)}.png")
        try:
            pix = page.get_pixmap(clip=padded)
            pix.save(crop_path)
            paths.append(crop_path)
        except Exception:
            continue
    return paths


# ---------------------------------------------------------------------------
# 스캔 페이지 감지 / OCR 렌더링
# ---------------------------------------------------------------------------

def _is_scanned_page(page: fitz.Page, text: str) -> bool:
    """텍스트가 임계값 미만이고 페이지 면적의 대부분을 차지하는 래스터가 있으면 스캔 페이지."""
    if len(text.strip()) >= _OCR_SCANNED_TEXT_THRESHOLD:
        return False
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False
    for img in page.get_images():
        if img[2] < _IMAGE_MIN_EDGE or img[3] < _IMAGE_MIN_EDGE:
            continue
        try:
            for rect in page.get_image_rects(img[0]):
                if not rect.is_empty and rect.width * rect.height / page_area >= _OCR_SCANNED_COVERAGE_RATIO:
                    return True
        except Exception:
            continue
    return False


def _render_page_for_ocr(page: fitz.Page, img_dir: Path, page_idx: int) -> str:
    """OCR용 고해상도 전체 페이지 PNG 렌더링. 경로 반환."""
    mat = fitz.Matrix(_OCR_RENDER_SCALE, _OCR_RENDER_SCALE)
    pix = page.get_pixmap(matrix=mat)
    img_dir.mkdir(parents=True, exist_ok=True)
    path = str(img_dir / f"page_{page_idx}_ocr.png")
    pix.save(path)
    return path


# ---------------------------------------------------------------------------
# Crop 실행
# ---------------------------------------------------------------------------

def _crop_raster_images(page: fitz.Page, img_dir: Path, page_idx: int) -> list[str]:
    """클러스터 union bbox 단위로 crop 저장. 유효한 경로 목록 반환."""
    valid_rects = _get_valid_cluster_rects(page)
    if not valid_rects:
        return []
    paths: list[str] = []
    img_dir.mkdir(parents=True, exist_ok=True)
    for rect in valid_rects:
        crop_path = str(img_dir / f"page_{page_idx}_crop_{len(paths)}.png")
        try:
            pix = page.get_pixmap(clip=rect)
            pix.save(crop_path)
            paths.append(crop_path)
        except Exception:
            continue
    return paths


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str) -> list[dict]:
    file_name = os.path.basename(file_path)
    img_dir = _image_dir(file_path)
    doc = fitz.open(file_path)
    results = []
    with timed(f"parse_pdf {file_name} ({len(doc)}p)", logger, logging.INFO):
        for i in range(len(doc)):
            page = doc[i]
            text = pymupdf4llm.to_markdown(doc, pages=[i], use_ocr=False)
            if _is_scanned_page(page, text):
                with timed(f"page_{i} ocr", logger, logging.INFO):
                    ocr_path = _render_page_for_ocr(page, img_dir, i)
                    text = get_ocr_provider().ocr(ocr_path)
                results.append({"text": text, "page": i, "file_name": file_name, "image_paths": [ocr_path]})
            elif _has_significant_visuals(page):
                with timed(f"page_{i} raster_crop", logger):
                    crops = _crop_raster_images(page, img_dir, i)
                if not crops:
                    # 벡터 드로잉만 있는 경우: 드로잉 영역 클러스터 crop 시도
                    with timed(f"page_{i} vector_crop", logger):
                        crops = _crop_vector_drawings(page, img_dir, i)
                if not crops:
                    # 최종 폴백: 전체 페이지 PNG
                    mat = fitz.Matrix(1.0, 1.0)
                    pix = page.get_pixmap(matrix=mat)
                    img_dir.mkdir(parents=True, exist_ok=True)
                    full_path = str(img_dir / f"page_{i}.png")
                    pix.save(full_path)
                    crops = [full_path]
                results.append({"text": text.strip(), "page": i, "file_name": file_name, "image_paths": crops})
            else:
                results.append({"text": text, "page": i, "file_name": file_name, "image_paths": []})
        _annotate_source_type(results)
    return results


def parse_docx(file_path: str) -> list[dict]:
    file_name = os.path.basename(file_path)
    document = Document(file_path)
    text = "\n".join(p.text for p in document.paragraphs)
    results = [{"text": text, "page": 0, "file_name": file_name, "image_paths": []}]
    _annotate_source_type(results)
    return results


def parse_txt(file_path: str) -> list[dict]:
    file_name = os.path.basename(file_path)
    with open(file_path, encoding="utf-8") as f:
        text = f.read()
    results = [{"text": text, "page": 0, "file_name": file_name, "image_paths": []}]
    _annotate_source_type(results)
    return results


def _detect_source_type(parsed_docs: list[dict]) -> str:
    """
    문서 전체 통계로 타입 추정. 호출자는 chunker 가 chunk 메타에 부착한다.
    값: "slide" | "textbook" | "code" | "general"
    """
    if not parsed_docs:
        return "general"
    pages = [d for d in parsed_docs if (d.get("text") or "").strip()]
    if not pages:
        return "general"

    avg_text_len = sum(len(d["text"]) for d in pages) / len(pages)
    has_code = any("```" in (d.get("text") or "") for d in pages)
    image_ratio = sum(1 for d in parsed_docs if d.get("image_paths")) / len(parsed_docs)

    if has_code and avg_text_len < 1000:
        return "code"
    if image_ratio >= 0.5 or avg_text_len < 400:
        return "slide"
    if avg_text_len > 1500:
        return "textbook"
    return "general"


def _annotate_source_type(parsed_docs: list[dict]) -> None:
    """parsed_docs 의 모든 항목에 동일한 source_type 을 in-place 부착."""
    src = _detect_source_type(parsed_docs)
    for d in parsed_docs:
        d["source_type"] = src


def parse_file(file_path: str) -> list[dict]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    elif ext == ".txt":
        return parse_txt(file_path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")
