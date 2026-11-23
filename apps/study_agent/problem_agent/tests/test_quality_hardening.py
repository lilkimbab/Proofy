from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents import ProblemQualityChecker
from app.models import Problem
from app.repositories.problem_repository import ProblemRepository
from app.schemas.integration_contracts import ProblemItemStatPayload, RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import HighRigorGenerationProfile, QualityFlag, QualityMode
from app.services.evidence_obligation_evaluator import EvidenceObligationEvaluator
from app.services.professor_grade_item_service import ItemModelSelector, ProfessorGradeItemDesigner
from app.services.problem_kernel_planner import ProblemKernelPlanner
from app.services.problem_service import ProblemService


class FixedProblemAgent:
    def __init__(self, problems):
        self.problems = problems

    def generate(self, request, chunks, **kwargs):
        return self.problems


class FixedSearchService:
    def __init__(self, chunks):
        self.chunks = chunks

    def search_chunks(self, **kwargs):
        return self.chunks

    def get_chunks_by_ids(self, **kwargs):
        return self.chunks


class SpyProblemRepository(ProblemRepository):
    def __init__(self, db):
        super().__init__(db)
        self.create_many_called = False
        self.create_called = False

    def create(self, *, user_id: str, problem_data: dict) -> Problem:
        self.create_called = True
        return super().create(user_id=user_id, problem_data=problem_data)

    def create_many(self, *, user_id: str, problems_data: list[dict]) -> list[Problem]:
        self.create_many_called = True
        return super().create_many(user_id=user_id, problems_data=problems_data)


class RaisingAnswerVerifier:
    def verify(self, **kwargs):
        raise AssertionError("answer verifier should not run when disabled")


def test_strict_mode_rejects_all_or_none_multiple_choice_option(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["question"] = "같은 힘이 작용할 때 질량이 더 큰 물체의 가속도는 어떻게 변화하는가?"
    problem["choices"][3] = {"id": "D", "text": "위의 내용 모두"}
    problem["choice_explanations"]["D"] = "all/none 유형 보기는 쓰지 않는다."
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="all_or_none_option"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_rejects_absolute_wording_distractor_pattern(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["question"] = "같은 힘이 작용할 때 질량이 더 큰 물체의 가속도는 어떻게 변화하는가?"
    problem["choices"][1]["text"] = "가속도는 항상 커진다."
    problem["choices"][2]["text"] = "질량과 관계없이 반드시 같다."
    problem["choice_explanations"]["B"] = "자료의 질량과 가속도 관계와 반대다."
    problem["choice_explanations"]["C"] = "자료는 질량 조건에 따라 가속도가 달라진다고 설명한다."
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="absolute_wording"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_rejects_implausible_distractor_pattern(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["question"] = "같은 힘이 작용할 때 질량이 더 큰 물체의 가속도는 어떻게 변화하는가?"
    problem["choices"][2]["text"] = "자료와 관계없는 설명이다."
    problem["choice_explanations"]["C"] = "오답 보기도 그럴듯한 개념 혼동이어야 한다."
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="implausible_distractor"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_rejects_unfocused_multiple_choice_stem(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["question"] = "다음 중 옳은 것은?"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="unfocused_stem"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_high_risk_generation_reranks_candidates_by_quality(db_session, fixed_search):
    weak_problem = valid_multiple_choice_problem()
    weak_problem["question"] = "같은 힘이 작용할 때 질량이 더 큰 물체의 가속도는 어떻게 변화하는가?"
    weak_problem["choices"] = [
        {
            "id": "A",
            "text": "힘은 질량과 가속도의 곱이며 같은 힘에서는 질량이 클수록 가속도가 작아진다는 관계를 종합적으로 설명한 보기이다.",
        },
        {"id": "B", "text": "커진다."},
        {"id": "C", "text": "같다."},
        {"id": "D", "text": "사라진다."},
    ]
    weak_problem["answer"] = {
        "choice_id": "A",
        "text": "힘은 질량과 가속도의 곱이며 같은 힘에서는 질량이 클수록 가속도가 작아진다는 관계를 종합적으로 설명한 보기이다.",
    }
    weak_problem["choice_explanations"] = {
        "A": "자료 근거와 맞지만 정답 보기만 지나치게 길다.",
        "B": "자료의 질량과 가속도 관계와 반대다.",
        "C": "자료는 질량에 따라 가속도가 달라진다고 설명한다.",
        "D": "자료에 없는 설명이다.",
    }
    strong_problem = valid_high_rigor_multiple_choice_problem()
    service = build_service(db_session, fixed_search, [weak_problem, strong_problem])

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            goal="exam_prep",
            course_level="university",
            target_rigor="high",
        ),
    )

    assert len(problems) == 1
    assert problems[0].answer["text"] == strong_problem["answer"]["text"]


def test_high_risk_generation_summary_counts_discarded_candidates(db_session, fixed_search):
    weak_problem = valid_high_rigor_multiple_choice_problem()
    weak_problem["choices"][3] = {"id": "D", "text": "위의 내용 모두"}
    weak_problem["choice_explanations"]["D"] = "all/none 유형 보기는 저장 후보에서 밀려야 한다."
    strong_problem = valid_high_rigor_multiple_choice_problem()
    service = build_service(db_session, fixed_search, [weak_problem, strong_problem])

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            goal="exam_prep",
            course_level="university",
            target_rigor="high",
        ),
    )

    assert result.quality_summary.generated == 2
    assert result.quality_summary.passed == 1
    assert result.quality_summary.rejected == 0
    assert result.quality_summary.discarded == 1
    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.total_ms >= 0
    assert performance.search_ms is not None
    assert performance.candidate_generation_total_ms is not None
    assert performance.quality_filter_total_ms is not None
    assert performance.db_write_ms is not None
    assert performance.db_commit_ms is not None
    assert performance.actual_retry_count == 0
    assert performance.reject_rate == 0
    assert performance.pass_rate == 0.5
    assert len(performance.attempts) == 1
    assert performance.attempts[0].generated_candidate_count == 2
    assert performance.attempts[0].valid_candidate_count_after_attempt == 2


def test_problem_repository_create_many_preserves_order(db_session):
    repo = ProblemRepository(db_session)
    first = valid_multiple_choice_problem()
    second = valid_short_answer_problem()

    created = repo.create_many(user_id="user_001", problems_data=[first, second])

    assert [problem.question for problem in created] == [first["question"], second["question"]]
    assert [problem.type for problem in created] == ["multiple_choice", "short_answer"]
    assert all(problem.id for problem in created)
    assert all(problem.created_at for problem in created)


def test_generation_summary_warns_on_high_reject_rate(db_session, fixed_search):
    first_bad = {**valid_multiple_choice_problem(), "concepts": ["다른 개념"]}
    second_bad = {**valid_multiple_choice_problem(), "type": "short_answer"}
    service = build_service(db_session, fixed_search, [first_bad, second_bad, valid_multiple_choice_problem()])

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )

    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.reject_rate is not None
    assert performance.reject_rate > 0.5
    assert performance.rejected_candidate_count == 2
    assert performance.approximate_wasted_candidate_ratio == pytest.approx(2 / 3)
    assert any(warning.startswith("high reject rate:") for warning in result.quality_summary.warnings)
    assert performance.rejection_category_counts["request_mismatch"] == 2
    assert performance.top_rejection_categories == ["request_mismatch"]


def test_problem_service_uses_create_many_for_batch_save(db_session, fixed_search):
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem()])
    spy_repo = SpyProblemRepository(db_session)
    service.problem_repo = spy_repo

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )

    assert result.quality_summary.passed == 1
    assert spy_repo.create_many_called is True
    assert spy_repo.create_called is False


