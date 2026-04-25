from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.content.curriculum_seed import build_curriculum_bundle


def _normalize_title(title: str) -> str:
    normalized = title.strip()
    normalized = re.sub(r"^(기본|중상|고난도|초고난도)\s*·\s*", "", normalized)
    normalized = re.sub(r"^(킬러|최종 apex|apex)\s*·\s*", "", normalized)
    normalized = re.sub(r"\s+킬러\s*\d+$", "", normalized)
    normalized = re.sub(r"\s+\d+$", "", normalized)
    return normalized.strip()


def _normalize_statement(statement: str) -> str:
    normalized = statement.strip()
    normalized = re.sub(r"\{[^}]+\}", "{#}", normalized)
    normalized = re.sub(r"\d+(?:/\d+)?", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _collect_duplicates(counter: Counter[str], *, minimum: int) -> list[dict]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if value and count >= minimum
    ]


def build_duplication_report() -> dict:
    bundle = build_curriculum_bundle()
    findings: list[dict] = []

    for problem_set in bundle.get("problemSets", []):
        problems = problem_set.get("problems", [])
        if not problems:
            continue

        type_counter = Counter(str(problem.get("problemType") or "").strip() for problem in problems)
        title_counter = Counter(_normalize_title(str(problem.get("title") or "")) for problem in problems)
        statement_counter = Counter(
            _normalize_statement(str(problem.get("statement") or "")) for problem in problems
        )
        killer_counter = Counter(
            str(problem.get("problemType") or "").strip()
            for problem in problems
            if problem.get("isKiller")
        )

        duplicate_types = _collect_duplicates(type_counter, minimum=3)
        duplicate_titles = _collect_duplicates(title_counter, minimum=2)
        duplicate_statement_templates = _collect_duplicates(statement_counter, minimum=2)
        duplicate_killer_types = _collect_duplicates(killer_counter, minimum=2)

        if not (
            duplicate_types
            or duplicate_titles
            or duplicate_statement_templates
            or duplicate_killer_types
        ):
            continue

        severity = (
            sum(item["count"] - 1 for item in duplicate_statement_templates)
            + sum(item["count"] - 1 for item in duplicate_killer_types)
            + sum(item["count"] - 1 for item in duplicate_types)
        )
        findings.append(
            {
                "problemSetId": problem_set["id"],
                "title": problem_set["title"],
                "problemCount": len(problems),
                "severity": severity,
                "duplicateProblemTypes": duplicate_types,
                "duplicateTitleStems": duplicate_titles,
                "duplicateStatementTemplates": duplicate_statement_templates,
                "duplicateKillerProblemTypes": duplicate_killer_types,
            }
        )

    findings.sort(key=lambda item: (-item["severity"], item["problemSetId"]))
    return {
        "bundleId": bundle.get("bundleId"),
        "findingCount": len(findings),
        "findings": findings,
    }


def render_markdown_report(report: dict) -> str:
    lines = [
        "# 콘텐츠 중복 감사",
        "",
        f"- bundle: `{report['bundleId']}`",
        f"- 중복이 감지된 문제 묶음 수: `{report['findingCount']}`",
        "",
    ]
    for finding in report["findings"]:
        lines.append(f"## {finding['problemSetId']}")
        lines.append(f"- 제목: {finding['title']}")
        lines.append(f"- 문항 수: {finding['problemCount']}")
        lines.append(f"- 심각도: {finding['severity']}")
        if finding["duplicateProblemTypes"]:
            lines.append("- 반복 problemType:")
            for item in finding["duplicateProblemTypes"][:8]:
                lines.append(f"  - {item['value']} × {item['count']}")
        if finding["duplicateKillerProblemTypes"]:
            lines.append("- 반복 killer problemType:")
            for item in finding["duplicateKillerProblemTypes"][:8]:
                lines.append(f"  - {item['value']} × {item['count']}")
        if finding["duplicateTitleStems"]:
            lines.append("- 반복 제목 줄기:")
            for item in finding["duplicateTitleStems"][:8]:
                lines.append(f"  - {item['value']} × {item['count']}")
        if finding["duplicateStatementTemplates"]:
            lines.append("- 숫자만 바꾼 문장 템플릿:")
            for item in finding["duplicateStatementTemplates"][:5]:
                lines.append(f"  - {item['value']} × {item['count']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    report = build_duplication_report()
    output_dir = Path("docs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "content_duplication_audit.md"
    output_path.write_text(render_markdown_report(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nmarkdown: {output_path}")


if __name__ == "__main__":
    main()
