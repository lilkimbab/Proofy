#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib import request as urllib_request


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_query(case: dict[str, Any]) -> str:
    terms = list(case.get("concepts") or []) + list(case.get("expected_search_terms") or [])
    seen: set[str] = set()
    cleaned: list[str] = []
    for term in terms:
        value = " ".join(str(term or "").split())
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            cleaned.append(value)
    return " ".join(cleaned)


def suggest_goldens_for_case(case: dict[str, Any], *, rag_url: str, top_k: int) -> dict[str, Any]:
    payload = {
        "query": build_query(case),
        "title": case["document_id"],
        "top_k": top_k,
        "filter": None,
    }
    req = urllib_request.Request(
        f"{rag_url.rstrip('/')}/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=30) as response:  # noqa: S310 - CLI points to local trusted RAG URL.
        raw_payload = json.loads(response.read().decode("utf-8"))
    results = extract_results(raw_payload)
    chunk_ids = [chunk_id for chunk_id in (extract_chunk_id(item) for item in results) if chunk_id]
    spans = [span for span in (extract_source_span(item) for item in results) if span]

    updated = dict(case)
    if not updated.get("expected_chunk_ids"):
        updated["expected_chunk_ids"] = chunk_ids[:top_k]
    if not updated.get("expected_source_spans"):
        updated["expected_source_spans"] = spans[: min(3, top_k)]
    updated["golden_label_mode"] = "partial"
    updated.pop("min_precision_at_k", None)
    return updated


def extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("results", "documents", "chunks", "items", "data", "matches", "contexts", "nodes"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def extract_chunk_id(item: dict[str, Any]) -> str | None:
    for key in ("chunk_id", "id", "node_id", "source_id"):
        value = item.get(key)
        if value:
            return str(value)
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for key in ("chunk_id", "id", "source_id"):
            value = metadata.get(key)
            if value:
                return str(value)
    return None


def extract_source_span(item: dict[str, Any]) -> str | None:
    for key in ("content", "text", "page_content", "parent_text", "chunk_text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return compact_span(value)
    return None


def compact_span(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:180]


def bootstrap_cases(
    *,
    cases_path: Path,
    out_path: Path,
    rag_url: str | None,
    top_k: int,
    apply: bool = False,
) -> list[dict[str, Any]]:
    rows = load_jsonl(cases_path)
    if not rag_url:
        print("RAG_AGENT_URL or --rag-url is missing; writing unchanged cases and exiting without live calls.")
        write_jsonl(out_path, rows)
        return rows

    suggested = [suggest_goldens_for_case(row, rag_url=rag_url, top_k=top_k) for row in rows]
    write_jsonl(cases_path if apply else out_path, suggested)
    return suggested


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Suggest partial golden labels for live benchmark cases.")
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rag-url", default=os.getenv("RAG_AGENT_URL"))
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bootstrap_cases(
        cases_path=args.cases,
        out_path=args.out,
        rag_url=args.rag_url,
        top_k=max(args.top_k, 1),
        apply=args.apply,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