def test_refresh_saved_problems_skips_loaded_python_defaults(db_session, fixed_search, monkeypatch):
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem()])
    problem = Problem(
        id="prob_loaded",
        user_id="user_001",
        document_id="doc_001",
        type="multiple_choice",
        difficulty="medium",
        bloom_level="understand",
        question="문제",
        choices=[{"id": "A", "text": "정답"}],
        answer={"choice_id": "A", "text": "정답"},
        explanation="해설",
        choice_explanations={"A": "정답"},
        concepts=["개념"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
        created_at=datetime.now(timezone.utc),
    )

    def fail_refresh(problem):
        raise AssertionError("refresh should be skipped for loaded Python defaults")

    monkeypatch.setattr(db_session, "refresh", fail_refresh)

    service._refresh_saved_problems_if_needed([problem])


def test_strict_mode_rejects_long_verbatim_source_copy(db_session):
    source_text = (
        "계약은 청약과 승낙의 의사표시가 합치될 때 성립하며, 당사자 사이의 권리와 의무를 발생시키는 "
        "법률행위이다. 계약의 해석에서는 문언, 체결 경위, 거래 관행, 신의성실의 원칙을 종합적으로 고려한다."
    )
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="chunk_contract",
                document_id="doc_contract",
                content=source_text,
                page=3,
                section_title="계약의 성립",
                concepts=["계약의 성립"],
            )
        ]
    )
    problem = {
        "document_id": "doc_contract",
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "계약의 성립 요건을 자료를 바탕으로 설명하시오.",
        "choices": None,
        "answer": {"choice_id": None, "text": "계약은 청약과 승낙의 의사표시 합치로 성립한다."},
        "explanation": source_text,
        "choice_explanations": None,
        "rubric": [{"criterion": "청약과 승낙의 합치를 설명했다.", "points": 2}],
        "concepts": ["계약의 성립"],
        "source_chunk_ids": ["chunk_contract"],
    }
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="source_verbatim_overlap"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_contract",
                concepts=["계약의 성립"],
                type="short_answer",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_deep_short_answer_requires_evidence_aware_rubric_in_strict_mode(db_session, fixed_search):
    problem = valid_short_answer_problem()
    problem["question"] = "뉴턴 제2법칙을 적용해 같은 힘 조건에서 질량 차이가 가속도에 미치는 영향을 분석하시오."
    problem["rubric"] = [
        {"criterion": "정확성", "points": 2},
        {"criterion": "완성도", "points": 2},
    ]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="weak_rubric_evidence"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                depth="deep",
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rubric_quality_check_validates_optional_list_fields_even_with_evidence(db_session, fixed_search):
    problem = valid_short_answer_problem()
    problem["rubric"][0]["common_mistakes"] = "관계를 반대로 설명함"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="weak_rubric_evidence"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                depth="deep",
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_high_rigor_short_answer_flags_overlapping_rubric_evidence():
    problem = valid_short_answer_problem()
    problem["rubric"] = [
        {
            "criterion": f"자료 근거 기준 {index}",
            "points": 1,
            "expected_evidence": ["자료 근거"],
            "common_mistakes": ["자료 근거 누락"],
            "partial_credit_rules": ["자료 근거 일부"],
        }
        for index in range(3)
    ]
    checker = ProblemQualityChecker()

    check = checker._rubric_quality_check(
        problem=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            target_rigor="high",
        ),
    )

    assert QualityFlag.weak_rubric_evidence in check.flags
    assert "rubric_expected_evidence_too_overlapping" in check.issues
    assert "rubric_items_not_distinct" in check.issues
    assert "condition_missing_answer_scores_too_high" in check.issues


def test_high_rigor_short_answer_accepts_distinct_rubric_evidence():
    problem = valid_short_answer_problem()
    problem["rubric"] = [
        {
            "criterion": "자료의 절차 또는 규칙을 식별한다.",
            "points": 1,
            "expected_evidence": ["F = ma", "힘과 질량과 가속도의 관계"],
            "common_mistakes": ["공식의 역할을 밝히지 않음"],
            "partial_credit_rules": ["공식만 쓰면 부분점수"],
        },
        {
            "criterion": "주어진 조건에 규칙을 적용한다.",
            "points": 1,
            "expected_evidence": ["같은 힘 조건", "질량이 커질 때 가속도 변화"],
            "common_mistakes": ["같은 힘 조건을 누락함"],
            "partial_credit_rules": ["조건만 쓰면 부분점수"],
        },
        {
            "criterion": "결론을 해석한다.",
            "points": 1,
            "expected_evidence": ["가속도는 작아진다", "반비례 해석"],
            "common_mistakes": ["결론 방향을 반대로 씀"],
            "partial_credit_rules": ["결론만 맞으면 부분점수"],
        },
    ]
    checker = ProblemQualityChecker()

    check = checker._rubric_quality_check(
        problem=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            target_rigor="high",
        ),
    )

    assert check.flags == []
    assert check.issues == []


def test_strict_mode_rejects_data_interpretation_without_source_values(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="enzyme_table",
                document_id="doc_enzyme",
                content="표에서 효소 활성은 25도에서 40, 37도에서 80, 45도에서 30으로 제시된다.",
                page=4,
                section_title="효소 활성 표",
                concepts=["효소", "온도", "활성"],
            )
        ]
    )
    problem = valid_data_interpretation_problem()
    problem["answer"]["text"] = "표에 나온 온도별 효소 활성을 비교하면 온도 조건에 따라 활성 수준이 달라진다고 해석할 수 있다."
    problem["explanation"] = "표는 온도와 효소 활성의 관계를 보여준다."
    problem["rubric"] = [
        {
            "criterion": "표에 나온 온도별 효소 활성을 근거로 비교한다.",
            "points": 2,
            "expected_evidence": ["온도별 효소 활성", "비교"],
            "common_mistakes": ["수치 없이 온도 조건만 설명함"],
            "partial_credit_rules": ["활성 조건만 언급하면 1점"],
        },
        {
            "criterion": "효소 활성이 달라지는 조건을 해석한다.",
            "points": 2,
            "expected_evidence": ["조건", "해석"],
            "common_mistakes": ["숫자 비교와 결론을 연결하지 않음"],
            "partial_credit_rules": ["조건만 쓰면 1점"],
        },
    ]
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="item_model_quality_violation"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_enzyme",
                concepts=["효소", "온도", "활성"],
                type="short_answer",
                count=1,
                difficulty="hard",
                bloom_level="analyze",
                quality_mode=QualityMode.strict,
                depth="deep",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_accepts_data_interpretation_with_value_based_conclusion(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="enzyme_table",
                document_id="doc_enzyme",
                content="표에서 효소 활성은 25도에서 40, 37도에서 80, 45도에서 30으로 제시된다.",
                page=4,
                section_title="효소 활성 표",
                concepts=["효소", "온도", "활성"],
            )
        ]
    )
    service = build_service(db_session, search, [valid_data_interpretation_problem()])

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_enzyme",
            concepts=["효소", "온도", "활성"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            quality_mode=QualityMode.strict,
            depth="deep",
        ),
    )

    assert len(problems) == 1
    assert problems[0].item_model_id == "data_interpretation"


def test_strict_mode_rejects_misconception_contrast_with_duplicate_targets(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="evap_chunk",
                document_id="doc_evap",
                content="증발은 액체 표면에서 기체로 변하는 현상이며 끓음과 달리 표면에서 일어난다.",
                page=2,
                section_title="증발",
                concepts=["증발", "상태 변화"],
            )
        ]
    )
    problem = valid_misconception_contrast_problem()
    for diagnostic in problem["choice_diagnostics"]:
        if diagnostic["is_correct"] is not True:
            diagnostic["misconception_id"] = "same_evap_misconception"
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="item_model_quality_violation"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_evap",
                concepts=["증발"],
                type="multiple_choice",
                count=1,
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_rejects_evidence_selection_without_claim_link(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ]
    )
    problem = valid_evidence_selection_problem()
    problem["explanation"] = "A가 정답이다."
    problem["choice_explanations"] = {
        "A": "자료와 일치한다.",
        "B": "자료와 거리가 있다.",
        "C": "자료와 거리가 있다.",
        "D": "자료와 거리가 있다.",
    }
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="item_model_quality_violation"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_photo",
                concepts=["광합성", "빛 에너지"],
                type="multiple_choice",
                count=1,
                bloom_level="analyze",
                quality_mode=QualityMode.strict,
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_accepts_evidence_selection_with_claim_link(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ]
    )
    service = build_service(db_session, search, [valid_evidence_selection_problem()])

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_photo",
            concepts=["광합성", "빛 에너지"],
            type="multiple_choice",
            count=1,
            bloom_level="analyze",
            quality_mode=QualityMode.strict,
        ),
    )

    assert len(problems) == 1
    assert problems[0].item_model_id == "evidence_selection"


def test_item_model_selector_ignores_source_only_evidence_cues_for_task_classification():
    selector = ItemModelSelector()
    item_model_id = selector.select(
        request=GenerateProblemRequest(
            document_id="doc_idx",
            concepts=["range query", "balanced index tree"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            problem_style="evidence_analysis",
        ),
        problem_data={
            "document_id": "doc_idx",
            "type": "multiple_choice",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "question": "조건이 바뀔 때 range query 성능 판단으로 가장 적절한 것은?",
            "choices": [{"id": "A", "text": "balanced tree가 필요하다."}],
            "answer": {"choice_id": "A", "text": "balanced tree가 필요하다."},
            "explanation": "범위 질의 조건에서는 균형 구조가 탐색 비용을 안정화한다.",
            "concepts": ["range query"],
            "source_chunk_ids": ["idx_chunk"],
        },
        chunks=[
            RetrievedChunk(
                chunk_id="idx_chunk",
                document_id="doc_idx",
                content="This source evidence supports the lecture claim. 자료 근거를 제시한다.",
                page=1,
                section_title="Indexing",
                concepts=["range query"],
            )
        ],
    )

    assert item_model_id.value == "case_based_application"


def test_item_model_selector_detects_source_grounded_claim_evaluation_task():
    selector = ItemModelSelector()
    item_model_id = selector.select(
        request=GenerateProblemRequest(
            document_id="doc_photo",
            concepts=["광합성", "빛 에너지"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            problem_style="evidence_analysis",
        ),
        problem_data=valid_evidence_claim_evaluation_problem(),
        chunks=[
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ],
    )

    assert item_model_id.value == "evidence_selection"


def test_strict_mode_accepts_high_rigor_evidence_analysis_claim_evaluation_mcq(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ]
    )
    service = build_service(db_session, search, [valid_evidence_claim_evaluation_problem()])

    problems = service.generate_problems(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_photo",
            concepts=["광합성", "빛 에너지"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            target_rigor="high",
            quality_mode=QualityMode.strict,
            problem_style="evidence_analysis",
        ),
    )

    assert len(problems) == 1
    assert problems[0].item_model_id == "evidence_selection"
    assert problems[0].difficulty_profile["reasoning_steps_required"] >= 2


def test_strict_mode_rejects_evidence_analysis_without_evidence_claim_link(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ]
    )
    problem = valid_evidence_claim_evaluation_problem()
    problem["explanation"] = "A가 정답이다."
    problem["choice_explanations"] = {choice["id"]: "자료를 확인한다." for choice in problem["choices"]}
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="item_model_quality_violation"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_photo",
                concepts=["광합성", "빛 에너지"],
                type="multiple_choice",
                count=1,
                difficulty="hard",
                bloom_level="analyze",
                target_rigor="high",
                quality_mode=QualityMode.strict,
                problem_style="evidence_analysis",
            ),
        )


def test_strict_mode_rejects_high_rigor_evidence_analysis_with_generic_diagnostics(db_session):
    search = FixedSearchService(
        [
            RetrievedChunk(
                chunk_id="photo_chunk",
                document_id="doc_photo",
                content="광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
                page=3,
                section_title="광합성 조건",
                concepts=["광합성", "빛 에너지"],
            )
        ]
    )
    problem = valid_evidence_claim_evaluation_problem()
    for diagnostic in problem["choice_diagnostics"]:
        if diagnostic["is_correct"] is not True:
            diagnostic["mistake_type"] = "generic_error"
            diagnostic["misconception_id"] = "same_generic"
            diagnostic["why_plausible"] = "자료를 잘못 읽었다."
            diagnostic["repair_strategy"] = "자료를 다시 확인한다."
    service = build_service(db_session, search, [problem])

    with pytest.raises(ValueError, match="item_model_quality_violation"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_photo",
                concepts=["광합성", "빛 에너지"],
                type="multiple_choice",
                count=1,
                difficulty="hard",
                bloom_level="analyze",
                target_rigor="high",
                quality_mode=QualityMode.strict,
                problem_style="evidence_analysis",
            ),
        )


def test_quality_report_exposes_source_grounding_metadata(fixed_search):
    problem = valid_multiple_choice_problem()
    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=fixed_search.chunks,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )

    assert is_valid is True
    assert errors == []
    assert report.source_coverage_score is not None
    assert report.unsupported_numbers == []
    assert QualityFlag.source_verbatim_overlap not in report.flags


@pytest.mark.parametrize(
    ("problem_factory", "expected_flag"),
    [
        (lambda: adversarial_broad_correctness_mcq(), QualityFlag.definition_only_risk),
        (lambda: adversarial_definition_only_mcq(), QualityFlag.definition_only_risk),
        (lambda: adversarial_absolute_distractors_mcq(), QualityFlag.absolute_wording),
        (lambda: adversarial_generic_diagnostics_mcq(), QualityFlag.item_model_quality_violation),
        (lambda: adversarial_evidence_analysis_without_source_link_mcq(), QualityFlag.item_model_quality_violation),
    ],
)
def test_adversarial_high_rigor_mcq_bad_cases_are_rejected(fixed_search, problem_factory, expected_flag):
    problem = problem_factory()
    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=fixed_search.chunks,
        request=adversarial_high_rigor_mcq_request(),
        high_rigor_profile=adversarial_high_rigor_mcq_profile(),
    )

    assert is_valid is False
    assert errors
    assert expected_flag in report.flags


def test_adversarial_high_rigor_mcq_keyword_match_answer_is_rejected_or_needs_review():
    source_text = (
        "뉴턴의 제2법칙은 힘이 질량과 가속도의 곱으로 표현되며, 같은 힘이 작용하는 상황에서는 "
        "질량이 커질수록 가속도는 작아진다는 관계를 통해 운동 상태 변화를 설명한다. "
        "이 관계는 조건을 고정한 뒤 변수 하나가 달라질 때 결과를 판단하는 데 쓰인다."
    )
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_keyword",
            document_id="doc_001",
            content=source_text,
            page=12,
            section_title="뉴턴의 운동 법칙",
            concepts=["뉴턴 제2법칙", "질량과 가속도"],
        )
    ]
    problem = adversarial_keyword_match_mcq(source_text)

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=adversarial_high_rigor_mcq_request(),
        high_rigor_profile=adversarial_high_rigor_mcq_profile(),
    )

    assert is_valid is False
    assert errors
    assert QualityFlag.source_verbatim_overlap in report.flags


def test_adversarial_high_rigor_mcq_good_case_passes(fixed_search):
    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        strong_source_grounded_claim_mcq(),
        retrieved_chunks=fixed_search.chunks,
        request=adversarial_high_rigor_mcq_request(problem_style="evidence_analysis"),
        high_rigor_profile=adversarial_high_rigor_mcq_profile(),
    )

    assert is_valid is True
    assert errors == []
    assert report.status.value == "passed"


def test_adversarial_high_rigor_mcq_errors_map_to_retry_feedback_categories(db_session, fixed_search):
    service = build_service(db_session, fixed_search, [])
    expected = {
        "missing_concrete_context": (
            "high-rigor multiple-choice item must include a concrete condition, case, source evidence, input, data, code, or changed scenario"
        ),
        "shallow_definition_recall": (
            "high-rigor multiple-choice item is too close to recall or broad correctness checking"
        ),
        "testwise_option_cue": "problem rejected by quality policy: absolute_wording",
        "weak_distractor_diagnostics": (
            "high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures"
        ),
        "evidence_analysis_structure": (
            "evidence_analysis MCQ must ask for source-evidence selection or source-grounded claim evaluation"
        ),
    }

    for category, error in expected.items():
        assert service._categorize_generation_error(error) == category

    feedback = service._summarize_retry_feedback(list(expected.values()))
    assert any("concrete condition" in item for item in feedback)
    assert any("definition-only" in item for item in feedback)
    assert any("absolute words" in item for item in feedback)
    assert any("distinct misconceptions" in item for item in feedback)
    assert any("source-evidence selection" in item for item in feedback)


def test_cpp_destructor_diagnose_error_mcq_plan_passes_quick_validation(db_session):
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["heap", "destructor", "dynamic memory"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        problem_style="error_detection",
    )
    problem = {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "힙에 할당한 배열을 소멸자에서 해제해야 하는 클래스에서, 어떤 학생 설명이 가장 정확한 오류 진단인가?",
        "choices": [
            {"id": "A", "text": "delete[]를 누락하면 객체 수명이 끝나도 힙 메모리가 반환되지 않는다는 점을 지적해야 한다."},
            {"id": "B", "text": "스택 객체라면 소멸자가 호출되지 않으므로 해제 코드는 필요 없다."},
            {"id": "C", "text": "new[]로 만든 배열도 delete 하나만 쓰면 충분하다고 진단해야 한다."},
            {"id": "D", "text": "힙 메모리는 프로그램 종료 때만 해제되므로 클래스 설계와 무관하다고 보아야 한다."},
        ],
        "answer": {
            "choice_id": "A",
            "text": "delete[]를 누락하면 객체 수명이 끝나도 힙 메모리가 반환되지 않는다는 점을 지적해야 한다.",
        },
        "explanation": "자료의 destructor rule은 객체 수명이 끝날 때 소유한 heap resource를 해제해야 한다는 절차를 요구한다.",
        "choice_explanations": {
            "A": "소멸자가 소유한 힙 자원을 해제해야 한다는 규칙과 맞다.",
            "B": "스택 객체도 수명이 끝나면 소멸자가 호출된다는 절차를 놓쳤다.",
            "C": "new[]와 delete[]의 짝을 혼동한 진단이다.",
            "D": "자원 해제 책임을 프로그램 종료로 미뤄 소유권 규칙을 무시했다.",
        },
        "choice_diagnostics": [
            {"choice_id": "A", "is_correct": True, "misconception_id": None, "mistake_type": "none", "why_plausible": None, "repair_strategy": None, "followup_problem_type": None},
            {"choice_id": "B", "is_correct": False, "misconception_id": "destructor_not_called_for_stack_object", "mistake_type": "procedure_order_error", "why_plausible": "스택과 힙을 객체 수명과 혼동하면 그럴듯하다.", "repair_strategy": "객체 수명 종료와 소멸자 호출 순서를 먼저 추적한다.", "followup_problem_type": "trace_process"},
            {"choice_id": "C", "is_correct": False, "misconception_id": "delete_array_pair_confusion", "mistake_type": "rule_overgeneralization", "why_plausible": "delete와 delete[]를 같은 해제 연산으로 보면 그럴듯하다.", "repair_strategy": "할당 형태 new/new[]와 해제 형태 delete/delete[]를 짝지어 확인한다.", "followup_problem_type": "error_diagnosis"},
            {"choice_id": "D", "is_correct": False, "misconception_id": "ownership_release_ignored", "mistake_type": "missing_condition", "why_plausible": "운영체제가 종료 때 회수한다는 사실을 클래스 책임과 혼동할 수 있다.", "repair_strategy": "소유권이 있는 클래스가 수명 종료 시 해제해야 하는 조건을 표시한다.", "followup_problem_type": "source_review"},
        ],
        "rubric": None,
        "concepts": ["heap", "destructor", "dynamic memory"],
        "source_chunk_ids": ["cpp_chunk"],
        "mcq_plan": {
            "kernel_type": "diagnose_error",
            "source_rule_or_evidence": "A destructor releases heap resources owned by the object.",
            "concrete_scenario": "클래스가 new[]로 힙 배열을 소유하고 객체 수명 종료 시 소멸자가 호출되는 사례",
            "correct_answer_claim": "delete[] 누락은 객체 수명 종료 후 힙 메모리를 해제하지 않는 오류다.",
            "correct_answer_evidence_link": "destructor releases owned heap resources and new[] pairs with delete[].",
            "distractor_plans": [
                {"misconception_id": "destructor_not_called_for_stack_object", "mistake_type": "procedure_order_error", "why_plausible": "스택 객체와 힙 자원의 수명을 혼동한다.", "violated_or_ignored_evidence_role": "procedure_step", "repair_strategy": "객체 수명 종료와 소멸자 호출 순서를 먼저 추적한다."},
                {"misconception_id": "delete_array_pair_confusion", "mistake_type": "rule_overgeneralization", "why_plausible": "delete와 delete[]를 같은 규칙으로 과잉 일반화한다.", "violated_or_ignored_evidence_role": "rule", "repair_strategy": "할당 형태 new/new[]와 해제 형태 delete/delete[]를 짝지어 확인한다."},
                {"misconception_id": "ownership_release_ignored", "mistake_type": "missing_condition", "why_plausible": "프로그램 종료 회수를 클래스 소유권 규칙과 혼동한다.", "violated_or_ignored_evidence_role": "condition", "repair_strategy": "소유권이 있는 클래스가 수명 종료 시 해제해야 하는 조건을 표시한다."},
            ],
            "prohibited_patterns": ["definition-only", "same distractor failure"],
            "required_source_chunk_ids": ["cpp_chunk"],
        },
    }
    service = build_service(db_session, FixedSearchService([]), [])

    assert service._quick_validate_high_rigor_mcq_candidate(
        problem_data=problem,
        request=request,
        high_rigor_profile=adversarial_high_rigor_mcq_profile(),
    ) == []


