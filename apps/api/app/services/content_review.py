from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.evaluator import (
    build_evaluator,
    canonical_submission_for_problem,
    is_auto_scorable_problem,
)
from app.services.content_generation import normalize_generated_bundle


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _review_problem(problem_set_id: str, problem: dict) -> dict:
    reasons: list[str] = []
    status = "approved"
    canonical_submission = canonical_submission_for_problem(problem)
    evaluation_type = str(problem.get("evaluationType") or "unknown")

    if not is_auto_scorable_problem(problem):
        status = "rejected"
        reasons.append(
            f"evaluationType '{evaluation_type}' 는 완전 자동채점 대상으로 확인되지 않았습니다."
        )
    elif canonical_submission is None:
        status = "rejected"
        reasons.append("canonical submission 을 만들지 못해 회귀 검증이 불가능합니다.")
    else:
        try:
            evaluator = build_evaluator(problem)
            feedback = evaluator.evaluate(canonical_submission)
            if not all(step.accepted for step in feedback):
                status = "rejected"
                reasons.append("canonical submission 회귀 검증에서 일부 step 이 통과하지 않았습니다.")
                reasons.extend(
                    f"{step.label}: {step.reason}" for step in feedback if not step.accepted
                )
        except Exception as exc:
            status = "rejected"
            reasons.append(f"evaluator 생성 또는 실행에 실패했습니다: {exc}")

    return {
        "id": f"review-item-{uuid4().hex[:8]}",
        "problemId": problem.get("id", ""),
        "problemSetId": problem_set_id,
        "title": problem.get("title", ""),
        "evaluationType": evaluation_type,
        "status": status,
        "reasons": reasons,
        "canonicalSubmission": canonical_submission,
    }


def _filter_approved_bundle(bundle: dict, review_items: list[dict]) -> dict:
    approved_map = {
        (item["problemSetId"], item["problemId"])
        for item in review_items
        if item["status"] == "approved"
    }
    approved_bundle = deepcopy(bundle)
    approved_problem_sets: list[dict] = []
    for problem_set in approved_bundle.get("problemSets", []):
        approved_problems = [
            problem
            for problem in problem_set.get("problems", [])
            if (problem_set["id"], problem.get("id")) in approved_map
        ]
        if not approved_problems:
            continue
        next_problem_set = deepcopy(problem_set)
        next_problem_set["problems"] = approved_problems
        approved_problem_sets.append(next_problem_set)
    approved_problem_set_ids = {item["id"] for item in approved_problem_sets}
    approved_lesson_pack_ids = {
        item.get("lessonPackId")
        for item in approved_problem_sets
        if item.get("lessonPackId")
    }
    approved_bundle["problemSets"] = approved_problem_sets
    approved_bundle["lessonPacks"] = [
        lesson
        for lesson in approved_bundle.get("lessonPacks", [])
        if lesson.get("id") in approved_lesson_pack_ids
    ]
    approved_bundle["concepts"] = [
        concept
        for concept in approved_bundle.get("concepts", [])
        if concept.get("problemSetId") in approved_problem_set_ids
    ]
    approved_concept_ids = {concept["id"] for concept in approved_bundle.get("concepts", [])}
    approved_bundle["diagnosticQuestions"] = [
        question
        for question in approved_bundle.get("diagnosticQuestions", [])
        if question.get("concept") in approved_concept_ids
    ]
    approved_bundle["reviewSummary"] = {
        "approvedProblemCount": sum(len(item.get("problems", [])) for item in approved_problem_sets),
        "problemSetCount": len(approved_problem_sets),
        "lessonPackCount": len(approved_bundle.get("lessonPacks", [])),
    }
    if approved_bundle.get("version"):
        approved_bundle["version"] = f"{approved_bundle['version']}-reviewed"
    return approved_bundle


def review_generated_bundle(raw_bundle: dict, *, source_provider: str = "gemini") -> dict:
    normalized = normalize_generated_bundle(raw_bundle)
    review_items: list[dict] = []
    for problem_set in normalized.get("problemSets", []):
        for problem in problem_set.get("problems", []):
            review_items.append(_review_problem(problem_set["id"], problem))

    approved_problem_count = sum(1 for item in review_items if item["status"] == "approved")
    rejected_problem_count = sum(1 for item in review_items if item["status"] == "rejected")
    approved_bundle = _filter_approved_bundle(normalized, review_items)
    if approved_problem_count == 0:
        status = "rejected"
    elif rejected_problem_count == 0:
        status = "approved"
    else:
        status = "partial"
    return {
        "reviewJobId": f"review-{uuid4().hex[:10]}",
        "createdAt": _utcnow_iso(),
        "sourceProvider": source_provider,
        "bundleId": normalized.get("bundleId", ""),
        "status": status,
        "approvedProblemCount": approved_problem_count,
        "rejectedProblemCount": rejected_problem_count,
        "rawBundle": normalized,
        "approvedBundle": approved_bundle,
        "items": review_items,
        "summary": {
            "message": "Gemini 생성 콘텐츠 묶음을 자동 검수해 완전 채점 가능한 문제만 승인했습니다.",
            "approvedProblemSetCount": len(approved_bundle.get("problemSets", [])),
            "approvedLessonPackCount": len(approved_bundle.get("lessonPacks", [])),
            "rejectedTitles": [
                item["title"] for item in review_items if item["status"] == "rejected"
            ],
        },
    }
