import re


def replace_image_tags(text: str, image_map: dict) -> str:
    def _replace_tag(m: re.Match) -> str:
        chunk_id = m.group(1).strip()
        info = image_map.get(chunk_id)
        if not info:
            return ""
        page = info.get("page", "")
        if not page:
            return ""
        return f'<span class="page-chip" onclick="jumpToPage({page})" title="{page}페이지로 이동">[p.{page}]</span>'
    return re.sub(r"\[IMAGE:\s*([^\]]+)\]", _replace_tag, text)


def replace_page_anchors(text: str) -> str:
    def _replace(m: re.Match) -> str:
        n = m.group(1)
        return f'<span class="page-chip" onclick="jumpToPage({n})" title="{n}페이지로 이동">(p.{n})</span>'
    return re.sub(r'\(p\.(\d+)\)', _replace, text)


def assemble(
    sections_md: list[str],
    image_map: dict,  # chunk_id -> {"image": str, "source": str, "page": int}
    sources: list[dict],
) -> str:
    body = "\n\n".join(sections_md)
    body = replace_image_tags(body, image_map)
    body = replace_page_anchors(body)

    if sources:
        source_lines = "\n".join(
            f"- {s['file']} p.{s['page']} (chunk: {s['chunk_id']})" for s in sources
        )
        body += f"\n\n---\n\n## 출처\n{source_lines}"

    return body