def test_statistics_discriminant_diagnose_error_mcq_plan_passes_quick_validation(db_session):
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["discriminant analysis", "classification", "covariance"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        problem_style="error_detection",
    )
    problem = {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "공분산을 반영하는 판별분석 분류 설명에서, 어떤 오류 진단이 가장 타당한가?",
        "choices": [
            {"id": "A", "text": "공분산 차이를 무시하고 유클리드 거리만으로 군집을 고른 점이 오류다."},
            {"id": "B", "text": "판별분석에서는 거리 개념을 사용할 수 없으므로 모든 거리 비교가 오류다."},
            {"id": "C", "text": "프로파일링은 분류 뒤에만 가능하므로 사전 변수 선택이 오류다."},
            {"id": "D", "text": "분류 기준은 항상 평균이 큰 집단을 고르는 것이므로 작은 평균 선택이 오류다."},
        ],
        "answer": {"choice_id": "A", "text": "공분산 차이를 무시하고 유클리드 거리만으로 군집을 고른 점이 오류다."},
        "explanation": "자료의 discriminant analysis rule은 classification에서 covariance/Mahalanobis distance를 함께 고려해야 함을 요구한다.",
        "choice_explanations": {
            "A": "공분산을 반영한 거리 기준을 누락한 오류를 정확히 진단한다.",
            "B": "거리 사용 자체를 금지한다고 과잉 일반화한다.",
            "C": "프로파일링과 분류 기준을 잘못 연결한다.",
            "D": "평균 크기만 기준으로 삼는 잘못된 단순화를 한다.",
        },
        "choice_diagnostics": [
            {"choice_id": "A", "is_correct": True, "misconception_id": None, "mistake_type": "none", "why_plausible": None, "repair_strategy": None, "followup_problem_type": None},
            {"choice_id": "B", "is_correct": False, "misconception_id": "rejects_distance_entirely", "mistake_type": "rule_overgeneralization", "why_plausible": "유클리드 거리 오류를 거리 개념 전체의 오류로 넓히면 그럴듯하다.", "repair_strategy": "거리 사용 여부와 어떤 거리/공분산을 쓰는지 구분한다.", "followup_problem_type": "comparison_drill"},
            {"choice_id": "C", "is_correct": False, "misconception_id": "profiling_classification_order_confusion", "mistake_type": "procedure_order_error", "why_plausible": "분석 단계 이름을 순서 규칙으로 착각할 수 있다.", "repair_strategy": "분류 기준과 profiling 해석 단계를 따로 표시한다.", "followup_problem_type": "trace_process"},
            {"choice_id": "D", "is_correct": False, "misconception_id": "mean_only_classifier", "mistake_type": "missing_key_concept", "why_plausible": "평균 차이가 눈에 띄면 공분산을 생략해도 된다고 볼 수 있다.", "repair_strategy": "평균 차이와 공분산 구조가 함께 분류 기준에 들어가는지 확인한다.", "followup_problem_type": "evidence_check"},
        ],
        "rubric": None,
        "concepts": ["discriminant analysis", "classification", "covariance"],
        "source_chunk_ids": ["stats_chunk"],
        "mcq_plan": {
            "kernel_type": "diagnose_error",
            "source_rule_or_evidence": "Discriminant analysis classification accounts for covariance through Mahalanobis distance.",
            "concrete_scenario": "두 집단 평균과 공분산이 다른 상황에서 학생이 유클리드 거리만으로 분류하는 사례",
            "correct_answer_claim": "공분산을 무시하고 유클리드 거리만 사용한 것이 classification 오류다.",
            "correct_answer_evidence_link": "Mahalanobis distance uses covariance for discriminant classification.",
            "distractor_plans": [
                {"misconception_id": "rejects_distance_entirely", "mistake_type": "rule_overgeneralization", "why_plausible": "잘못된 거리 사용을 거리 사용 금지로 과잉 일반화한다.", "violated_or_ignored_evidence_role": "rule", "repair_strategy": "거리 사용 여부와 어떤 거리/공분산을 쓰는지 구분한다."},
                {"misconception_id": "profiling_classification_order_confusion", "mistake_type": "procedure_order_error", "why_plausible": "분석 단계 이름을 순서 규칙으로 착각한다.", "violated_or_ignored_evidence_role": "procedure_step", "repair_strategy": "분류 기준과 profiling 해석 단계를 따로 표시한다."},
                {"misconception_id": "mean_only_classifier", "mistake_type": "missing_key_concept", "why_plausible": "평균 차이가 눈에 띄면 공분산을 생략해도 된다고 본다.", "violated_or_ignored_evidence_role": "formula", "repair_strategy": "평균 차이와 공분산 구조가 함께 분류 기준에 들어가는지 확인한다."},
            ],
            "prohibited_patterns": ["definition-only", "mean-only shortcut"],
            "required_source_chunk_ids": ["stats_chunk"],
        },
    }
    service = build_service(db_session, FixedSearchService([]), [])

    assert service._quick_validate_high_rigor_mcq_candidate(
        problem_data=problem,
        request=request,
        high_rigor_profile=adversarial_high_rigor_mcq_profile(),
    ) == []


def test_answer_verifier_disabled_by_default_does_not_affect_generation(db_session, fixed_search):
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([valid_multiple_choice_problem()]),
        quality_checker=ProblemQualityChecker(),
        answer_verifier=RaisingAnswerVerifier(),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
    )

    assert len(result.problems) == 1
    assert result.quality_summary.passed == 1


def test_professor_grade_excellent_short_answer_with_distinct_rubric_scores_high(fixed_search):
    problem = valid_short_answer_problem()
    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            difficulty="medium",
            bloom_level="understand",
        ),
        chunks=fixed_search.chunks,
    )

    score = result.problem_data["professor_grade_score"]
    assert score["final_score"] >= 0.78
    assert score["rubric_quality"] > 0.75
    assert score["structural_score"] > 0
    assert score["pedagogical_score"] > 0
    assert score["grounding_score"] > 0
    assert score["assessment_design_score"] > 0


def test_professor_grade_generic_repeated_rubric_does_not_score_perfect(fixed_search):
    problem = valid_short_answer_problem()
    problem["rubric"] = [
        {
            "criterion": "정답을 설명했다.",
            "points": 1,
            "expected_evidence": ["가속도는 감소한다."],
            "common_mistakes": [],
            "partial_credit_rules": [],
        },
        {
            "criterion": "정답을 설명했다.",
            "points": 1,
            "expected_evidence": ["가속도는 감소한다."],
            "common_mistakes": [],
            "partial_credit_rules": [],
        },
    ]

    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
        ),
        chunks=fixed_search.chunks,
    )

    score = result.problem_data["professor_grade_score"]
    assert score["final_score"] < 1.0
    assert score["rubric_quality"] < 0.75
    assert "rubric expected_evidence is repetitive" in score["calibration_notes"]


def test_professor_grade_source_refs_with_weak_overlap_does_not_score_perfect(fixed_search):
    problem = valid_short_answer_problem()
    problem["question"] = "다음 조건에서 광합성 색소 분리 실험의 결론을 설명하시오."
    problem["answer"] = {
        "choice_id": None,
        "text": "엽록소와 카로티노이드의 이동 거리가 다르므로 색소가 분리된다.",
    }
    problem["explanation"] = "용매 전개와 색소 극성 차이가 결과를 만든다."

    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
        ),
        chunks=fixed_search.chunks,
    )

    score = result.problem_data["professor_grade_score"]
    assert score["source_grounding"] < 1.0
    assert score["final_score"] < 1.0
    assert "answer/explanation has weak overlap with cited source chunks" in score["calibration_notes"]


