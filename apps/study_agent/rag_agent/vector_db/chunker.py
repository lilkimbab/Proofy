import hashlib
import os
import re
from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter

load_dotenv()

# (?:[A-Z]\.)? 로 부록 번호 형식(Figure A.1, Figure B.4)도 매칭
_EXPLICIT_FIG_RE = re.compile(r'\b(?:Figure|Fig\.?|그림|도표|Table|표)\s*(?:[A-Z]\.)?\d+', re.IGNORECASE)
_IMPLICIT_FIG_RE = re.compile(r'(?:위|아래|다음|이전)\s*(?:그림|트리|그래프|다이어그램|힙|배열|표)')

# chunk의 image_page가 실제 이미지 없는 페이지를 가리킬 때, 이 범위 내 인접 이미지 페이지로 보정
_IMAGE_PAGE_SEARCH_RADIUS = int(os.getenv("IMAGE_PAGE_SEARCH_RADIUS", 5))


def _has_explicit_figure_ref(text: str) -> bool:
    """청크 텍스트에 명시적 그림/표 참조 패턴이 있는지 판별."""
    return bool(_EXPLICIT_FIG_RE.search(text) or _IMPLICIT_FIG_RE.search(text))


def _decide_image_page(doc: dict, chunk_text: str) -> int:
    """청크에 부여할 image_page 결정. -1은 이미지 없음을 의미한다.

    신호 1: 텍스트에 명시적 그림/표 참조 패턴이 있으면 무조건 부여.
    신호 2: 페이지 자체가 시각 중심(image_path 존재 AND 텍스트 < 600자)이면 부여.
    """
    if _has_explicit_figure_ref(chunk_text):
        return doc["page"]
    if doc.get("image_paths") and len((doc.get("text") or "").strip()) < 600:
        return doc["page"]
    return -1


def _build_splitter(chunk_size: int, chunk_overlap: int) -> SentenceSplitter:
    try:
        from mecab import MeCab
        mecab = MeCab()

        def tokenizer_fn(text: str) -> list[str]:
            return [token.surface for token in mecab.parse(text)]

        return SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=tokenizer_fn,
        )
    except ImportError:
        print("[WARNING] mecab not available, using default tokenizer")
        return SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


# 헤더(#, ##, ###...), 표 시작(|), 코드블록(```) 라인을 경계 후보로 인식
_HEADER_RE = re.compile(r"^\s{0,3}(#{1,6})\s+\S", re.MULTILINE)
_HEADER_LINE_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")


def _content_hash(text: str) -> str:
    """chunk 텍스트의 SHA-256. 공백 정규화 후 해싱하여 사소한 trailing whitespace 변화에 안정적."""
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _update_heading_stack(stack: list[tuple[int, str]], header_line: str) -> None:
    """헤더 라인을 보고 stack 을 in-place 갱신. 새 헤더 레벨보다 깊거나 같은 항목은 pop."""
    m = _HEADER_LINE_RE.match(header_line)
    if not m:
        return
    level = len(m.group(1))
    title = m.group(2).strip()
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))


def _block_heading_path(block: str, stack_before: list[tuple[int, str]]) -> list[str]:
    """
    block 시작 시점의 heading 체인을 반환.
    block 자체가 헤더로 시작하면 그 헤더도 path 끝에 포함.
    """
    if block.lstrip().startswith("```"):
        # 코드블록은 직전 헤더 컨텍스트만 유지
        return [t for _, t in stack_before]

    first_line = block.splitlines()[0] if block else ""
    m = _HEADER_LINE_RE.match(first_line)
    if not m:
        return [t for _, t in stack_before]

    level = len(m.group(1))
    title = m.group(2).strip()
    # 시뮬레이션: 이 헤더를 stack 에 적용한 결과를 path 로
    sim = list(stack_before)
    while sim and sim[-1][0] >= level:
        sim.pop()
    sim.append((level, title))
    return [t for _, t in sim]


def _split_by_structure(text: str) -> list[str]:
    """
    markdown 구조(헤더 / 코드블록 / 표) 단위로 1차 분할.
    코드블록은 ``` 사이를 통째로 보존한다.
    """
    if not text or not text.strip():
        return []

    blocks: list[str] = []
    cur: list[str] = []
    in_code = False

    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        # 코드블록은 통째로
        if line.lstrip().startswith("```"):
            if not in_code:
                # 진입: 현재 누적 flush
                if cur:
                    blocks.append("".join(cur))
                    cur = []
                in_code = True
                cur.append(line)
            else:
                # 탈출
                cur.append(line)
                in_code = False
                blocks.append("".join(cur))
                cur = []
            i += 1
            continue

        if in_code:
            cur.append(line)
            i += 1
            continue

        # 헤더 라인은 그 라인부터 새 블록 시작
        if _HEADER_RE.match(line):
            if cur:
                blocks.append("".join(cur))
                cur = []
            cur.append(line)
            i += 1
            continue

        cur.append(line)
        i += 1

    if cur:
        blocks.append("".join(cur))

    return [b for b in blocks if b.strip()]


