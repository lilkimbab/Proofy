from app.agents import ProblemQualityChecker
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    ContentForm,
    ProblemStrategy,
    QualityFlag,
    QualityMode,
    QualityStatus,
    ReadinessLevel,
    SubjectDomain,
    TargetRigor,
)
from app.services.assessment_blueprint_service import AssessmentBlueprintPlanner
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.material_readiness_service import MaterialReadinessAnalyzer


def test_learning_task_router_uses_content_evidence_over_subject_guessing():
    request = generate_request(target_rigor=TargetRigor.high)
    chunk = physics_chunk()

    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])

    assert profile.subject_domain == SubjectDomain.science
    assert profile.topic_label == "뉴턴 제2법칙"
    assert "질량과 가속도" in profile.core_keywords
    assert ContentForm.formula in profile.content_forms
    assert ContentForm.concept_relation in profile.content_forms
    assert ProblemStrategy.near_transfer_application in profile.recommended_strategies


def test_learning_task_router_stays_conservative_when_subject_is_unclear():
    request = GenerateProblemRequest(
        document_id="doc_general",
        concepts=["학습 전략"],
        type="multiple_choice",
        count=1,
        target_rigor="high",
    )
    chunk = RetrievedChunk(
        chunk_id="chunk_general",
        document_id="doc_general",
        content="학습 전략은 목표 설정, 반복, 피드백을 통해 개선될 수 있다.",
        page=1,
        section_title="학습 전략",
        concepts=["학습 전략"],
    )

    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])

    assert profile.subject_domain in {SubjectDomain.unknown, SubjectDomain.general_concept}
    assert profile.subject_domain != SubjectDomain.science
    assert profile.strategy_id


def test_learning_task_router_recommends_content_types_from_chunk_tags():
    request = GenerateProblemRequest(
        document_id="doc_math",
        concepts=["이차함수"],
        type="multiple_choice",
        count=1,
    )
    chunk = RetrievedChunk(
        chunk_id="chunk_math",
        document_id="doc_math",
        content="이차함수는 y = ax^2 + bx + c로 나타내며 그래프의 꼭짓점과 축을 확인한다.",
        page=3,
        section_title="이차함수",
        concepts=["이차함수", "그래프", "꼭짓점"],
        tags=["math", "formula"],
        metadata={"content_forms": ["formula", "graph"], "subject_domain": "math"},
    )

    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])

    assert ContentForm.formula in profile.content_forms
    assert "ordering" in profile.selectable_learning_content_types
    assert "worked_example" in profile.available_learning_content_types
    assert "worked_example" in profile.recommended_learning_content_types
    assert "ordering" not in profile.available_learning_content_types
    assert "ordering" in profile.not_recommended_learning_content_types
    assert "순서 배열은 우선 추천하지 않는다" in profile.learning_content_type_reason


def test_learning_task_router_recommends_ordering_only_for_sequence_material():
    request = GenerateProblemRequest(
        document_id="doc_science",
        concepts=["실험 설계"],
        type="multiple_choice",
        count=1,
    )
    chunk = RetrievedChunk(
        chunk_id="chunk_sequence",
        document_id="doc_science",
        content="실험 설계는 가설 설정, 변수 통제, 측정, 결론 도출의 순서로 진행한다.",
        page=5,
        section_title="실험 설계 절차",
        concepts=["실험 설계", "변수 통제"],
        tags=["procedure"],
        metadata={"content_forms": ["procedure"]},
    )

    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])

    assert ContentForm.procedure in profile.content_forms
    assert "ordering" in profile.available_learning_content_types
    assert "ordering" in profile.recommended_learning_content_types


def test_material_readiness_allows_near_transfer_from_definition_with_relation():
    request = generate_request(target_rigor=TargetRigor.high)
    chunk = physics_chunk()
    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])

    readiness = MaterialReadinessAnalyzer().analyze(
        request=request,
        chunks=[chunk],
        strategy_profile=profile,
    )

    assert readiness.level in {ReadinessLevel.sufficient, ReadinessLevel.limited}
    assert ProblemStrategy.near_transfer_application in readiness.can_generate
    assert ProblemStrategy.calculation in readiness.can_generate
    assert any("간단한 응용" in reason for reason in readiness.reasons)