def test_professor_grade_item_model_mismatch_lowers_score(fixed_search):
    problem = valid_short_answer_problem()
    problem["item_model_id"] = "evidence_selection"

    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
        ),
        chunks=fixed_search.chunks,
    )

    score = result.problem_data["professor_grade_score"]
    assert score["cognitive_demand"] < result.problem_data["difficulty_profile"]["cognitive_demand_score"]
    assert "generated item_model_id differed from selected task model" in score["calibration_notes"]


def test_problem_item_stat_payload_validates_aggregate_counts():
    payload = ProblemItemStatPayload(
        problem_id="prob_001",
        document_id="doc_001",
        problem_type="multiple_choice",
        total_attempts=3,
        correct_count=2,
        incorrect_count=1,
        average_score=0.7,
        max_score=1,
        choice_selection_counts={"A": 2, "B": 1},
        mistake_type_counts={"concept_misunderstanding": 1},
    )

    assert payload.correct_count == 2

    with pytest.raises(ValidationError):
        ProblemItemStatPayload(
            problem_id="prob_001",
            document_id="doc_001",
            problem_type="multiple_choice",
            total_attempts=1,
            correct_count=1,
            incorrect_count=1,
        )


def build_service(db_session, search_service, problems):
    return ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=FixedProblemAgent(problems),
        quality_checker=ProblemQualityChecker(),
    )


def adversarial_high_rigor_mcq_request(*, problem_style: str = "exam_application") -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙", "질량과 가속도"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode=QualityMode.strict,
        problem_style=problem_style,
    )


def adversarial_high_rigor_mcq_profile() -> HighRigorGenerationProfile:
    return HighRigorGenerationProfile(
        enabled=True,
        intensity="advanced",
        multi_step_required=False,
        verification_level="enhanced",
    )


def strong_source_grounded_claim_mcq():
    return {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "제시된 F = ma 근거와 같은 힘 조건을 함께 볼 때, '질량이 큰 물체의 가속도는 더 작다'는 "
            "주장에 대한 판단으로 가장 타당한 것은?"
        ),
        "choices": [
            {
                "id": "A",
                "text": "타당하다. 같은 힘 조건에서 F = ma를 a = F/m로 해석하면 질량 증가는 가속도 감소로 이어진다.",
            },
            {
                "id": "B",
                "text": "타당하지 않다. 질량이 커지면 같은 힘 조건에서도 힘이 함께 커진다고 보아야 한다.",
            },
            {
                "id": "C",
                "text": "판단할 수 없다. F = ma는 힘과 가속도만 연결하고 질량 차이는 반영하지 않는다.",
            },
            {
                "id": "D",
                "text": "반대로 판단해야 한다. 질량이 큰 물체는 관성 때문에 같은 힘에서 가속도가 더 커진다.",
            },
        ],
        "answer": {
            "choice_id": "A",
            "text": "타당하다. 같은 힘 조건에서 F = ma를 a = F/m로 해석하면 질량 증가는 가속도 감소로 이어진다.",
        },
        "explanation": "강의 근거인 F = ma와 같은 힘 조건을 연결하면, 주장은 질량과 가속도의 반비례 관계에 맞다.",
        "choice_explanations": {
            "A": "F = ma 근거와 같은 힘 조건을 함께 적용한 판단이다.",
            "B": "같은 힘 조건을 무시하고 질량 증가가 힘 증가를 뜻한다고 잘못 바꿨다.",
            "C": "F = ma에서 질량 변수가 가속도 판단에 쓰인다는 근거를 놓쳤다.",
            "D": "관성 직관을 수식 관계보다 앞세워 관계 방향을 반대로 해석했다.",
        },
        "choice_diagnostics": [
            {
                "choice_id": "A",
                "is_correct": True,
                "misconception_id": None,
                "mistake_type": "none",
                "why_plausible": None,
                "repair_strategy": None,
                "followup_problem_type": None,
            },
            {
                "choice_id": "B",
                "is_correct": False,
                "misconception_id": "changed_fixed_force_condition",
                "mistake_type": "misread_question",
                "why_plausible": "질량이 큰 물체를 움직이려면 더 큰 힘이 필요하다는 일상 직관 때문에 그럴듯하다.",
                "repair_strategy": "먼저 같은 힘 조건을 고정하고 그다음 a = F/m 관계를 적용한다.",
                "followup_problem_type": "condition_mutation",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "ignores_mass_variable",
                "mistake_type": "missing_key_concept",
                "why_plausible": "공식을 힘과 가속도의 비례 관계로만 외우면 질량 변수의 역할을 빼먹을 수 있다.",
                "repair_strategy": "F = ma를 변형해 질량이 같은 힘에서 가속도에 주는 영향을 확인한다.",
                "followup_problem_type": "formula_reasoning",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "reversed_mass_acceleration_relation",
                "mistake_type": "concept_misunderstanding",
                "why_plausible": "관성을 '더 잘 움직인다'는 의미로 오해하면 관계 방향을 반대로 고를 수 있다.",
                "repair_strategy": "수식 근거로 질량 증가가 가속도 감소와 연결되는지 다시 비교한다.",
                "followup_problem_type": "concept_comparison",
            },
        ],
        "item_model_id": "evidence_selection",
        "concepts": ["뉴턴 제2법칙", "질량과 가속도"],
        "source_chunk_ids": ["chunk_001"],
        "mcq_plan": {
            "kernel_type": "evidence_to_claim",
            "source_rule_or_evidence": "F = ma connects force, mass, and acceleration under a fixed-force condition.",
            "concrete_scenario": "같은 힘 조건에서 질량이 큰 물체와 작은 물체의 가속도를 비교하는 사례",
            "correct_answer_claim": "같은 힘에서 F = ma를 적용하면 질량 증가가 가속도 감소로 이어진다.",
            "correct_answer_evidence_link": "F = ma and fixed force imply a = F/m.",
            "distractor_plans": [
                {
                    "misconception_id": "changed_fixed_force_condition",
                    "mistake_type": "misread_question",
                    "why_plausible": "질량이 큰 물체를 움직이려면 더 큰 힘이 필요하다는 일상 직관 때문에 그럴듯하다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "먼저 같은 힘 조건을 고정하고 그다음 a = F/m 관계를 적용한다.",
                },
                {
                    "misconception_id": "ignores_mass_variable",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "공식을 힘과 가속도의 비례 관계로만 외우면 질량 변수의 역할을 빼먹을 수 있다.",
                    "violated_or_ignored_evidence_role": "formula",
                    "repair_strategy": "F = ma를 변형해 질량이 같은 힘에서 가속도에 주는 영향을 확인한다.",
                },
                {
                    "misconception_id": "reversed_mass_acceleration_relation",
                    "mistake_type": "concept_misunderstanding",
                    "why_plausible": "관성을 '더 잘 움직인다'는 의미로 오해하면 관계 방향을 반대로 고를 수 있다.",
                    "violated_or_ignored_evidence_role": "rule",
                    "repair_strategy": "수식 근거로 질량 증가가 가속도 감소와 연결되는지 다시 비교한다.",
                },
            ],
            "prohibited_patterns": ["broad correctness", "generic diagnostics"],
            "required_source_chunk_ids": ["chunk_001"],
        },
    }


def adversarial_broad_correctness_mcq():
    problem = strong_source_grounded_claim_mcq()
    problem["question"] = "다음 중 옳은 것은?"
    return problem


