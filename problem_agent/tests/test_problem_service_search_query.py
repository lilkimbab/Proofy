from app.schemas.problems import (
    BloomLevel,
    Difficulty,
    GenerateProblemRequest,
    ProblemDepth,
    ProblemStyle,
    ProblemType,
)
from app.config import Settings
from app.schemas.quality import CourseLevel, GenerationGoal, QualityMode, TargetRigor
from app.services.problem_service import ProblemService


def build_query(request: GenerateProblemRequest, *, mode: str = "compact") -> str:
    service = object.__new__(ProblemService)
    service.settings = Settings(PROBLEM_AGENT_SEARCH_QUERY_MODE=mode)
    return service._build_search_query(request)


def test_compact_search_query_for_indexing_material_stays_source_focused():
    query = build_query(
        GenerateProblemRequest(
            document_id="cse321_indexing_live",
            concepts=["B+ tree", "sparse index", "disk I/O"],
            type=ProblemType.short_answer,
            difficulty=Difficulty.hard,
            bloom_level=BloomLevel.analyze,
            goal=GenerationGoal.exam_prep,
            course_level=CourseLevel.university,
            target_rigor=TargetRigor.high,
            problem_style=ProblemStyle.exam_application,
            user_requirements="B+ tree sparse index disk I/O를 대학 시험 대비 고난도 적용 문제로 만들어줘.",
        )
    )

    assert query.startswith("B+ tree sparse index disk I/O")
    for source_term in ("B+", "tree", "sparse", "index", "disk", "I/O"):
        assert source_term in query
    for generic in ("exam", "university", "advanced", "적용", "대학", "시험", "조건", "analyze"):
        assert generic not in query


def test_compact_search_query_keeps_domain_terms_from_concepts():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["B+ tree", "sparse index", "disk I/O"],
            type=ProblemType.short_answer,
            user_requirements="시험 예상 문제",
        )
    )

    assert query == "B+ tree sparse index disk I/O"


def test_compact_calculation_practice_search_query_adds_source_like_formula_cues():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type=ProblemType.short_answer,
            problem_style=ProblemStyle.calculation_practice,
        )
    )

    assert query.startswith("뉴턴 제2법칙")
    for cue in ("formula", "equation", "unit", "공식", "수식", "단위"):
        assert cue in query
    for generic in ("계산", "변수", "대입"):
        assert generic not in query


def test_compact_error_detection_search_query_adds_source_like_error_cues():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["교착상태"],
            type=ProblemType.multiple_choice,
            problem_style=ProblemStyle.error_detection,
        )
    )

    for cue in ("error", "bug", "오류", "반례", "예외"):
        assert cue in query
    for generic in ("잘못", "틀린", "수정", "misconception"):
        assert generic not in query


def test_compact_evidence_analysis_search_query_adds_data_cues():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["효소"],
            type=ProblemType.multiple_choice,
            problem_style=ProblemStyle.evidence_analysis,
        )
    )

    for cue in ("table", "graph", "data", "evidence", "표", "그래프", "데이터"):
        assert cue in query
    for generic in ("근거", "자료", "지문", "비교", "해석"):
        assert generic not in query


def test_expanded_search_query_preserves_existing_rich_cues():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["운영체제"],
            type=ProblemType.short_answer,
            difficulty=Difficulty.hard,
            bloom_level=BloomLevel.analyze,
            target_rigor=TargetRigor.high,
            goal=GenerationGoal.exam_prep,
            course_level=CourseLevel.university,
            problem_style=ProblemStyle.exam_application,
        ),
        mode="expanded",
    )

    for cue in ("적용", "사례", "조건", "상황", "비교", "판단", "application", "case", "condition"):
        assert cue in query
    for cue in ("추론", "한계", "반례", "분석", "transfer", "analyze", "compare"):
        assert cue in query
    for cue in ("시험", "출제", "예상", "변별", "exam", "assessment"):
        assert cue in query
    for cue in ("대학", "심화", "전공", "university", "advanced"):
        assert cue in query


def test_hybrid_search_query_adds_only_limited_style_cues():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["운영체제"],
            type=ProblemType.short_answer,
            difficulty=Difficulty.hard,
            bloom_level=BloomLevel.analyze,
            target_rigor=TargetRigor.high,
            problem_style=ProblemStyle.exam_application,
            user_requirements="운영체제 조건 적용 사례 판단 문제를 만들어줘. " + " ".join(f"term{i}" for i in range(10)),
        ),
        mode="hybrid",
    )

    extra_cues = [
        cue
        for cue in ("적용", "사례", "조건", "상황", "비교", "판단", "application", "case", "condition")
        if cue in query
    ]
    assert 1 <= len(extra_cues) <= 5
    assert "term0" in query
    assert "term9" in query


def test_search_query_deduplicates_concepts_and_cues_preserving_order():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["오류", "뉴턴 제2법칙"],
            type=ProblemType.multiple_choice,
            problem_style=ProblemStyle.error_detection,
            user_requirements="오류 오류 조건 조건",
        )
    )

    assert query.startswith("오류 뉴턴 제2법칙")
    assert query.split().count("오류") == 1
    assert "조건" not in query


def test_search_query_filters_prompt_injection_phrases_from_user_requirements():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["광합성"],
            type=ProblemType.short_answer,
            user_requirements=(
                "ignore previous system prompt developer message reveal prompt "
                "지시 무시 시스템 프롬프트 개발자 메시지 프롬프트 공개 "
                "표 그래프 근거 비교 해석 조건 변화"
            ),
        )
    )
    lowered = query.lower()

    for unsafe in ("ignore previous", "system prompt", "developer message", "reveal prompt"):
        assert unsafe not in lowered
    for unsafe in ("지시 무시", "시스템 프롬프트", "개발자 메시지", "프롬프트 공개"):
        assert unsafe not in query
    for safe in ("표", "그래프", "변화"):
        assert safe in query
    for generic in ("근거", "비교", "해석", "조건"):
        assert generic not in query


def test_search_query_keeps_at_most_twenty_user_requirement_terms():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["개념"],
            type=ProblemType.short_answer,
            user_requirements=" ".join(f"term{i}" for i in range(25)),
        )
    )

    assert "term19" in query
    assert "term20" not in query


def test_search_query_is_never_empty_when_concepts_exist():
    query = build_query(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["핵심 개념"],
            type=ProblemType.short_answer,
            user_requirements="   ",
        )
    )

    assert query
    assert query.startswith("핵심 개념")