def _merge_small_blocks(blocks: list[str], min_chars: int) -> list[str]:
    """min_chars 미만의 블록은 인접 블록과 병합."""
    if not blocks:
        return []
    merged: list[str] = []
    buf = ""
    for b in blocks:
        if len(buf) < min_chars:
            buf = (buf + b) if buf else b
        else:
            merged.append(buf)
            buf = b
    if buf:
        if merged and len(buf) < min_chars:
            merged[-1] = merged[-1] + buf
        else:
            merged.append(buf)
    return merged


def _fix_image_pages(chunks: list[dict], parsed_docs: list[dict]) -> None:
    """image_page가 이미지 없는 페이지를 가리키는 chunk를 인접 이미지 페이지로 보정한다.

    _decide_image_page()는 figure 참조 발견 시 chunk 자신의 페이지를 반환하지만,
    실제 figure는 인접 페이지(±RADIUS)에 있는 경우가 많다. 보정 우선순위:
    1) 이미 올바른 이미지 페이지 → 유지
    2) ±RADIUS 내 가장 가까운 이미지 페이지 → 업데이트
    3) 범위 내 이미지 없음 → image_page = -1 (false link 제거)
    """
    # file_name → 이미지가 있는 페이지 번호 sorted list
    img_pages: dict[str, list[int]] = {}
    for d in parsed_docs:
        if d.get("image_paths"):
            img_pages.setdefault(d["file_name"], []).append(d["page"])
    for pages in img_pages.values():
        pages.sort()

    radius = _IMAGE_PAGE_SEARCH_RADIUS
    for chunk in chunks:
        ip = chunk.get("image_page", -1)
        if ip == -1:
            continue
        pages = img_pages.get(chunk["file_name"], [])
        if ip in pages:
            continue  # 이미 정확한 페이지
        best, best_dist = None, radius + 1
        for p in pages:
            dist = abs(p - ip)
            if dist < best_dist:
                best, best_dist = p, dist
        chunk["image_page"] = best if best is not None else -1


def chunk_documents(parsed_docs: list[dict]) -> list[dict]:
    """
    Adaptive chunking:
      1) markdown 구조(헤더/코드블록/표)로 1차 경계 분할
      2) 작은 블록 병합 (MIN_CHUNK_CHARS)
      3) 블록이 chunk_size 를 넘으면 SentenceSplitter 로 2차 분할
    """
    chunk_size = int(os.getenv("CHUNK_SIZE", 512))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", 64))
    min_chars = int(os.getenv("MIN_CHUNK_CHARS", 200))
    structural = os.getenv("CHUNK_STRATEGY", "structural").lower()

    splitter = _build_splitter(chunk_size, chunk_overlap)

    results = []
    chunk_index = 0
    # 한 문서(parsed_docs 리스트 전체)에서 누적되는 heading 컨텍스트
    heading_stack: list[tuple[int, str]] = []

    for doc in parsed_docs:
        text = doc["text"] or ""
        page = doc["page"]
        file_name = doc["file_name"]
        source_type = doc.get("source_type", "general")

        if structural == "fixed":
            primary_blocks = [text] if text.strip() else []
        else:
            blocks = _split_by_structure(text)
            primary_blocks = _merge_small_blocks(blocks, min_chars)

        for block in primary_blocks:
            # block 진입 시점의 heading_path 결정
            heading_path = _block_heading_path(block, heading_stack)
            # block 안의 모든 헤더 라인을 stack 에 적용 (다음 block 의 컨텍스트가 됨)
            if not block.lstrip().startswith("```"):
                for line in block.splitlines():
                    if _HEADER_LINE_RE.match(line):
                        _update_heading_stack(heading_stack, line)

            # 2차 분할: chunk_size 를 넘는 경우만
            sub_chunks = splitter.split_text(block)
            for chunk_text in sub_chunks:
                results.append({
                    "text": chunk_text,
                    "chunk_index": chunk_index,
                    "page": page,
                    "file_name": file_name,
                    "image_page": _decide_image_page(doc, chunk_text),
                    "content_hash": _content_hash(chunk_text),
                    "heading_path": list(heading_path),
                    "source_type": source_type,
                })
                chunk_index += 1

    _fix_image_pages(results, parsed_docs)
    return results