def adversarial_definition_only_mcq():
    problem = strong_source_grounded_claim_mcq()
    problem["question"] = "뉴턴의 제2법칙의 정의는 무엇인가?"
    problem["choices"] = [
        {"id": "A", "text": "힘은 질량과 가속도의 곱이라는 법칙이다."},
        {"id": "B", "text": "힘은 속도와 시간의 곱이라는 법칙이다."},
        {"id": "C", "text": "질량은 가속도와 무관하다는 법칙이다."},
        {"id": "D", "text": "가속도는 힘과 무관하다는 법칙이다."},
    ]
    problem["answer"] = {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이라는 법칙이다."}
    problem["explanation"] = "자료에는 뉴턴의 제2법칙이 F = ma라고 제시되어 있다."
    return problem


def adversarial_keyword_match_mcq(source_text: str):
    problem = strong_source_grounded_claim_mcq()
    problem["question"] = "자료 문장과 일치하는 설명을 고르시오."
    problem["choices"] = [
        {"id": "A", "text": source_text},
        {"id": "B", "text": "자료와 관계없는 선택지이다."},
        {"id": "C", "text": "근거 없이 암기만 하면 고를 수 있는 선택지이다."},
        {"id": "D", "text": "반대 의미로만 구성된 선택지이다."},
    ]
    problem["answer"] = {"choice_id": "A", "text": source_text}
    problem["explanation"] = source_text
    problem["choice_explanations"] = {
        "A": source_text,
        "B": "자료와 관계없는 선택지이다.",
        "C": "근거 없이 암기만 하면 고를 수 있는 선택지이다.",
        "D": "반대 의미로만 구성된 선택지이다.",
    }
    problem["source_chunk_ids"] = ["chunk_keyword"]
    return problem


def adversarial_absolute_distractors_mcq():
    problem = strong_source_grounded_claim_mcq()
    problem["choices"][1]["text"] = "질량이 큰 물체의 가속도는 항상 더 커진다."
    problem["choices"][2]["text"] = "같은 힘 조건에서는 질량 차이가 절대 영향을 주지 않는다."
    problem["choices"][3]["text"] = "F = ma는 무조건 질량과 무관하게 적용된다."
    return problem


def adversarial_generic_diagnostics_mcq():
    problem = strong_source_grounded_claim_mcq()
    for diagnostic in problem["choice_diagnostics"]:
        if diagnostic["is_correct"] is not True:
            diagnostic["mistake_type"] = "generic_error"
            diagnostic["misconception_id"] = "same_generic"
            diagnostic["why_plausible"] = "헷갈릴 수 있다"
            diagnostic["repair_strategy"] = "다시 확인한다"
    return problem


def adversarial_evidence_analysis_without_source_link_mcq():
    problem = strong_source_grounded_claim_mcq()
    problem["choices"] = [
        {"id": "A", "text": "A 선택지가 맞다."},
        {"id": "B", "text": "B 선택지가 맞다."},
        {"id": "C", "text": "C 선택지가 맞다."},
        {"id": "D", "text": "D 선택지가 맞다."},
    ]
    problem["answer"] = {"choice_id": "A", "text": "A 선택지가 맞다."}
    problem["explanation"] = "A가 정답이다."
    problem["choice_explanations"] = {choice["id"]: "다시 확인한다." for choice in problem["choices"]}
    return problem


def valid_multiple_choice_problem():
    return {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
        "choices": [
            {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "B", "text": "힘은 질량과 무관하다."},
            {"id": "C", "text": "가속도는 항상 0이다."},
            {"id": "D", "text": "질량이 클수록 같은 힘에서 가속도는 커진다."},
        ],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "자료에는 뉴턴의 제2법칙이 F = ma라고 설명되어 있다.",
        "choice_explanations": {
            "A": "자료 내용과 일치한다.",
            "B": "자료에서는 힘이 질량과 가속도와 관련된다고 설명한다.",
            "C": "자료에 없는 설명이다.",
            "D": "같은 힘에서는 질량이 클수록 가속도가 작아진다.",
        },
        "rubric": None,
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
        "mcq_plan": {
            "kernel_type": "compute_from_given",
            "source_rule_or_evidence": "F = ma connects force, mass, and acceleration under a fixed-force condition.",
            "concrete_scenario": "같은 힘 조건에서 질량이 큰 물체와 작은 물체의 가속도를 비교하는 사례",
            "correct_answer_claim": "같은 힘에서는 질량이 큰 물체의 가속도가 더 작다.",
            "correct_answer_evidence_link": "F = ma and same force imply a = F/m.",
            "distractor_plans": [
                {
                    "misconception_id": "force_changes_with_mass",
                    "mistake_type": "misread_question",
                    "why_plausible": "질량이 커지면 힘도 커진다고 조건을 바꿔 읽으면 그럴듯해 보인다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "문제의 같은 힘 조건을 먼저 고정한 뒤 F = ma를 적용한다.",
                },
                {
                    "misconception_id": "ignores_mass_difference",
                    "mistake_type": "incomplete_answer",
                    "why_plausible": "같은 힘이라는 조건만 보면 두 물체가 같게 움직일 것처럼 보인다.",
                    "violated_or_ignored_evidence_role": "formula",
                    "repair_strategy": "같은 힘 조건 다음에 질량 차이가 가속도에 주는 영향을 비교한다.",
                },
                {
                    "misconception_id": "formula_relation_missing",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "공식을 단순 암기하면 질량과 가속도의 관계를 놓칠 수 있다.",
                    "violated_or_ignored_evidence_role": "rule",
                    "repair_strategy": "F = ma를 a = F/m 관계로 읽어 같은 힘에서 질량 효과를 확인한다.",
                },
            ],
            "prohibited_patterns": ["definition-only", "generic diagnostics"],
            "required_source_chunk_ids": ["chunk_001"],
        },
    }


def valid_high_rigor_multiple_choice_problem():
    return {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": (
            "같은 힘 조건에서 질량이 큰 물체와 작은 물체를 비교할 때 F = ma에 근거한 "
            "가속도 판단과 이유로 가장 타당한 것은?"
        ),
        "choices": [
            {"id": "A", "text": "질량이 큰 물체의 가속도가 더 작다. 같은 힘에서는 질량 증가가 가속도 감소로 이어진다."},
            {"id": "B", "text": "질량이 큰 물체의 가속도가 더 크다. 질량이 커질수록 힘도 함께 커진다고 본다."},
            {"id": "C", "text": "두 물체의 가속도는 같다. 같은 힘 조건만으로 가속도가 이미 결정된다고 본다."},
            {"id": "D", "text": "비교할 수 없다. F = ma에는 질량과 가속도를 연결하는 정보가 없다고 본다."},
        ],
        "answer": {
            "choice_id": "A",
            "text": "질량이 큰 물체의 가속도가 더 작다. 같은 힘에서는 질량 증가가 가속도 감소로 이어진다.",
        },
        "explanation": "자료의 F = ma 관계와 같은 힘 조건을 함께 적용하면 질량이 클수록 가속도는 작아진다.",
        "choice_explanations": {
            "A": "F = ma와 같은 힘 조건을 함께 적용한 판단이다.",
            "B": "같은 힘 조건인데 질량 증가가 힘 증가를 뜻한다고 잘못 해석했다.",
            "C": "힘이 같다는 조건만 보고 질량 차이가 가속도에 주는 영향을 빠뜨렸다.",
            "D": "F = ma에서 질량과 가속도가 연결된다는 핵심 관계를 놓쳤다.",
        },
        "choice_diagnostics": [
            {
                "choice_id": "A",
                "is_correct": True,
                "misconception_id": None,
                "mistake_type": "none",
                "why_plausible": None,
                "repair_strategy": None,
                "followup_problem_type": None,
            },
            {
                "choice_id": "B",
                "is_correct": False,
                "misconception_id": "force_changes_with_mass",
                "mistake_type": "misread_question",
                "why_plausible": "질량이 커지면 힘도 커진다고 조건을 바꿔 읽으면 그럴듯해 보인다.",
                "repair_strategy": "문제의 같은 힘 조건을 먼저 고정한 뒤 F = ma를 적용한다.",
                "followup_problem_type": "condition_check",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "ignores_mass_difference",
                "mistake_type": "incomplete_answer",
                "why_plausible": "같은 힘이라는 조건만 보면 두 물체가 같게 움직일 것처럼 보인다.",
                "repair_strategy": "같은 힘 조건 다음에 질량 차이가 가속도에 주는 영향을 비교한다.",
                "followup_problem_type": "concept_comparison",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "formula_relation_missing",
                "mistake_type": "missing_key_concept",
                "why_plausible": "공식을 단순 암기하면 질량과 가속도의 관계를 놓칠 수 있다.",
                "repair_strategy": "F = ma를 a = F/m 관계로 읽어 같은 힘에서 질량 효과를 확인한다.",
                "followup_problem_type": "formula_reasoning",
            },
        ],
        "rubric": None,
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
        "mcq_plan": {
            "kernel_type": "compute_from_given",
            "source_rule_or_evidence": "F = ma connects force, mass, and acceleration under a fixed-force condition.",
            "concrete_scenario": "같은 힘 조건에서 질량이 큰 물체와 작은 물체의 가속도를 비교하는 사례",
            "correct_answer_claim": "같은 힘에서는 질량이 큰 물체의 가속도가 더 작다.",
            "correct_answer_evidence_link": "F = ma and same force imply a = F/m.",
            "distractor_plans": [
                {
                    "misconception_id": "force_changes_with_mass",
                    "mistake_type": "misread_question",
                    "why_plausible": "질량이 커지면 힘도 커진다고 조건을 바꿔 읽으면 그럴듯해 보인다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "문제의 같은 힘 조건을 먼저 고정한 뒤 F = ma를 적용한다.",
                },
                {
                    "misconception_id": "ignores_mass_difference",
                    "mistake_type": "incomplete_answer",
                    "why_plausible": "같은 힘이라는 조건만 보면 두 물체가 같게 움직일 것처럼 보인다.",
                    "violated_or_ignored_evidence_role": "formula",
                    "repair_strategy": "같은 힘 조건 다음에 질량 차이가 가속도에 주는 영향을 비교한다.",
                },
                {
                    "misconception_id": "formula_relation_missing",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "공식을 단순 암기하면 질량과 가속도의 관계를 놓칠 수 있다.",
                    "violated_or_ignored_evidence_role": "rule",
                    "repair_strategy": "F = ma를 a = F/m 관계로 읽어 같은 힘에서 질량 효과를 확인한다.",
                },
            ],
            "prohibited_patterns": ["definition-only", "generic diagnostics"],
            "required_source_chunk_ids": ["chunk_001"],
        },
    }


