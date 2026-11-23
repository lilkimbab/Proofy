from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"(?:^|[\s\"'=])(?P<value>sk-[A-Za-z0-9_-]{20,})"),
    re.compile(r"^(?:OPENAI_API_KEY|SEARCH_AGENT_API_KEY|GENERATED_ARTIFACT_API_KEY)=(?P<value>[^\s#\\]*)", re.MULTILINE),
]


def tracked_public_text_files() -> list[Path]:
    return [
        REPO_ROOT / ".env.example",
        REPO_ROOT / ".env.free.example",
        REPO_ROOT / "README.md",
        REPO_ROOT / "GOAL.md",
        REPO_ROOT / "problem-feedback-roadmap.md",
        *sorted((REPO_ROOT / "docs").glob("*.md")),
    ]


def test_public_docs_and_env_examples_do_not_contain_real_api_keys():
    findings: list[str] = []
    for path in tracked_public_text_files():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                value = match.groupdict().get("value", match.group(0))
                if value in {"", "...", "sk-..."}:
                    continue
                findings.append(f"{path.relative_to(REPO_ROOT)} contains possible secret value: {value[:8]}...")

    assert findings == []