def test_quality_checker_rejects_definition_only_question_in_strict_exam_mode():
    request = generate_request(target_rigor=TargetRigor.high, quality_mode=QualityMode.strict)
    chunk = physics_chunk()
    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])
    readiness = MaterialReadinessAnalyzer().analyze(request=request, chunks=[chunk], strategy_profile=profile)
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )
    problem = valid_multiple_choice_problem()

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[chunk],
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is False
    assert report.status == QualityStatus.rejected
    assert QualityFlag.definition_only_risk in report.flags
    assert any("quality policy" in error for error in errors)


def test_quality_checker_accepts_near_transfer_question_from_relation_source():
    request = generate_request(target_rigor=TargetRigor.high, quality_mode=QualityMode.strict)
    chunk = physics_chunk()
    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])
    readiness = MaterialReadinessAnalyzer().analyze(request=request, chunks=[chunk], strategy_profile=profile)
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )
    problem = valid_multiple_choice_problem()
    problem["question"] = "같은 힘이 작용할 때 질량이 더 큰 물체의 가속도는 어떻게 변화하는가?"

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[chunk],
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is True
    assert errors == []
    assert report.status in {QualityStatus.passed, QualityStatus.limited_source}
    assert QualityFlag.definition_only_risk not in report.flags


def test_quality_checker_rejects_relation_summary_without_application_condition_in_strict_exam_mode():
    request = generate_request(target_rigor=TargetRigor.high, quality_mode=QualityMode.strict)
    chunk = physics_chunk()
    profile = LearningTaskStrategyRouter().route(request=request, chunks=[chunk])
    readiness = MaterialReadinessAnalyzer().analyze(request=request, chunks=[chunk], strategy_profile=profile)
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )
    problem = valid_multiple_choice_problem()
    problem["question"] = "뉴턴 제2법칙에서 질량과 가속도의 관계로 알맞은 것은?"

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[chunk],
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is False
    assert report.status == QualityStatus.rejected
    assert QualityFlag.blueprint_mismatch in report.flags
    assert any("blueprint_mismatch" in error for error in errors)


def generate_request(
    *,
    target_rigor: TargetRigor = TargetRigor.standard,
    quality_mode: QualityMode = QualityMode.standard,
) -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        type="multiple_choice",
        count=1,
        difficulty="medium",
        bloom_level="understand",
        goal="exam_prep",
        course_level="university",
        target_rigor=target_rigor,
        quality_mode=quality_mode,
    )


def physics_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk_001",
        document_id="doc_001",
        content=(
            "뉴턴의 제2법칙은 F = ma이다. 같은 힘이 작용할 때 질량이 클수록 "
            "가속도는 작아지고, 가속도는 힘에 비례하며 질량에 반비례한다."
        ),
        page=12,
        section_title="뉴턴의 운동 법칙",
        concepts=["뉴턴 제2법칙", "질량과 가속도"],
    )


def valid_multiple_choice_problem() -> dict:
    return {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴의 제2법칙은 무엇인가?",
        "choices": [
            {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "B", "text": "힘은 질량과 무관하다."},
            {"id": "C", "text": "가속도는 항상 0이다."},
            {"id": "D", "text": "질량이 클수록 같은 힘에서 가속도는 커진다."},
        ],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "뉴턴의 제2법칙은 F = ma로 나타낼 수 있다.",
        "choice_explanations": {
            "A": "힘, 질량, 가속도의 관계와 맞다.",
            "B": "질량은 식에 들어간다.",
            "C": "근거 문장과 맞지 않는다.",
            "D": "같은 힘에서는 질량이 클수록 가속도가 작아진다.",
        },
        "rubric": None,
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }
