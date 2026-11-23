import ast
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api import find_problem_feedback_route_conflicts, problem_feedback_route_keys
from app.config import Settings
from app.main import create_app
from app.schemas.integration_contracts import (
    FeedbackStoragePayload,
    GeneratedArtifactIndexPayload,
    ProblemItemAttemptPayload,
    ProblemItemStatPayload,
    ProblemStoragePayload,
    RetrievedChunk,
    SearchChunksRequest,
    SubmissionStoragePayload,
    UserConceptUpdatePayload,
)
from app.schemas.problems import GenerateProblemRequest, SubmitAnswerRequest


SMOKE_TEST_FILES = (
    "tests/test_openai_smoke_llm.py",
    "tests/test_rag_agent_live_smoke.py",
    "tests/test_generated_artifact_live_smoke.py",
    "tests/test_problem_agent_live_e2e_smoke.py",
)
EXPECTED_SMOKE_TEST_MARKERS = {
    ("tests/test_openai_smoke_llm.py", "test_live_openai_problem_generation_smoke"): {"llm"},
    ("tests/test_openai_smoke_llm.py", "test_live_openai_short_answer_feedback_smoke"): {"llm"},
    ("tests/test_rag_agent_live_smoke.py", "test_live_rag_agent_search_contract_returns_problem_ready_chunks"): {"rag"},
    ("tests/test_generated_artifact_live_smoke.py", "test_live_generated_artifact_index_accepts_problem_payload"): {"rag"},
    ("tests/test_problem_agent_live_e2e_smoke.py", "test_live_rag_problem_feedback_artifact_e2e"): {"rag"},
    ("tests/test_problem_agent_live_e2e_smoke.py", "test_live_rag_openai_problem_feedback_artifact_e2e"): {
        "llm",
        "rag",
    },
}
DOC_LINK_SOURCE_FILES = (
    *Path(".").glob("*.md"),
    *Path("docs").glob("*.md"),
    *Path("evals").glob("*.md"),
)


def _env_keys(path: str) -> set[str]:
    keys: set[str] = set()
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            stripped = stripped[1:].strip()
        if "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.isidentifier() and key.upper() == key:
            keys.add(key)
    return keys


def _env_values(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            stripped = stripped[1:].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.isidentifier() and key.upper() == key:
            values[key] = value.strip()
    return values


def _settings_aliases() -> set[str]:
    return {
        str(field.alias)
        for field in Settings.model_fields.values()
        if field.alias
    }


def _smoke_env_keys_from_tests() -> set[str]:
    keys: set[str] = set()
    for path in SMOKE_TEST_FILES:
        tree = ast.parse(Path(path).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "getenv"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                keys.add(node.args[0].value)
    return keys


def _smoke_env_keys() -> set[str]:
    return _smoke_env_keys_from_tests() - _settings_aliases()


def _pytest_marker_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _pytest_marker_name(node.func)
    if not isinstance(node, ast.Attribute):
        return None
    mark_node = node.value
    if not (
        isinstance(mark_node, ast.Attribute)
        and mark_node.attr == "mark"
        and isinstance(mark_node.value, ast.Name)
        and mark_node.value.id == "pytest"
    ):
        return None
    return node.attr


def _module_pytest_markers(tree: ast.Module) -> set[str]:
    markers: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
        markers.update(marker for value in values if (marker := _pytest_marker_name(value)))
    return markers


def _smoke_test_markers() -> dict[tuple[str, str], set[str]]:
    markers_by_test: dict[tuple[str, str], set[str]] = {}
    for path in SMOKE_TEST_FILES:
        tree = ast.parse(Path(path).read_text())
        module_markers = _module_pytest_markers(tree)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            function_markers = {
                marker for decorator in node.decorator_list if (marker := _pytest_marker_name(decorator))
            }
            markers_by_test[(path, node.name)] = module_markers | function_markers
    return markers_by_test


def _local_markdown_links(path: Path) -> list[Path]:
    links: list[Path] = []
    for target in re.findall(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)", path.read_text()):
        target = target.strip().strip("<>")
        if "://" in target or target.startswith("mailto:"):
            continue
        target_path = target.split("#", 1)[0]
        links.append((path.parent / target_path).resolve())
    return links


def test_env_example_covers_all_runtime_settings_aliases():
    missing = _settings_aliases() - _env_keys(".env.example")

    assert missing == set()


def test_env_example_documents_smoke_env_keys_used_by_live_tests():
    missing = _smoke_env_keys() - _env_keys(".env.example")

    assert missing == set()


def test_live_smoke_tests_have_expected_pytest_markers():
    markers_by_test = _smoke_test_markers()

    assert set(markers_by_test) == set(EXPECTED_SMOKE_TEST_MARKERS)
    missing_markers = {
        test_key: expected - markers_by_test[test_key]
        for test_key, expected in EXPECTED_SMOKE_TEST_MARKERS.items()
        if not expected <= markers_by_test[test_key]
    }

    assert missing_markers == {}


def test_env_examples_do_not_contain_unknown_runtime_keys():
    allowed_keys = _settings_aliases() | _smoke_env_keys()

    assert _env_keys(".env.example") - allowed_keys == set()
    assert _env_keys(".env.free.example") - allowed_keys == set()


def test_env_examples_keep_commercial_limits_disabled_by_default():
    disabled_values = {
        "LLM_MONTHLY_USER_BUDGET_KRW": "0",
        "LLM_ENFORCE_MONTHLY_BUDGET": "false",
        "PROBLEM_GENERATION_MONTHLY_LIMIT": "0",
        "PROBLEM_GENERATION_HIGH_RIGOR_MONTHLY_LIMIT": "0",
    }

    for path in [".env.example", ".env.free.example"]:
        values = _env_values(path)
        for key, expected in disabled_values.items():
            if key in values:
                assert values[key] == expected


def test_user_facing_markdown_links_resolve_to_existing_files():
    missing_links = []
    for path in DOC_LINK_SOURCE_FILES:
        for target in _local_markdown_links(path):
            if not target.exists():
                missing_links.append(f"{path}: {target}")

    assert missing_links == []


def test_user_facing_route_docs_cover_current_api_routes():
    app = create_app(auto_create_tables=False)
    api_paths = sorted(
        {
            route.path
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/")
        }
    )
    docs_text = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/problem-feedback-development-plan.md").read_text(),
            Path("docs/problem-feedback-shared-server-integration.md").read_text(),
        ]
    )

    missing_paths = [path for path in api_paths if path not in docs_text]

    assert missing_paths == []