def test_quality_checker_normalizes_dielectric_style_followup_problem_type():
    problem = valid_high_rigor_multiple_choice_problem()
    problem["choice_diagnostics"][1][
        "followup_problem_type"
    ] = "condition_mutation 비교 조건을 바꾸어 유전체 제거 상황을 다시 판단하는 후속 문항"
    checker = ProblemQualityChecker()

    errors = checker._validate_choice_diagnostics_shape(
        problem=problem,
        choice_ids=[choice["id"] for choice in problem["choices"]],
        answer_id=problem["answer"]["choice_id"],
    )

    assert errors == []
    assert problem["choice_diagnostics"][1]["followup_problem_type"] == "condition_change"


def _compute_from_given_contract_fixture():
    request = GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode=QualityMode.strict,
        problem_style="calculation_practice",
    )
    atom = ContentAtom(
        atom_id="atom_formula",
        atom_type=ContentAtomType.formula,
        source_chunk_id="formula_chunk",
        statement="For parallel capacitors, C_eq = C1 + C2.",
        evidence_quote="C_eq = C1 + C2",
        concepts=["capacitance"],
        confidence=0.95,
    )
    chunk = RetrievedChunk(
        chunk_id="formula_chunk",
        document_id="physics_doc",
        content="For parallel capacitors, C_eq = C1 + C2.",
        page=1,
        section_title="Capacitance",
        concepts=["capacitance"],
    )
    plan = ProblemKernelPlanner().plan(request=request, content_atoms=[atom])
    return request, atom, chunk, plan


def test_compute_from_given_contract_accepts_stem_values_formula_and_derivation():
    _request, atom, chunk, plan = _compute_from_given_contract_fixture()
    problem = {
        "document_id": "physics_doc",
        "type": "short_answer",
        "question": "병렬 연결에서 C1 = 2 uF, C2 = 3 uF일 때 등가 정전용량 C_eq를 구하시오.",
        "answer": {"choice_id": None, "text": "C_eq = 5 uF이다."},
        "explanation": "자료의 공식 C_eq = C1 + C2를 적용한다. C1 = 2 uF, C2 = 3 uF를 대입하면 2 + 3 = 5이므로 C_eq = 5 uF이다.",
        "rubric": [
            {"criterion": "공식 확인", "points": 1, "expected_evidence": ["C_eq = C1 + C2"]},
            {"criterion": "대입 계산", "points": 1, "expected_evidence": ["2 + 3 = 5"]},
        ],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[chunk],
    )

    assert report.generated_scenario_values_declared is True
    assert report.source_formula_or_rule_cited is True
    assert "missing_concrete_context" not in report.issues
    assert not any("derivation" in issue for issue in report.issues)


def test_compute_from_given_contract_rejects_missing_concrete_values():
    _request, atom, chunk, plan = _compute_from_given_contract_fixture()
    problem = {
        "document_id": "physics_doc",
        "type": "short_answer",
        "question": "병렬 연결에서 등가 정전용량 C_eq를 구하시오.",
        "answer": {"choice_id": None, "text": "C_eq = 5 uF이다."},
        "explanation": "자료의 공식 C_eq = C1 + C2를 적용한다.",
        "rubric": [{"criterion": "공식 확인", "points": 1, "expected_evidence": ["C_eq = C1 + C2"]}],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[chunk],
    )

    assert "missing_concrete_context" in report.issues
    assert any("number_not_given_in_stem" in issue for issue in report.issues)


def test_compute_from_given_contract_rejects_formula_without_derivation():
    _request, atom, chunk, plan = _compute_from_given_contract_fixture()
    problem = {
        "document_id": "physics_doc",
        "type": "short_answer",
        "question": "병렬 연결에서 C1 = 2 uF, C2 = 3 uF일 때 등가 정전용량 C_eq를 구하시오.",
        "answer": {"choice_id": None, "text": "C_eq = 5 uF이다."},
        "explanation": "자료의 공식 C_eq = C1 + C2를 사용하므로 답은 5 uF이다.",
        "rubric": [{"criterion": "공식 확인", "points": 1, "expected_evidence": ["C_eq = C1 + C2"]}],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[chunk],
    )

    assert "compute_from_given explanation must show derivation/substitution" in report.issues


def valid_short_answer_problem():
    return {
        "document_id": "doc_001",
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴 제2법칙을 적용해 같은 힘 조건에서 질량 차이가 가속도에 미치는 영향을 분석하시오.",
        "choices": None,
        "answer": {"choice_id": None, "text": "같은 힘에서는 질량이 클수록 가속도는 작아진다."},
        "explanation": "자료에는 뉴턴의 제2법칙과 질량, 가속도의 관계가 제시되어 있다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "자료 근거로 F = ma의 의미를 설명했다.",
                "points": 2,
                "expected_evidence": ["F = ma", "힘", "질량", "가속도"],
                "common_mistakes": ["공식만 쓰고 관계를 설명하지 않음"],
                "partial_credit_rules": ["핵심 변수 일부만 설명하면 부분 점수"],
            },
            {
                "criterion": "같은 힘 조건에서 질량과 가속도의 관계를 분석했다.",
                "points": 2,
                "expected_evidence": ["같은 힘", "질량이 클수록", "가속도는 작아진다"],
                "common_mistakes": ["관계를 반대로 설명함"],
                "partial_credit_rules": ["관계 방향이 맞으면 부분 점수"],
            },
        ],
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }


def valid_data_interpretation_problem():
    return {
        "document_id": "doc_enzyme",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "표를 바탕으로 효소 활성이 가장 높은 온도 조건을 찾고, 다른 조건과 비교해 해석하시오.",
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": "표에서 37도 조건의 효소 활성은 80으로, 25도의 40과 45도의 30보다 높다. 따라서 37도 조건에서 효소 활성이 가장 높다고 해석할 수 있다.",
        },
        "explanation": "수치 80, 40, 30을 비교해 37도 조건이 가장 높은 활성 조건임을 판단해야 한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "표의 37도, 25도, 45도 수치를 근거로 비교한다.",
                "points": 2,
                "expected_evidence": ["37도", "80", "25도", "40", "45도", "30"],
                "common_mistakes": ["수치 없이 온도 조건만 설명함"],
                "partial_credit_rules": ["가장 높은 조건만 맞히면 1점"],
            },
            {
                "criterion": "37도 조건의 효소 활성이 가장 높다는 결론을 해석한다.",
                "points": 2,
                "expected_evidence": ["가장 높다", "해석"],
                "common_mistakes": ["숫자 비교와 결론을 연결하지 않음"],
                "partial_credit_rules": ["결론만 쓰면 1점"],
            },
        ],
        "concepts": ["효소", "온도", "활성"],
        "source_chunk_ids": ["enzyme_table"],
    }


def valid_misconception_contrast_problem():
    return {
        "document_id": "doc_evap",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "증발의 특징으로 옳은 설명을 고르시오.",
        "choices": [
            {"id": "A", "text": "액체 표면에서 기체로 변하는 현상이다."},
            {"id": "B", "text": "액체 내부 전체에서만 기체로 변하는 현상이다."},
            {"id": "C", "text": "기체가 액체로 되돌아가는 현상이다."},
            {"id": "D", "text": "고체가 액체를 거치지 않고 기체로 변하는 현상이다."},
        ],
        "answer": {"choice_id": "A", "text": "액체 표면에서 기체로 변하는 현상이다."},
        "explanation": "자료는 증발이 액체 표면에서 기체로 변하는 현상이라고 설명한다.",
        "choice_explanations": {
            "A": "자료의 설명과 일치한다.",
            "B": "끓음의 조건을 증발과 혼동한 설명이다.",
            "C": "응결과 증발을 혼동한 설명이다.",
            "D": "승화와 증발을 혼동한 설명이다.",
        },
        "choice_diagnostics": [
            {
                "choice_id": "A",
                "is_correct": True,
                "misconception_id": None,
                "mistake_type": "none",
                "why_plausible": None,
                "repair_strategy": None,
                "followup_problem_type": None,
            },
            {
                "choice_id": "B",
                "is_correct": False,
                "misconception_id": "evap_boiling_confusion",
                "mistake_type": "term_confusion",
                "why_plausible": "끓음처럼 액체 내부 전체에서 일어나는 변화와 증발을 섞어 생각할 수 있다.",
                "repair_strategy": "증발은 표면, 끓음은 액체 내부까지 포함한다는 위치 차이를 비교한다.",
                "followup_problem_type": "misconception_contrast",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "evap_condensation_confusion",
                "mistake_type": "term_confusion",
                "why_plausible": "기체와 액체 사이의 변화 방향을 반대로 기억하면 고를 수 있다.",
                "repair_strategy": "액체에서 기체로 가는 방향과 기체에서 액체로 가는 방향을 화살표로 구분한다.",
                "followup_problem_type": "matching",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "evap_sublimation_confusion",
                "mistake_type": "term_confusion",
                "why_plausible": "상태 변화 이름을 외울 때 고체와 액체의 출발 상태를 혼동할 수 있다.",
                "repair_strategy": "각 상태 변화의 출발 상태와 도착 상태를 표로 정리한다.",
                "followup_problem_type": "matching",
            },
        ],
        "rubric": None,
        "concepts": ["증발"],
        "source_chunk_ids": ["evap_chunk"],
    }


