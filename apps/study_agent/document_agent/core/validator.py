import re
from collections import Counter

_OCR_OMIT_RE = re.compile(r'==>.*?intentionally omitted.*?<==', re.IGNORECASE | re.DOTALL)

# OCR 아티팩트가 키워드로 올라오지 않도록 blocklist
_OCR_STOPWORDS = frozenset({
    "picture", "intentionally", "omitted", "omit",
    "gt", "lt", "amp", "nbsp",
})


def _tokenize(text: str) -> list[str]:
    # Korean: extract syllable blocks of length ≥ 2 (strips particles/endings naturally)
    korean = re.findall(r'[가-힣]{2,}', text)
    # Latin/numbers: split by non-word chars, length ≥ 2
    latin = [t for t in re.findall(r'[A-Za-z0-9]{2,}', text) if t.lower() not in _OCR_STOPWORDS]
    return korean + latin


def validate_section(section_text: str, source_chunks: list[dict]) -> dict:
    # Strip OCR omit markers before tokenizing — same as creator does when calling the LLM
    raw = " ".join(c["text"] for c in source_chunks)
    all_text = _OCR_OMIT_RE.sub("", raw)
    tokens = _tokenize(all_text)
    keywords = [w for w, _ in Counter(tokens).most_common(10)]

    if not keywords:
        return {"coverage": 1.0, "missing_keywords": []}

    covered = sum(1 for k in keywords if k in section_text)
    coverage = covered / len(keywords)
    missing = [k for k in keywords if k not in section_text]
    return {"coverage": coverage, "missing_keywords": missing}
