import hashlib
import os
from dotenv import load_dotenv

load_dotenv()


def _is_boundary(
    prev: dict,
    curr: dict,
    accumulated_chars: int,
    min_chars: int,
    max_chars: int,
) -> bool:
    prev_hp = prev.get("heading_path") or []
    curr_hp = curr.get("heading_path") or []

    # 1순위: heading_path 변경 → 항상 경계
    if prev_hp != curr_hp:
        return True

    # 2순위: page 변경
    if prev.get("page") != curr.get("page"):
        # heading 없음 → page 자체가 경계
        if not prev_hp:
            return True
        # heading 있지만 충분히 누적됨 → page도 경계로 인정
        if accumulated_chars >= min_chars:
            return True

    # 3순위: 크기 상한 초과 + 코드블록이 아님 → 강제 경계
    # 코드블록(```로 시작)은 맥락 보존을 위해 초과 허용
    if accumulated_chars >= max_chars:
        if not curr.get("text", "").lstrip().startswith("```"):
            return True

    return False


def _make_parent_id(file_name: str, idx: int) -> str:
    key = f"{file_name}__parent_{idx}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _split_group_by_chunks(group: list[dict], max_chars: int) -> list[list[dict]]:
    """
    그룹을 chunk 경계에서만 분할해 sub-group 리스트를 반환한다.
    각 sub-group의 combined 크기가 max_chars 이하가 되도록 보장하며,
    단일 chunk가 max_chars를 초과하면 그 chunk만 단독 sub-group으로 둔다.
    chunk 경계에서만 자르므로 parent가 항상 child chunk 텍스트를 완전히 포함한다.
    """
    subgroups: list[list[dict]] = []
    cur: list[dict] = []
    size = 0

    for c in group:
        clen = len(c["text"])
        sep = 2 if cur else 0  # "\n\n" 구분자
        if cur and size + sep + clen > max_chars:
            subgroups.append(cur)
            cur = [c]
            size = clen
        else:
            cur.append(c)
            size += sep + clen

    if cur:
        subgroups.append(cur)

    return subgroups


def build_parents(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    child chunk 리스트를 순회하며 로컬 신호(heading_path, page, 누적 크기)로
    parent 경계를 감지하고 parent 레코드를 생성한다.

    같은 문서 안에서도 heading 구간은 heading 기준, heading 없는 구간은 page 기준,
    크기 초과 구간은 chunk 경계 기준으로 자동 전환된다.

    Returns:
        children: parent_id 컬럼이 추가된 child chunk 리스트 (원본 불변)
        parents:  parent 레코드 리스트
    """
    if not chunks:
        return [], []

    min_chars = int(os.getenv("MIN_PARENT_CHARS", "300"))
    max_chars = int(os.getenv("MAX_PARENT_CHARS", "3000"))
    file_name = chunks[0]["file_name"]

    # ── 1단계: 경계 감지로 chunk 그룹 구성 ──────────────────────────────
    groups: list[list[dict]] = []
    cur_group: list[dict] = []
    accumulated = 0

    for chunk in chunks:
        if not cur_group:
            cur_group.append(chunk)
            accumulated = len(chunk["text"])
            continue
        if _is_boundary(cur_group[-1], chunk, accumulated, min_chars, max_chars):
            groups.append(cur_group)
            cur_group = [chunk]
            accumulated = len(chunk["text"])
        else:
            cur_group.append(chunk)
            accumulated += len(chunk["text"])

    if cur_group:
        groups.append(cur_group)

    # ── 2단계: 각 그룹 → parent (크기 초과 시 chunk 경계 분할) ──────────
    parent_counter = 0
    parent_map: dict[int, str] = {}  # chunk_index → parent_id
    parents: list[dict] = []

    for group in groups:
        subgroups = _split_group_by_chunks(group, max_chars)
        for subgroup in subgroups:
            combined = "\n\n".join(c["text"] for c in subgroup)
            pid = _make_parent_id(file_name, parent_counter)
            parent_counter += 1
            parents.append(_make_parent_record(pid, combined, file_name, subgroup, subgroup))
            for c in subgroup:
                parent_map[c["chunk_index"]] = pid

    children = [dict(c) | {"parent_id": parent_map.get(c["chunk_index"], "")} for c in chunks]
    return children, parents


def _make_parent_record(
    pid: str,
    text: str,
    file_name: str,
    seg_chunks: list[dict],
    fallback_group: list[dict],
) -> dict:
    anchor = seg_chunks if seg_chunks else fallback_group
    return {
        "parent_id": pid,
        "text": text,
        "file_name": file_name,
        "page_start": anchor[0]["page"],
        "page_end": anchor[-1]["page"],
        "heading_path": list(anchor[0].get("heading_path") or []),
        "source_type": anchor[0].get("source_type", "general"),
    }