def valid_evidence_selection_problem():
    return {
        "document_id": "doc_photo",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "analyze",
        "question": "자료에서 '광합성에는 빛 조건이 필요하다'는 주장을 가장 직접적으로 뒷받침하는 근거를 고르시오.",
        "choices": [
            {"id": "A", "text": "광합성은 빛 에너지를 이용한다."},
            {"id": "B", "text": "광합성은 포도당을 만든다."},
            {"id": "C", "text": "광합성은 물을 사용한다."},
            {"id": "D", "text": "광합성은 이산화탄소를 사용한다."},
        ],
        "answer": {"choice_id": "A", "text": "광합성은 빛 에너지를 이용한다."},
        "explanation": "A는 자료 근거인 '빛 에너지를 이용'을 빛이 필요하다는 주장과 직접 연결한다.",
        "choice_explanations": {
            "A": "자료 근거가 주장과 직접 연결된다.",
            "B": "포도당 생성은 광합성 결과이지 빛 필요성을 직접 뒷받침하는 근거는 아니다.",
            "C": "물 사용은 다른 조건 근거라서 빛 필요성 주장과 직접 연결되지 않는다.",
            "D": "이산화탄소 사용은 다른 조건 근거라서 빛 필요성 주장과 직접 연결되지 않는다.",
        },
        "choice_diagnostics": [
            {
                "choice_id": "A",
                "is_correct": True,
                "misconception_id": None,
                "mistake_type": "none",
                "why_plausible": None,
                "repair_strategy": None,
                "followup_problem_type": None,
            },
            {
                "choice_id": "B",
                "is_correct": False,
                "misconception_id": "photo_result_as_evidence",
                "mistake_type": "missing_key_concept",
                "why_plausible": "광합성의 산출물을 조건 근거로 착각하면 고를 수 있다.",
                "repair_strategy": "주장을 직접 뒷받침하는 단어와 단순 결과를 구분한다.",
                "followup_problem_type": "evidence_selection",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "photo_condition_confusion_water",
                "mistake_type": "missing_key_concept",
                "why_plausible": "조건이라는 말만 보고 물을 빛 조건의 근거처럼 볼 수 있다.",
                "repair_strategy": "주장 속 핵심어와 자료 근거의 핵심어가 맞는지 확인한다.",
                "followup_problem_type": "evidence_selection",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "photo_condition_confusion_carbon",
                "mistake_type": "missing_key_concept",
                "why_plausible": "광합성에 필요한 다른 조건을 빛 조건의 근거와 섞을 수 있다.",
                "repair_strategy": "자료 근거가 어떤 주장에 직접 연결되는지 한 문장으로 써 본다.",
                "followup_problem_type": "evidence_selection",
            },
        ],
        "rubric": None,
        "concepts": ["광합성", "빛 에너지"],
        "source_chunk_ids": ["photo_chunk"],
        "mcq_plan": {
            "kernel_type": "evidence_to_claim",
            "source_rule_or_evidence": "광합성은 빛 에너지를 이용한다.",
            "concrete_scenario": "자료의 광합성 설명에서 빛 조건 필요성을 뒷받침하는 근거를 고르는 사례",
            "correct_answer_claim": "빛 에너지를 이용한다는 근거가 빛 조건 필요성을 직접 뒷받침한다.",
            "correct_answer_evidence_link": "광합성은 빛 에너지를 이용한다.",
            "distractor_plans": [
                {
                    "misconception_id": "photo_result_as_evidence",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "광합성의 산출물을 조건 근거로 착각하면 고를 수 있다.",
                    "violated_or_ignored_evidence_role": "source_claim",
                    "repair_strategy": "주장을 직접 뒷받침하는 단어와 단순 결과를 구분한다.",
                },
                {
                    "misconception_id": "photo_condition_confusion_water",
                    "mistake_type": "concept_misunderstanding",
                    "why_plausible": "조건이라는 말만 보고 물을 빛 조건의 근거처럼 볼 수 있다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "주장 속 핵심어와 자료 근거의 핵심어가 맞는지 확인한다.",
                },
                {
                    "misconception_id": "photo_condition_confusion_carbon",
                    "mistake_type": "logic_error",
                    "why_plausible": "다른 조건을 빛 조건의 근거와 섞을 수 있다.",
                    "violated_or_ignored_evidence_role": "contrast",
                    "repair_strategy": "자료 근거가 어떤 주장에 직접 연결되는지 한 문장으로 써 본다.",
                },
            ],
            "prohibited_patterns": ["generic diagnostics", "unsupported evidence"],
            "required_source_chunk_ids": ["photo_chunk"],
        },
    }


def valid_evidence_claim_evaluation_problem():
    return {
        "document_id": "doc_photo",
        "type": "multiple_choice",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "자료 근거와 가장 잘 연결되는 판단은 무엇인가?",
        "choices": [
            {"id": "A", "text": "빛 에너지를 이용한다는 근거는 빛 조건이 광합성 판단에 중요하다는 결론과 연결된다."},
            {"id": "B", "text": "포도당 생성 결과만으로 빛 조건 필요성을 직접 판단할 수 있다."},
            {"id": "C", "text": "물 사용 근거는 빛 에너지 조건을 대체한다는 결론과 연결된다."},
            {"id": "D", "text": "이산화탄소 사용 근거는 빛이 불필요하다는 결론과 연결된다."},
        ],
        "answer": {
            "choice_id": "A",
            "text": "빛 에너지를 이용한다는 근거는 빛 조건이 광합성 판단에 중요하다는 결론과 연결된다.",
        },
        "explanation": "A는 자료 근거인 '빛 에너지를 이용'을 빛 조건이 중요하다는 결론과 직접 연결한다.",
        "choice_explanations": {
            "A": "자료의 빛 에너지 근거와 결론이 직접 연결된다.",
            "B": "포도당은 결과 근거라서 빛 조건 판단과 직접 연결되지 않는다.",
            "C": "물 사용 근거를 빛 에너지 조건의 대체 근거로 과잉 일반화했다.",
            "D": "이산화탄소 사용 근거를 빛 불필요 결론으로 잘못 연결했다.",
        },
        "choice_diagnostics": [
            {
                "choice_id": "A",
                "is_correct": True,
                "misconception_id": None,
                "mistake_type": "none",
                "why_plausible": None,
                "repair_strategy": None,
                "followup_problem_type": None,
            },
            {
                "choice_id": "B",
                "is_correct": False,
                "misconception_id": "result_as_direct_evidence",
                "mistake_type": "missing_key_concept",
                "why_plausible": "광합성 결과를 조건 근거처럼 읽으면 그럴듯하게 보인다.",
                "repair_strategy": "결론의 핵심 조건과 직접 연결되는 자료 표현을 먼저 찾는다.",
                "followup_problem_type": "evidence_selection",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "condition_substitution",
                "mistake_type": "concept_misunderstanding",
                "why_plausible": "물도 광합성에 쓰인다는 점을 빛 조건의 대체 근거로 넓혀 해석할 수 있다.",
                "repair_strategy": "자료 근거가 어느 조건을 직접 뒷받침하는지 조건별로 분리한다.",
                "followup_problem_type": "evidence_selection",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "wrong_evidence_to_claim",
                "mistake_type": "logic_error",
                "why_plausible": "다른 입력 조건 근거를 빛 조건 결론에 잘못 연결하면 선택할 수 있다.",
                "repair_strategy": "근거의 핵심어와 결론의 핵심어가 같은 조건을 가리키는지 확인한다.",
                "followup_problem_type": "evidence_selection",
            },
        ],
        "rubric": None,
        "concepts": ["광합성", "빛 에너지"],
        "source_chunk_ids": ["photo_chunk"],
        "mcq_plan": {
            "kernel_type": "evidence_to_claim",
            "source_rule_or_evidence": "광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만든다.",
            "concrete_scenario": "자료의 광합성 근거를 결론과 연결해 가장 타당한 판단을 고르는 사례",
            "correct_answer_claim": "빛 에너지를 이용한다는 근거는 빛 조건이 광합성 판단에 중요하다는 결론과 연결된다.",
            "correct_answer_evidence_link": "광합성은 빛 에너지를 이용한다.",
            "distractor_plans": [
                {
                    "misconception_id": "result_as_direct_evidence",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "광합성 결과를 조건 근거처럼 읽으면 그럴듯하게 보인다.",
                    "violated_or_ignored_evidence_role": "source_claim",
                    "repair_strategy": "결론의 핵심 조건과 직접 연결되는 자료 표현을 먼저 찾는다.",
                },
                {
                    "misconception_id": "condition_substitution",
                    "mistake_type": "concept_misunderstanding",
                    "why_plausible": "물도 광합성에 쓰인다는 점을 빛 조건의 대체 근거로 넓혀 해석할 수 있다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "자료 근거가 어느 조건을 직접 뒷받침하는지 조건별로 분리한다.",
                },
                {
                    "misconception_id": "wrong_evidence_to_claim",
                    "mistake_type": "logic_error",
                    "why_plausible": "다른 입력 조건 근거를 빛 조건 결론에 잘못 연결하면 선택할 수 있다.",
                    "violated_or_ignored_evidence_role": "evidence",
                    "repair_strategy": "근거의 핵심어와 결론의 핵심어가 같은 조건을 가리키는지 확인한다.",
                },
            ],
            "prohibited_patterns": ["generic diagnostics", "unsupported evidence"],
            "required_source_chunk_ids": ["photo_chunk"],
        },
    }