def test_problem_feedback_route_inventory_has_no_internal_collisions():
    keys = problem_feedback_route_keys()

    assert len(keys) == len(set(keys))


def test_problem_feedback_route_conflict_checker_catches_shared_server_overlap():
    app = FastAPI()

    @app.get("/api/problems/{id}")
    async def existing_problem_detail():
        return {"ok": True}

    conflicts = find_problem_feedback_route_conflicts(app)

    assert conflicts == [("GET", "/api/problems/{}")]


def test_learning_signal_artifact_contract_requires_private_visibility():
    payload = GeneratedArtifactIndexPayload(
        artifact_id="learning_signal:fb_001",
        artifact_type="learning_signal",
        user_id="user_001",
        document_id="doc_001",
        content="학습 신호: 뉴턴 제2법칙",
        metadata={"schema_version": "learning_signal_artifact.v1"},
        source_chunk_ids=["chunk_001"],
        visibility="private",
    )

    assert payload.artifact_type == "learning_signal"

    with pytest.raises(ValidationError, match="learning_signal artifacts must use private visibility"):
        GeneratedArtifactIndexPayload(
            artifact_id="learning_signal:fb_001",
            artifact_type="learning_signal",
            user_id="user_001",
            document_id="doc_001",
            content="학습 신호: 뉴턴 제2법칙",
            source_chunk_ids=["chunk_001"],
            visibility="hidden_until_submission",
        )


def test_learning_content_artifact_contract_requires_private_visibility():
    payload = GeneratedArtifactIndexPayload(
        artifact_id="content_001",
        artifact_type="learning_content",
        user_id="user_001",
        document_id="doc_001",
        content="학습 콘텐츠: cloze",
        metadata={"schema_version": "learning_content_artifact.v1"},
        source_chunk_ids=["chunk_001"],
        visibility="private",
    )

    assert payload.artifact_type == "learning_content"

    with pytest.raises(ValidationError, match="learning_content artifacts must use private visibility"):
        GeneratedArtifactIndexPayload(
            artifact_id="content_001",
            artifact_type="learning_content",
            user_id="user_001",
            document_id="doc_001",
            content="학습 콘텐츠: cloze",
            source_chunk_ids=["chunk_001"],
            visibility="hidden_until_submission",
        )


def test_assessment_report_artifact_contract_requires_private_visibility():
    payload = GeneratedArtifactIndexPayload(
        artifact_id="assessment_report:asess_001",
        artifact_type="assessment_report",
        user_id="user_001",
        document_id="doc_001",
        content="평가 세트 리포트: asess_001",
        metadata={"schema_version": "assessment_report_artifact.v1"},
        visibility="private",
    )

    assert payload.artifact_type == "assessment_report"

    with pytest.raises(ValidationError, match="assessment_report artifacts must use private visibility"):
        GeneratedArtifactIndexPayload(
            artifact_id="assessment_report:asess_001",
            artifact_type="assessment_report",
            user_id="user_001",
            document_id="doc_001",
            content="평가 세트 리포트: asess_001",
            visibility="hidden_until_submission",
        )


def test_search_contract_accepts_required_chunk_fields():
    request = SearchChunksRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        difficulty="medium",
        query="뉴턴 제2법칙",
        top_k=6,
    )
    chunk = RetrievedChunk(
        chunk_id="chunk_001",
        document_id="doc_001",
        content="뉴턴의 제2법칙은 F = ma이다.",
        concepts=["뉴턴 제2법칙"],
    )

    assert request.top_k == 6
    assert chunk.page is None


def test_generate_problem_request_rejects_duplicate_or_empty_concepts():
    with pytest.raises(ValidationError):
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙", "뉴턴 제2법칙"],
            type="multiple_choice",
        )

    with pytest.raises(ValidationError):
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=[" "],
            type="multiple_choice",
        )


def test_generate_problem_request_accepts_ui_problem_style():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        type="short_answer",
        problem_style="calculation_practice",
    )

    assert request.problem_style == "calculation_practice"

    with pytest.raises(ValidationError):
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            problem_style="copy_exam_bank",
        )


def test_submit_answer_request_rejects_oversized_answer_text():
    with pytest.raises(ValidationError):
        SubmitAnswerRequest(answer={"text": "가" * 4001})


def test_problem_storage_contract_rejects_multiple_choice_without_source_chunks():
    with pytest.raises(ValidationError):
        ProblemStoragePayload(
            user_id="user_001",
            document_id="doc_001",
            type="multiple_choice",
            difficulty="medium",
            bloom_level="understand",
            question="질문",
            choices=[
                {"id": "A", "text": "A"},
                {"id": "B", "text": "B"},
                {"id": "C", "text": "C"},
                {"id": "D", "text": "D"},
            ],
            answer={"choice_id": "A", "text": "A"},
            explanation="해설",
            choice_explanations={"A": "정답"},
            concepts=["개념"],
            source_chunk_ids=[],
        )


def test_problem_storage_contract_accepts_short_answer_rubric():
    payload = ProblemStoragePayload(
        user_id="user_001",
        document_id="doc_001",
        type="short_answer",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙을 설명하시오.",
        choices=None,
        answer={"text": "F = ma이다."},
        explanation="힘, 질량, 가속도의 관계를 설명한다.",
        choice_explanations=None,
        rubric=[{"criterion": "핵심 공식을 포함했다.", "points": 2}],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
    )

    assert payload.rubric[0].points == 2


def test_problem_storage_contract_accepts_source_evidence_snapshot():
    payload = ProblemStoragePayload(
        user_id="user_001",
        document_id="doc_001",
        type="short_answer",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙을 설명하시오.",
        choices=None,
        answer={"text": "F = ma이다."},
        explanation="힘, 질량, 가속도의 관계를 설명한다.",
        choice_explanations=None,
        rubric=[{"criterion": "핵심 공식을 포함했다.", "points": 2}],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        source_evidence_snapshot=[
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "뉴턴의 제2법칙은 F = ma이다.",
                "page": 12,
                "section_title": "뉴턴의 운동 법칙",
                "concepts": ["뉴턴 제2법칙"],
            }
        ],
    )

    assert payload.source_evidence_snapshot[0].chunk_id == "chunk_001"


def test_problem_storage_contract_rejects_mismatched_source_evidence_snapshot():
    with pytest.raises(ValidationError, match="source_evidence_snapshot"):
        ProblemStoragePayload(
            user_id="user_001",
            document_id="doc_001",
            type="short_answer",
            difficulty="medium",
            bloom_level="understand",
            question="뉴턴의 제2법칙을 설명하시오.",
            choices=None,
            answer={"text": "F = ma이다."},
            explanation="힘, 질량, 가속도의 관계를 설명한다.",
            choice_explanations=None,
            rubric=[{"criterion": "핵심 공식을 포함했다.", "points": 2}],
            concepts=["뉴턴 제2법칙"],
            source_chunk_ids=["chunk_001"],
            source_evidence_snapshot=[
                {
                    "chunk_id": "other_chunk",
                    "document_id": "doc_001",
                    "content": "다른 근거",
                }
            ],
        )


def test_problem_storage_contract_rejects_shape_mismatch():
    with pytest.raises(ValidationError):
        ProblemStoragePayload(
            user_id="user_001",
            document_id="doc_001",
            type="short_answer",
            difficulty="medium",
            bloom_level="understand",
            question="뉴턴의 제2법칙을 설명하시오.",
            choices=[{"id": "A", "text": "보기"}],
            answer={"choice_id": None, "text": "F = ma이다."},
            explanation="힘, 질량, 가속도의 관계를 설명한다.",
            choice_explanations=None,
            rubric=[{"criterion": "핵심 공식을 포함했다.", "points": 2}],
            concepts=["뉴턴 제2법칙"],
            source_chunk_ids=["chunk_001"],
        )


def test_submission_contract_accepts_tablet_ocr_answer():
    submission = SubmissionStoragePayload(
        problem_id="prob_002",
        user_id="user_001",
        answer={
            "input_mode": "tablet_ocr",
            "ocr_text": "뉴턴 제2법칙은 힘과 질량과 가속도의 관계를 설명한다.",
            "ocr_confidence": 0.9,
            "tablet_image_url": "https://example.test/submission.png",
        },
    )

    assert submission.answer["text"] == submission.answer["ocr_text"]
    assert submission.answer["input_mode"] == "tablet_ocr"


def test_submission_feedback_and_user_update_contracts():
    submission = SubmissionStoragePayload(
        problem_id="prob_001",
        user_id="user_001",
        answer={"choice_id": "C", "text": "C"},
    )
    feedback = FeedbackStoragePayload(
        submission_id="sub_001",
        problem_id="prob_001",
        user_id="user_001",
        is_correct=False,
        score=0,
        max_score=1,
        mistake_type="concept_misunderstanding",
        weak_concepts=["뉴턴 제2법칙"],
        summary="핵심 개념을 헷갈렸어.",
        feedback="정답은 A야.",
        recommended_review=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
    )
    update = UserConceptUpdatePayload(
        user_id="user_001",
        problem_id="prob_001",
        submission_id="sub_001",
        feedback_id="fb_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=False,
        score=0,
        max_score=1,
        mistake_type="concept_misunderstanding",
        weak_concepts=["뉴턴 제2법칙"],
        recommended_review=["뉴턴 제2법칙"],
        mastery_updates=[
            {
                "concept": "뉴턴 제2법칙",
                "attempts": 2,
                "correct_count": 0,
                "wrong_count": 2,
                "mastery": 0.34,
                "mistake_types": ["concept_misunderstanding"],
                "should_review": True,
            }
        ],
    )

    assert submission.answer["choice_id"] == "C"
    assert feedback.score == 0
    assert update.recommended_review == ["뉴턴 제2법칙"]
    assert update.mastery_updates[0].should_review is True


def test_problem_item_attempt_contract_carries_choice_diagnostic():
    attempt = ProblemItemAttemptPayload(
        user_id="user_001",
        problem_id="prob_001",
        document_id="doc_001",
        submission_id="sub_001",
        feedback_id="fb_001",
        problem_type="multiple_choice",
        is_correct=False,
        score=0,
        max_score=1,
        selected_choice_id="C",
        mistake_type="concept_misunderstanding",
        choice_diagnostic={
            "selected_choice_id": "C",
            "selected_choice_text": "가속도는 항상 0이다.",
            "correct_choice_id": "A",
            "correct_choice_text": "힘은 질량과 가속도의 곱이다.",
            "selected_choice_explanation": "헷갈린 지점: 가속도를 항상 0으로 본 점.",
            "correct_choice_explanation": "자료의 식과 일치한다.",
            "misconception": "가속도를 항상 0으로 본 점.",
            "repair_strategy": "$F = ma$ 관계로 다시 확인한다.",
            "mistake_type": "concept_misunderstanding",
        },
    )

    assert attempt.selected_choice_id == "C"
    assert attempt.choice_diagnostic is not None
    assert attempt.choice_diagnostic.misconception.startswith("가속도")


def test_problem_item_stat_contract_tracks_choice_mistake_types():
    stats = ProblemItemStatPayload(
        problem_id="prob_001",
        document_id="doc_001",
        problem_type="multiple_choice",
        total_attempts=3,
        correct_count=1,
        incorrect_count=2,
        average_score=0.33,
        max_score=1,
        choice_selection_counts={"A": 1, "C": 2},
        choice_mistake_type_counts={"C": {"concept_misunderstanding": 2}},
        mistake_type_counts={"concept_misunderstanding": 2},
    )

    assert stats.choice_selection_counts["C"] == 2
    assert stats.choice_mistake_type_counts["C"]["concept_misunderstanding"] == 2


def test_user_concept_update_rejects_inconsistent_score():
    with pytest.raises(ValidationError):
        UserConceptUpdatePayload(
            user_id="user_001",
            problem_id="prob_001",
            submission_id="sub_001",
            feedback_id="fb_001",
            concepts=["뉴턴 제2법칙"],
            is_correct=True,
            score=0,
            max_score=1,
            mistake_type="none",
        )
