import inspect

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    HighRigorGenerationProfile,
    HighRigorIntensity,
    QualityFlag,
    SourceGroundingMode,
    SourceGroundingProfile,
    VerificationLevel,
)
from app.services.high_rigor_generation_service import AdaptiveHighRigorPlanner
from app.services.problem_kernel_planner import ProblemKernelPlanner
from app.services.problem_service import ProblemService
from app.services.source_grounding_policy_service import SourceGroundingPolicyPlanner


class CapturingSearchService:
    def __init__(self, chunks):
        self.chunks = chunks
        self.last_kwargs = None

    def search_chunks(self, **kwargs):
        self.last_kwargs = kwargs
        return self.chunks

    def get_chunks_by_ids(self, **kwargs):
        return self.chunks


class CapturingProblemAgent:
    def __init__(self):
        self.last_kwargs = None
        self.last_chunks = None

    def generate(self, request, chunks, **kwargs):
        self.last_kwargs = kwargs
        self.last_chunks = chunks
        return [high_rigor_problem_payload(request, chunks)]


class FormulaProblemAgent:
    def __init__(self):
        self.last_chunks = None

    def generate(self, request, chunks, **kwargs):
        self.last_chunks = chunks
        return [
            {
                "document_id": request.document_id,
                "type": "short_answer",
                "difficulty": request.difficulty.value,
                "bloom_level": request.bloom_level.value,
                "question": "Using the source formula C = Q / V, compute C when Q = 10 and V = 2.",
                "choices": None,
                "answer": {"choice_id": None, "text": "C = 5"},
                "explanation": "Use the cited formula C = Q / V. Substituting Q = 10 and V = 2 gives 10 / 2 = 5.",
                "choice_explanations": None,
                "choice_diagnostics": None,
                "rubric": [
                    {
                        "criterion": "Uses C = Q / V from the source and substitutes Q = 10, V = 2.",
                        "points": 1,
                        "expected_evidence": ["C = Q / V", "10 / 2 = 5"],
                    }
                ],
                "concepts": request.concepts,
                "source_chunk_ids": ["formula_chunk"],
            }
        ]


class DefinitionProblemAgent:
    def __init__(self):
        self.last_request = None

    def generate(self, request, chunks, **kwargs):
        self.last_request = request
        return [
            {
                "document_id": request.document_id,
                "type": "short_answer",
                "difficulty": request.difficulty.value,
                "bloom_level": request.bloom_level.value,
                "question": "According to the source, what is capacitance?",
                "choices": None,
                "answer": {"choice_id": None, "text": "Capacitance is the ability to store charge."},
                "explanation": "The source definition says capacitance is the ability to store charge.",
                "choice_explanations": None,
                "choice_diagnostics": None,
                "rubric": [
                    {
                        "criterion": "States the source definition of capacitance.",
                        "points": 1,
                        "expected_evidence": ["capacitance", "ability", "store charge"],
                    }
                ],
                "concepts": request.concepts,
                "source_chunk_ids": ["def_chunk"],
            }
        ]


class SequentialProblemAgent:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = []

    def generate(self, request, chunks, **kwargs):
        self.calls.append(kwargs)
        return self.batches.pop(0)


class RepairingProblemAgent:
    def __init__(self, invalid_candidate, repaired_candidate):
        self.invalid_candidate = invalid_candidate
        self.repaired_candidate = repaired_candidate
        self.calls = []
        self.repair_calls = []
        self.last_generation_mode = "llm"
        self.last_prompt_char_count = 1000
        self.last_evidence_pack_atom_count = 1
        self.last_raw_context_char_count = 5000
        self.last_compressed_prompt_enabled = True

    def generate(self, request, chunks, **kwargs):
        self.calls.append(kwargs)
        return [self.invalid_candidate]

    def repair_candidate(self, request, invalid_candidate, validation_errors, chunks, **kwargs):
        self.repair_calls.append(
            {
                "invalid_candidate": invalid_candidate,
                "validation_errors": validation_errors,
                **kwargs,
            }
        )
        return [self.repaired_candidate]


def test_high_rigor_planner_detects_contextual_elite_assessment_request():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["함수", "미분", "극한"],
        type="short_answer",
        count=1,
        user_requirements="평가에서 변별력 있게 쓰일 만한 여러 개념을 섞은 고난도 문제를 만들어줘.",
    )

    profile = AdaptiveHighRigorPlanner().plan(request=request, chunks=math_chunks())

    assert profile.enabled is True
    assert profile.intensity == HighRigorIntensity.elite
    assert profile.multi_concept_required is True
    assert profile.multi_step_required is True
    assert profile.broad_search_required is True
    assert profile.verification_level == VerificationLevel.strict
    assert profile.recommended_top_k >= 12
    assert profile.candidate_multiplier >= 4
    assert "평가 대비" in profile.signals
    assert "최상위 난도" in profile.signals


def test_high_rigor_planner_does_not_enable_from_material_complexity_alone():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["함수", "미분", "극한"],
        type="short_answer",
        count=1,
    )

    profile = AdaptiveHighRigorPlanner().plan(request=request, chunks=math_chunks())

    assert profile.enabled is False


def test_problem_service_uses_adaptive_profile_for_search_and_agent(db_session):
    search_service = CapturingSearchService(math_chunks())
    problem_agent = CapturingProblemAgent()
    service = ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="full"),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="math_doc",
            concepts=["함수", "미분", "극한"],
            type="short_answer",
            count=1,
            user_requirements="평가에서 변별력 있게 쓰일 만한 여러 개념이 섞이고 여러 단계로 푸는 고난도 문제를 만들어줘.",
        ),
    )

    assert search_service.last_kwargs["top_k"] >= 12
    assert problem_agent.last_kwargs["candidate_count"] >= 4
    assert problem_agent.last_kwargs["high_rigor_profile"].intensity == HighRigorIntensity.elite
    assert result.high_rigor_profile.multi_step_required is True
    assert result.source_grounding_profile.mode == SourceGroundingMode.source_application
    assert result.quality_summary.passed == 1


def test_source_grounding_policy_keeps_simple_short_answer_source_grounded():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["세포막"],
        type="short_answer",
        count=1,
        user_requirements="세포막의 정의를 짧고 간단한 주관식으로 물어봐줘.",
    )

    profile = SourceGroundingPolicyPlanner().plan(request=request)

    assert profile.mode == SourceGroundingMode.source_grounded
    assert profile.allow_synthetic_context is False
    assert profile.allow_external_knowledge is False


def test_source_grounding_policy_detects_contextual_application_request():
    request = GenerateProblemRequest(
        document_id="policy_doc",
        concepts=["도덕적 해이", "인센티브"],
        type="short_answer",
        count=1,
        user_requirements="자료의 관계를 새로운 사례 상황에 적용하고 원인과 해결책을 분석하게 해줘.",
    )

    profile = SourceGroundingPolicyPlanner().plan(request=request)

    assert profile.mode == SourceGroundingMode.source_application
    assert profile.allow_synthetic_context is True
    assert profile.allow_external_knowledge is False


def test_source_grounding_policy_detects_contextual_model_extension_without_subject_specific_cues():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["핵심 개념", "조건 관계"],
        type="short_answer",
        count=1,
        user_requirements="평가 대비용으로 자료 개념을 바탕으로 새로운 조건을 만들고 분석과 판단이 필요한 문제를 만들어줘.",
    )

    profile = SourceGroundingPolicyPlanner().plan(request=request)

    assert profile.mode == SourceGroundingMode.model_extension
    assert profile.allow_synthetic_context is True
    assert profile.allow_external_knowledge is True


def test_problem_service_passes_contextual_source_grounding_profile(db_session):
    search_service = CapturingSearchService(math_chunks())
    problem_agent = CapturingProblemAgent()
    service = ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="math_doc",
            concepts=["함수", "미분", "극한"],
            type="short_answer",
            count=1,
            user_requirements="평가 대비용으로 자료 개념을 바탕으로 새로운 조건을 만들고 분석과 판단이 필요한 문제를 만들어줘.",
        ),
    )

    assert problem_agent.last_kwargs["source_grounding_profile"].mode == SourceGroundingMode.model_extension
    assert result.source_grounding_profile.mode == SourceGroundingMode.model_extension


def test_problem_service_rescues_low_rank_formula_chunk_for_kernel_context(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id=f"context_{index}",
            document_id="physics_doc",
            content=f"Capacitance context chunk {index} discusses plates, charge storage, and dielectric behavior.",
            concepts=["capacitance", "dielectric"],
            metadata={"score": 0.95 - index * 0.01},
        )
        for index in range(5)
    ]
    chunks.append(
        RetrievedChunk(
            chunk_id="formula_chunk",
            document_id="physics_doc",
            content="Equation: C = Q / V.",
            concepts=[],
            metadata={"score": 0.01},
        )
    )
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=FormulaProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=3,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )
    request = GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        difficulty="medium",
        bloom_level="apply",
        target_rigor="standard",
        quality_mode="standard",
        problem_style="calculation_practice",
    )
    raw_atoms = service.content_atom_extractor.extract(
        chunks=chunks,
        concepts=request.concepts,
        problem_style=request.problem_style,
    )
    plan = service.problem_kernel_planner.plan(request=request, content_atoms=raw_atoms)
    initial_context = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="capacitance",
    )
    selected_ids = service._selected_kernel_atom_chunk_ids(
        content_atoms=raw_atoms,
        problem_kernel_plan=plan,
    )
    rescued_context = service._rescue_kernel_atom_chunks(
        request=request,
        chunks=chunks,
        generation_chunks=initial_context,
        search_query="capacitance",
        selected_kernel_atom_chunk_ids=selected_ids,
    )

    initial_ids = {chunk.chunk_id for chunk in initial_context}
    rescued_ids = {chunk.chunk_id for chunk in rescued_context}
    selected_set = set(selected_ids)

    assert "formula_chunk" not in initial_ids
    assert selected_ids == ["formula_chunk"]
    assert "formula_chunk" in rescued_ids
    assert len((rescued_ids - initial_ids) & selected_set) == 1
    assert len(selected_set & rescued_ids) / len(selected_set) == 1.0


def test_problem_service_rescues_rule_chunk_for_diagnose_error_kernel(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id=f"generic_{index}",
            document_id="cpp_doc",
            content=f"General course overview chunk {index} about C++ programming examples.",
            concepts=["C++"],
            metadata={"score": 0.95 - index * 0.01},
        )
        for index in range(4)
    ]
    chunks.append(
        RetrievedChunk(
            chunk_id="rule_chunk",
            document_id="cpp_doc",
            content="Objects allocated dynamically must be released by the destructor; otherwise memory leaks remain.",
            concepts=[],
            metadata={"score": 0.01},
        )
    )
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=FormulaProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=2,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=2,
        ),
    )
    request = GenerateProblemRequest(
        document_id="cpp_doc",
        concepts=["resource management"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
        problem_style="error_detection",
    )
    raw_atoms = service.content_atom_extractor.extract(
        chunks=chunks,
        concepts=request.concepts,
        problem_style=request.problem_style,
    )
    plan = service.problem_kernel_planner.plan(request=request, content_atoms=raw_atoms)
    initial_context = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="resource management",
    )
    selected_ids = service._selected_kernel_atom_chunk_ids(
        content_atoms=raw_atoms,
        problem_kernel_plan=plan,
    )
    rescued_context = service._rescue_kernel_atom_chunks(
        request=request,
        chunks=chunks,
        generation_chunks=initial_context,
        search_query="resource management",
        selected_kernel_atom_chunk_ids=selected_ids,
    )

    assert plan.kernel_type.value == "diagnose_error"
    assert selected_ids == ["rule_chunk"]
    assert "rule_chunk" not in {chunk.chunk_id for chunk in initial_context}
    assert "rule_chunk" in {chunk.chunk_id for chunk in rescued_context}


def test_problem_service_atom_bonus_selects_evidence_claim_chunk(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id=f"generic_{index}",
            document_id="cv_doc",
            content=f"General visual learning overview chunk {index} with broad terminology.",
            concepts=["vision"],
            metadata={"score": 0.95 - index * 0.01},
        )
        for index in range(5)
    ]
    chunks.append(
        RetrievedChunk(
            chunk_id="evidence_chunk",
            document_id="cv_doc",
            content=(
                "Evidence from the figure supports the claim that segmentation assigns a label to each pixel, "
                "while detection localizes object boxes."
            ),
            concepts=["segmentation", "detection"],
            metadata={"score": 0.01},
        )
    )
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=FormulaProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=3,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )
    request = GenerateProblemRequest(
        document_id="cv_doc",
        concepts=["segmentation", "detection"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
        problem_style="evidence_analysis",
    )
    raw_atoms = service.content_atom_extractor.extract(
        chunks=chunks,
        concepts=request.concepts,
        problem_style=request.problem_style,
    )
    plan = service.problem_kernel_planner.plan(request=request, content_atoms=raw_atoms)
    selected_context = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="segmentation detection evidence",
        content_atoms=raw_atoms,
        problem_kernel_plan=plan,
    )

    assert plan.kernel_type.value == "evidence_to_claim"
    assert "evidence_chunk" in {chunk.chunk_id for chunk in selected_context}


def test_problem_service_kernel_rescue_replaces_low_score_generic_chunk_when_cap_exceeded(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id=f"context_{index}",
            document_id="physics_doc",
            content=f"Capacitance context chunk {index} discusses plates and charge storage.",
            concepts=["capacitance"],
            metadata={"score": 0.95 - index * 0.01},
        )
        for index in range(3)
    ]
    chunks.append(
        RetrievedChunk(
            chunk_id="formula_chunk",
            document_id="physics_doc",
            content="Equation: C = Q / V.",
            concepts=[],
            metadata={"score": 0.01},
        )
    )
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=FormulaProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=3,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )
    request = GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        problem_style="calculation_practice",
    )
    raw_atoms = service.content_atom_extractor.extract(
        chunks=chunks,
        concepts=request.concepts,
        problem_style=request.problem_style,
    )
    plan = service.problem_kernel_planner.plan(request=request, content_atoms=raw_atoms)
    initial_context = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="capacitance",
    )
    rescued_context = service._rescue_kernel_atom_chunks(
        request=request,
        chunks=chunks,
        generation_chunks=initial_context,
        search_query="capacitance",
        selected_kernel_atom_chunk_ids=service._selected_kernel_atom_chunk_ids(
            content_atoms=raw_atoms,
            problem_kernel_plan=plan,
        ),
    )
    rescued_ids = {chunk.chunk_id for chunk in rescued_context}

    assert len(rescued_context) == 3
    assert "context_0" in rescued_ids
    assert "formula_chunk" in rescued_ids
    assert "context_2" not in rescued_ids


def test_problem_service_calculates_selected_atom_recall_metrics(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id="context_chunk",
            document_id="physics_doc",
            content="Capacitance context discusses plates and charge storage.",
            concepts=["capacitance"],
            metadata={"score": 0.95},
        ),
        RetrievedChunk(
            chunk_id="formula_chunk",
            document_id="physics_doc",
            content="Equation: C = Q / V.",
            concepts=[],
            metadata={"score": 0.01},
        ),
    ]
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=FormulaProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=1,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=1,
        ),
    )
    request = GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        difficulty="medium",
        bloom_level="apply",
        target_rigor="standard",
        quality_mode="standard",
        problem_style="calculation_practice",
    )
    raw_atoms = service.content_atom_extractor.extract(
        chunks=chunks,
        concepts=request.concepts,
        problem_style=request.problem_style,
    )
    plan = service.problem_kernel_planner.plan(request=request, content_atoms=raw_atoms)
    selected_ids = service._selected_kernel_atom_ids(content_atoms=raw_atoms, problem_kernel_plan=plan)
    selected_chunk_ids = service._selected_kernel_atom_chunk_ids(
        content_atoms=raw_atoms,
        problem_kernel_plan=plan,
    )
    generation_chunks = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="capacitance",
        content_atoms=raw_atoms,
        problem_kernel_plan=plan,
    )
    generation_chunks = service._rescue_kernel_atom_chunks(
        request=request,
        chunks=chunks,
        generation_chunks=generation_chunks,
        search_query="capacitance",
        selected_kernel_atom_chunk_ids=selected_chunk_ids,
    )
    context_ids = {chunk.chunk_id for chunk in generation_chunks}
    context_atom_type_counts = {
        atom.atom_type.value: sum(
            1 for candidate in raw_atoms if candidate.atom_type == atom.atom_type and candidate.source_chunk_id in context_ids
        )
        for atom in raw_atoms
        if atom.source_chunk_id in context_ids
    }

    assert selected_ids
    assert selected_chunk_ids == ["formula_chunk"]
    assert len(set(selected_chunk_ids) & context_ids) / len(set(selected_chunk_ids)) == 1.0
    assert context_atom_type_counts["formula"] >= 1


def test_problem_service_context_packing_does_not_use_expected_chunk_ids():
    packing_source = inspect.getsource(ProblemService._select_generation_context_chunks)
    rescue_source = inspect.getsource(ProblemService._rescue_kernel_atom_chunks)

    assert "expected_chunk" not in packing_source
    assert "expected_chunk" not in rescue_source


def test_high_rigor_definition_only_source_fails_with_kernel_diagnostic(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id="def_chunk",
            document_id="physics_doc",
            content="Capacitance is a property describing the ability to store charge.",
            concepts=["capacitance"],
        )
    ]
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=DefinitionProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(OPENAI_API_KEY=None),
    )

    try:
        service.generate_problem_batch(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="physics_doc",
                concepts=["capacitance"],
                type="short_answer",
                count=1,
                difficulty="hard",
                bloom_level="analyze",
                target_rigor="high",
                quality_mode="strict",
                problem_style="calculation_practice",
            ),
        )
    except Exception as exc:
        assert "insufficient_source_structure" in str(exc)
        assert getattr(exc, "trace")["raw_content_atom_count"] >= 1
        assert getattr(exc, "trace")["kernel_planning_failure_reason"] == "insufficient_source_structure"
    else:
        raise AssertionError("expected kernel planning failure")


def test_high_rigor_kernel_failure_can_fallback_to_standard_when_enabled(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id="def_chunk",
            document_id="physics_doc",
            content="Capacitance is a property describing the ability to store charge.",
            concepts=["capacitance"],
        )
    ]
    problem_agent = DefinitionProblemAgent()
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            OPENAI_API_KEY=None,
            PROBLEM_AGENT_ALLOW_STANDARD_FALLBACK_ON_KERNEL_FAILURE=True,
        ),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="physics_doc",
            concepts=["capacitance"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            target_rigor="high",
            quality_mode="strict",
            problem_style="calculation_practice",
        ),
    )

    assert problem_agent.last_request.problem_style.value == "concept_check"
    assert problem_agent.last_request.quality_mode.value == "standard"
    assert result.quality_summary.passed == 1
    assert any("fallback applied" in warning for warning in result.quality_summary.warnings)


def test_high_rigor_quality_flags_weak_multi_concept_integration():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한", "연속"],
        type="short_answer",
        count=1,
        quality_mode="strict",
        user_requirements="여러 개념을 섞어서 고난도 문제를 만들어줘.",
    )
    problem = high_rigor_problem_payload(request, math_chunks())
    problem["question"] = "극한 조건만 이용해 값을 판단하시오."
    problem["answer"]["text"] = "극한에서는 x가 한 값에 가까워질 때 값의 변화를 본다."
    problem["explanation"] = "극한 조건만 확인하면 된다."
    problem["rubric"] = [
        {
            "criterion": "함수의 극한 조건을 설명했다.",
            "points": 2,
            "expected_evidence": ["극한"],
        }
    ]
    problem["source_chunk_ids"] = ["math_chunk_001"]

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=math_chunks(),
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            multi_concept_required=True,
            multi_step_required=True,
            signals=["복합 개념"],
        ),
    )

    assert is_valid is False
    assert QualityFlag.weak_concept_integration in report.flags
    assert any("weak_concept_integration" in error for error in errors)


def test_high_rigor_rejects_recall_style_problem_without_strict_mode():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한", "연속"],
        type="short_answer",
        count=1,
        user_requirements="여러 개념을 섞어서 고난도 문제를 만들어줘.",
    )
    problem = high_rigor_problem_payload(request, math_chunks())
    problem["question"] = "극한에서 가장 먼저 확인해야 하는 개념 두 가지를 서술하시오."
    problem["answer"]["text"] = "극한에서는 x가 한 값에 가까워질 때 함수값의 변화를 확인한다."
    problem["explanation"] = "극한의 기본 의미를 확인하는 문제이다."
    problem["rubric"] = [
        {
            "criterion": "극한의 기본 의미를 설명했다.",
            "points": 2,
            "expected_evidence": ["극한"],
            "common_mistakes": [],
            "partial_credit_rules": ["극한만 언급하면 부분 점수"],
        }
    ]
    problem["source_chunk_ids"] = ["math_chunk_001"]
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.35,
        "reasoning_steps_required": 1,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=math_chunks(),
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_concept_required=True,
            multi_step_required=True,
            signals=["복합 개념"],
        ),
    )

    assert is_valid is False
    assert QualityFlag.weak_application_fit in report.flags
    assert QualityFlag.low_cognitive_demand in report.flags
    assert any("weak_application_fit" in error for error in errors)


def test_high_rigor_allows_concrete_multi_step_reasoning_problem_without_strict_mode():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한", "연속"],
        type="short_answer",
        count=1,
        user_requirements="여러 개념을 섞어서 고난도 문제를 만들어줘.",
    )
    problem = high_rigor_problem_payload(request, math_chunks())
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.72,
        "reasoning_steps_required": 3,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=math_chunks(),
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_concept_required=True,
            multi_step_required=True,
            signals=["복합 개념"],
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.weak_application_fit not in report.flags
    assert QualityFlag.low_cognitive_demand not in report.flags


def test_high_rigor_multiple_choice_rejects_definition_only_question():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
    )
    problem = high_rigor_multiple_choice_payload(request)
    problem["question"] = "극한의 정의는 무엇인가?"
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.72,
        "reasoning_steps_required": 3,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert is_valid is False
    assert QualityFlag.definition_only_risk in report.flags
    assert any("recall or broad correctness" in error for error in errors)


def test_high_rigor_multiple_choice_rejects_broad_which_is_correct_stem():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    problem = high_rigor_multiple_choice_payload(request)
    problem["question"] = "다음 중 옳은 것은?"

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert is_valid is False
    assert QualityFlag.definition_only_risk in report.flags
    assert any("recall or broad correctness" in error for error in errors)


def test_high_rigor_multiple_choice_rejects_low_cognitive_demand_score():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한", "연속"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    problem = high_rigor_multiple_choice_payload(request)
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.49,
        "reasoning_steps_required": 3,
        "requires_comparison": True,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert is_valid is False
    assert QualityFlag.low_cognitive_demand in report.flags
    assert any("cognitive_demand_score" in error for error in errors)


def test_high_rigor_multiple_choice_rejects_single_reasoning_step():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한", "연속"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    problem = high_rigor_multiple_choice_payload(request)
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.72,
        "reasoning_steps_required": 1,
        "requires_comparison": True,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(multi_step_required=False),
    )

    assert is_valid is False
    assert QualityFlag.low_cognitive_demand in report.flags
    assert any("at least two reasoning steps" in error for error in errors)


def test_high_rigor_multiple_choice_allows_changed_condition_with_distinct_diagnostics():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한", "연속", "미분"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    problem = high_rigor_multiple_choice_payload(request)

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.weak_application_fit not in report.flags
    assert QualityFlag.low_cognitive_demand not in report.flags
    assert QualityFlag.item_model_quality_violation not in report.flags


def test_high_rigor_multiple_choice_rejects_generic_duplicate_distractor_diagnostics():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한", "연속", "미분"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    problem = high_rigor_multiple_choice_payload(request)
    for diagnostic in problem["choice_diagnostics"]:
        if diagnostic["is_correct"]:
            continue
        diagnostic["mistake_type"] = "concept_misunderstanding"
        diagnostic["misconception_id"] = "same_generic_misconception"
        diagnostic["why_plausible"] = "조건 관계를 충분히 구분하지 않으면 그럴듯하게 보일 수 있다."
        diagnostic["repair_strategy"] = "핵심 조건과 결론의 연결을 다시 확인한다."

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert is_valid is False
    assert QualityFlag.item_model_quality_violation in report.flags
    assert any("distractors must diagnose distinct" in error for error in errors)


def test_normal_medium_concept_check_multiple_choice_is_not_affected_by_high_rigor_checks():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["극한"],
        type="multiple_choice",
        count=1,
        difficulty="medium",
        bloom_level="understand",
    )
    problem = {
        "document_id": "math_doc",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "극한의 의미로 가장 적절한 것은?",
        "choices": [
            {"id": "A", "text": "입력이 한 값에 가까워질 때 함수값의 변화를 보는 개념이다."},
            {"id": "B", "text": "함수값이 언제나 같은 값을 갖는다는 뜻이다."},
            {"id": "C", "text": "도함수의 부호만으로 정의되는 개념이다."},
            {"id": "D", "text": "그래프의 넓이를 직접 계산하는 절차이다."},
        ],
        "answer": {"choice_id": "A", "text": "입력이 한 값에 가까워질 때 함수값의 변화를 보는 개념이다."},
        "explanation": "극한은 입력이 가까워질 때 함수값의 변화를 다룬다.",
        "choice_explanations": {
            "A": "자료의 극한 설명과 일치한다.",
            "B": "함수값이 항상 같다는 뜻은 아니다.",
            "C": "도함수 부호는 미분과 더 직접적으로 연결된다.",
            "D": "넓이 계산 절차는 적분 쪽 설명에 가깝다.",
        },
        "rubric": None,
        "concepts": ["극한"],
        "source_chunk_ids": ["math_chunk_001"],
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(enabled=False),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.low_cognitive_demand not in report.flags


def test_structured_application_request_allows_non_arithmetic_process_work():
    request = GenerateProblemRequest(
        document_id="econ_doc",
        concepts=["수요", "공급", "균형"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        user_requirements="구체 조건을 주고 균형 변화 과정을 계산/추적하게 만들어줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="econ_chunk_001",
            document_id="econ_doc",
            content=(
                "수요가 증가하고 공급이 일정하면 균형 가격과 균형 거래량은 상승한다. "
                "공급이 감소하면 균형 가격은 상승하지만 균형 거래량은 감소할 수 있다."
            ),
            page=1,
            section_title="수요와 공급의 변화",
            concepts=["수요", "공급", "균형"],
        )
    ]
    problem = {
        "document_id": "econ_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "소득 증가로 수요가 증가하고 공급은 일정한 상황에서 균형 가격과 균형 거래량의 "
            "변화 과정을 단계별로 추적하고, 공급 감소 상황과 비교하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "1단계로 수요 증가는 수요곡선을 오른쪽으로 이동시킨다. "
                "2단계로 공급이 일정하므로 새 균형은 더 높은 가격과 더 많은 거래량에서 형성된다. "
                "공급 감소와 비교하면 두 경우 모두 가격은 오르지만, 공급 감소에서는 거래량이 줄 수 있다는 점이 다르다."
            ),
        },
        "explanation": "조건 변화가 어느 곡선을 움직이는지 먼저 판단하고, 새 교차점의 방향을 비교한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "구체 조건에서 어떤 곡선이 이동하는지 판단한다.",
                "points": 2,
                "expected_evidence": ["소득 증가", "수요 증가", "공급 일정"],
                "common_mistakes": ["공급이 변한다고 잘못 판단함"],
                "partial_credit_rules": ["수요 증가만 맞히면 부분 점수"],
            },
            {
                "criterion": "균형 변화 과정을 단계별로 추적한다.",
                "points": 3,
                "expected_evidence": ["수요곡선 오른쪽 이동", "균형 가격 상승", "균형 거래량 증가"],
                "common_mistakes": ["가격과 거래량 중 하나만 결론냄"],
                "partial_credit_rules": ["가격 또는 거래량 변화만 맞히면 부분 점수"],
            },
            {
                "criterion": "공급 감소 상황과 비교해 차이를 설명한다.",
                "points": 2,
                "expected_evidence": ["공급 감소", "가격 상승", "거래량 감소 가능"],
                "common_mistakes": ["두 상황의 거래량 변화를 같다고 봄"],
                "partial_credit_rules": ["공통점만 쓰면 부분 점수"],
            },
        ],
        "concepts": ["수요", "공급", "균형"],
        "source_chunk_ids": ["econ_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.72,
            "reasoning_steps_required": 3,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["구체 조건", "단계 추적"],
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.weak_application_fit not in report.flags


def test_structured_application_request_rejects_shallow_step_labeling_without_application():
    request = GenerateProblemRequest(
        document_id="econ_doc",
        concepts=["수요", "공급", "균형"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        user_requirements="구체 조건을 주고 균형 변화 과정을 계산/추적하게 만들어줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="econ_chunk_001",
            document_id="econ_doc",
            content=(
                "수요가 증가하고 공급이 일정하면 균형 가격과 균형 거래량은 상승한다. "
                "공급이 감소하면 균형 가격은 상승하지만 균형 거래량은 감소할 수 있다."
            ),
            page=1,
            section_title="수요와 공급의 변화",
            concepts=["수요", "공급", "균형"],
        )
    ]
    problem = {
        "document_id": "econ_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "수요, 공급, 균형의 개념을 1단계, 2단계, 3단계로 나누어 설명하시오.",
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": "1단계: 수요는 사고자 하는 양이다. 2단계: 공급은 팔고자 하는 양이다. 3단계: 균형은 두 양이 만나는 지점이다.",
        },
        "explanation": "각 개념의 정의를 순서대로 정리하면 된다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "수요의 뜻을 설명한다.",
                "points": 1,
                "expected_evidence": ["수요"],
                "common_mistakes": [],
                "partial_credit_rules": ["수요를 언급하면 부분 점수"],
            },
            {
                "criterion": "공급의 뜻을 설명한다.",
                "points": 1,
                "expected_evidence": ["공급"],
                "common_mistakes": [],
                "partial_credit_rules": ["공급을 언급하면 부분 점수"],
            },
        ],
        "concepts": ["수요", "공급", "균형"],
        "source_chunk_ids": ["econ_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.72,
            "reasoning_steps_required": 3,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["구체 조건", "단계 추적"],
        ),
    )

    assert is_valid is False
    assert QualityFlag.weak_application_fit in report.flags
    assert any("weak_application_fit" in error for error in errors)


def test_high_rigor_allows_synthetic_application_context_when_source_supports_transfer():
    request = GenerateProblemRequest(
        document_id="heap_doc",
        concepts=["heapsort", "build max heap"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        quality_mode="strict",
        user_requirements="작은 예제 배열은 네가 직접 만들어서 Build-Max-Heap의 과정을 분석하게 해줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="heap_chunk_001",
            document_id="heap_doc",
            content=(
                "Build-Max-Heap은 마지막 내부 노드부터 루트까지 Max-Heapify를 수행한다. "
                "Max-Heapify는 부모가 자식보다 크거나 같도록 heap property를 회복한다."
            ),
            page=1,
            section_title="Building a Max-Heap",
            concepts=["heapsort", "build max heap", "max heapify"],
        )
    ]
    problem = {
        "document_id": "heap_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "새 예제 배열 A=[6,13,2,10,7]에 대해 Build-Max-Heap을 수행하고, "
            "각 Max-Heapify 호출 후 배열과 heap property 회복 이유를 설명하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "i=2에서는 13이 자식 10,7보다 커서 변화가 없다. "
                "i=1에서는 6과 13을 교환하고, 내려간 6은 자식 10과 교환되어 [13,10,2,6,7]이 된다. "
                "각 단계는 더 큰 자식을 올려 부모가 자식보다 크거나 같게 만드는 규칙을 적용한다."
            ),
        },
        "explanation": "자료의 Build-Max-Heap 절차와 Max-Heapify 규칙을 새 배열에 적용한 문제이다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "새 예제 배열의 중간 상태를 계산한다.",
                "points": 2,
                "expected_evidence": ["A=[6,13,2,10,7]", "i=2 변화 없음", "[13,10,2,6,7]"],
                "common_mistakes": ["자료의 예제 배열만 그대로 사용함"],
                "partial_credit_rules": ["최종 heap만 맞으면 부분 점수"],
            },
            {
                "criterion": "Max-Heapify 규칙을 적용해 결과를 정당화한다.",
                "points": 2,
                "expected_evidence": ["더 큰 자식", "heap property", "부모가 자식보다 크거나 같음"],
                "common_mistakes": ["교환 결과만 쓰고 규칙을 설명하지 않음"],
                "partial_credit_rules": ["규칙만 언급하면 부분 점수"],
            },
        ],
        "concepts": ["heapsort", "build max heap"],
        "source_chunk_ids": ["heap_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.72,
            "reasoning_steps_required": 3,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["새 예제", "단계 추적"],
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.unsupported_source not in report.flags


def test_high_rigor_allows_synthetic_case_context_beyond_numbers():
    request = GenerateProblemRequest(
        document_id="policy_doc",
        concepts=["도덕적 해이", "인센티브", "감시 비용"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        quality_mode="strict",
        user_requirements="자료를 바탕으로 새 사례 지문을 만들어서 원인과 해결책을 분석하게 해줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="policy_chunk_001",
            document_id="policy_doc",
            content=(
                "도덕적 해이는 행동을 직접 관찰하기 어렵고 감시 비용이 클 때 발생한다. "
                "인센티브 설계와 결과 기반 보상은 행동을 바꾸는 데 사용된다."
            ),
            page=1,
            section_title="정보 비대칭과 인센티브",
            concepts=["도덕적 해이", "인센티브", "감시 비용"],
        )
    ]
    problem = {
        "document_id": "policy_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "새 사례: 재택근무 프로젝트에서 관리자는 직원의 실제 작업 과정을 직접 보기 어렵고, "
            "감시 시스템 도입 비용도 크다. 이 상황에서 도덕적 해이가 발생할 수 있는 원인을 분석하고, "
            "인센티브 설계로 완화하는 방안을 제시하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "행동을 직접 관찰하기 어렵고 감시 비용이 크므로 직원이 노력을 줄여도 관리자가 즉시 알기 어렵다. "
                "이것이 도덕적 해이의 원인이다. 해결책은 작업 시간 자체를 감시하는 대신 산출물 품질, 마감 준수, 팀 기여도처럼 "
                "관찰 가능한 결과와 보상을 연결하는 것이다. 다만 단일 결과 지표만 쓰면 품질을 희생할 수 있으므로 여러 성과 기준을 함께 두어야 한다."
            ),
        },
        "explanation": "자료의 조건인 관찰 어려움과 감시 비용을 새 사례에 적용하고, 인센티브 설계 원리로 해결책을 도출한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "새 사례에서 도덕적 해이 발생 조건을 분석한다.",
                "points": 2,
                "expected_evidence": ["행동 관찰 어려움", "감시 비용", "노력 감소 가능성"],
                "common_mistakes": ["도덕적 해이를 단순한 게으름으로만 설명함"],
                "partial_credit_rules": ["관찰 어려움만 언급하면 부분 점수"],
            },
            {
                "criterion": "자료의 인센티브 설계 원리를 적용한다.",
                "points": 2,
                "expected_evidence": ["결과 기반 보상", "산출물 품질", "마감 준수"],
                "common_mistakes": ["감시 강화만 해결책으로 제시함"],
                "partial_credit_rules": ["결과 지표만 언급하면 부분 점수"],
            },
            {
                "criterion": "해결책의 한계나 부작용을 판단한다.",
                "points": 1,
                "expected_evidence": ["단일 지표의 부작용", "여러 성과 기준"],
                "common_mistakes": ["인센티브가 항상 완벽하다고 봄"],
                "partial_credit_rules": ["한계만 언급하면 부분 점수"],
            },
        ],
        "concepts": ["도덕적 해이", "인센티브", "감시 비용"],
        "source_chunk_ids": ["policy_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.74,
            "reasoning_steps_required": 3,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["새 사례", "분석"],
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.unsupported_source not in report.flags


def test_model_extension_allows_self_contained_new_context_when_source_anchor_exists():
    request = GenerateProblemRequest(
        document_id="policy_doc",
        concepts=["인센티브", "정보 비대칭"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        quality_mode="strict",
        user_requirements="평가 대비용으로 새 조건을 만들고 분석과 판단이 필요한 문제를 만들어줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="policy_chunk_001",
            document_id="policy_doc",
            content=(
                "정보 비대칭이 있으면 한쪽의 행동이나 품질을 상대방이 완전히 관찰하기 어렵다. "
                "인센티브 설계는 관찰 가능한 결과와 보상을 연결해 행동을 유도한다."
            ),
            page=1,
            section_title="정보 비대칭과 인센티브",
            concepts=["정보 비대칭", "인센티브"],
        )
    ]
    problem = {
        "document_id": "policy_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "다음 조건에서 판단하시오. 플랫폼이 판매자의 실제 품질 관리 노력은 직접 볼 수 없지만 "
            "반품률과 재구매율은 관찰할 수 있다고 가정한다. 이 조건에서 정보 비대칭이 어떤 문제를 만들고, "
            "인센티브 설계를 어떻게 바꾸면 판매자 행동을 개선할 수 있는지 분석하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "품질 관리 노력이 보이지 않으므로 판매자는 단기 비용을 줄이기 위해 노력을 낮출 수 있다. "
                "반품률과 재구매율처럼 관찰 가능한 결과를 보상과 제재에 연결하면 숨은 행동을 간접적으로 통제할 수 있다. "
                "다만 한 지표만 쓰면 조작이나 부작용이 생길 수 있으므로 여러 결과 지표를 함께 써야 한다."
            ),
        },
        "explanation": "자료의 정보 비대칭과 인센티브 관계를 새 플랫폼 조건에 적용해 판단하는 문제이다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "새 조건에서 정보 비대칭 문제를 분석한다.",
                "points": 2,
                "expected_evidence": ["품질 관리 노력 관찰 어려움", "숨은 행동", "단기 비용"],
                "common_mistakes": ["정보 비대칭을 단순 정보 부족으로만 설명함"],
                "partial_credit_rules": ["관찰 어려움만 언급하면 부분 점수"],
            },
            {
                "criterion": "인센티브 설계의 적용과 한계를 판단한다.",
                "points": 2,
                "expected_evidence": ["반품률", "재구매율", "보상과 제재", "여러 결과 지표"],
                "common_mistakes": ["보상 연결만 쓰고 부작용을 판단하지 않음"],
                "partial_credit_rules": ["관찰 가능한 지표만 제시하면 부분 점수"],
            },
        ],
        "concepts": ["인센티브", "정보 비대칭"],
        "source_chunk_ids": ["policy_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.74,
            "reasoning_steps_required": 3,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["평가 대비", "확장 설계"],
        ),
        source_grounding_profile=SourceGroundingProfile(
            mode=SourceGroundingMode.model_extension,
            allow_synthetic_context=True,
            allow_external_knowledge=True,
            strict_source_rejection=False,
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.unsupported_source not in report.flags


def test_model_extension_rejects_context_free_recall_problem():
    request = GenerateProblemRequest(
        document_id="policy_doc",
        concepts=["인센티브", "정보 비대칭"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        quality_mode="strict",
        user_requirements="평가 대비용으로 새 조건을 만들고 분석과 판단이 필요한 문제를 만들어줘.",
    )
    chunks = [
        RetrievedChunk(
            chunk_id="policy_chunk_001",
            document_id="policy_doc",
            content="정보 비대칭에서는 한쪽이 더 많은 정보를 가진다. 인센티브는 행동을 유도한다.",
            page=1,
            section_title="정보 비대칭과 인센티브",
            concepts=["정보 비대칭", "인센티브"],
        )
    ]
    problem = {
        "document_id": "policy_doc",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "정보 비대칭의 정의를 쓰시오.",
        "choices": None,
        "answer": {"choice_id": None, "text": "정보 비대칭은 한쪽이 더 많은 정보를 가진 상황이다."},
        "explanation": "정의를 확인하는 문제이다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "정의를 썼다.",
                "points": 1,
                "expected_evidence": ["한쪽이 더 많은 정보"],
                "common_mistakes": [],
                "partial_credit_rules": [],
            }
        ],
        "concepts": ["정보 비대칭"],
        "source_chunk_ids": ["policy_chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.2,
            "reasoning_steps_required": 1,
        },
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_step_required=True,
            signals=["평가 대비", "확장 설계"],
        ),
        source_grounding_profile=SourceGroundingProfile(
            mode=SourceGroundingMode.model_extension,
            allow_synthetic_context=True,
            allow_external_knowledge=True,
            strict_source_rejection=False,
        ),
    )

    assert is_valid is False
    assert QualityFlag.item_model_quality_violation in report.flags
    assert any("model-extension" in error for error in errors)


def test_high_rigor_treats_ai_like_wording_as_warning_when_content_passes():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한", "연속"],
        type="short_answer",
        count=1,
        quality_mode="strict",
        user_requirements="여러 개념을 섞어서 고난도 문제를 만들어줘.",
    )
    problem = high_rigor_problem_payload(request, math_chunks())
    problem["question"] += " 자료에서 어떤 관계를 중심으로 설명되는가?"
    problem["explanation"] += " 핵심 개념을 확인하는 개념이다."
    problem["difficulty_profile"] = {
        "cognitive_demand_score": 0.72,
        "reasoning_steps_required": 3,
    }

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=math_chunks(),
        request=request,
        high_rigor_profile=HighRigorGenerationProfile(
            enabled=True,
            intensity=HighRigorIntensity.advanced,
            multi_concept_required=True,
            multi_step_required=True,
            signals=["복합 개념"],
        ),
    )

    assert is_valid is True
    assert errors == []
    assert QualityFlag.ai_like_wording in report.flags


def test_problem_service_retries_high_rigor_generation_with_quality_feedback(db_session):
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한", "연속"],
        type="short_answer",
        count=1,
        user_requirements="여러 개념을 섞어서 고난도 문제를 만들어줘.",
    )
    bad_problem = high_rigor_problem_payload(request, math_chunks())
    bad_problem["difficulty"] = "hard"
    bad_problem["bloom_level"] = "analyze"
    bad_problem["question"] = "극한에서 가장 먼저 확인해야 하는 개념 두 가지를 서술하시오."
    bad_problem["answer"]["text"] = "극한에서는 x가 한 값에 가까워질 때 함수값의 변화를 확인한다."
    bad_problem["explanation"] = "극한의 기본 의미를 확인하는 문제이다."
    bad_problem["rubric"] = [
        {
            "criterion": "극한의 기본 의미를 설명했다.",
            "points": 2,
            "expected_evidence": ["극한"],
            "common_mistakes": [],
            "partial_credit_rules": ["극한만 언급하면 부분 점수"],
        }
    ]
    bad_problem["source_chunk_ids"] = ["math_chunk_001"]

    good_problem = high_rigor_problem_payload(request, math_chunks())
    good_problem["difficulty"] = "hard"
    good_problem["bloom_level"] = "analyze"
    problem_agent = SequentialProblemAgent([[bad_problem], [good_problem]])
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(user_id="user_001", request=request)

    assert result.quality_summary.passed == 1
    assert result.quality_summary.rejected == 1
    assert len(problem_agent.calls) == 2
    assert problem_agent.calls[0].get("quality_feedback") is None
    assert any("Add a concrete condition" in item for item in problem_agent.calls[1]["quality_feedback"])
    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.actual_retry_count == 1
    assert performance.rejection_category_counts == {"missing_concrete_context": 1}
    assert "retry attempts used: 1" in result.quality_summary.warnings
    assert performance.attempts[0].new_rejection_category_counts == {"missing_concrete_context": 1}
    assert performance.attempts[1].retry_feedback_categories
    assert "연속 조건과 도함수의 부호 변화" in result.problems[0].question


def test_retry_feedback_summarizes_concrete_context_error(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    error = (
        "high-rigor multiple-choice item must include a concrete condition, case, "
        "source evidence, input, data, code, or changed scenario"
    )
    feedback = service._summarize_retry_feedback([error])

    assert service._categorize_generation_error(error) == "missing_concrete_context"
    assert feedback == [
        "Add a concrete condition, case, input, table, code, changed scenario, or flawed claim to the stem."
    ]


def test_retry_feedback_summarizes_distractor_and_duplicate_errors(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    weak_diagnostics_error = (
        "high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures"
    )
    duplicate_error = "problem is too similar to a previously generated problem"
    feedback = service._summarize_retry_feedback([weak_diagnostics_error, duplicate_error])

    assert service._categorize_generation_error(weak_diagnostics_error) == "weak_distractor_diagnostics"
    assert service._categorize_generation_error(duplicate_error) == "duplicate_reasoning_template"
    assert (
        "Make wrong choices diagnose distinct misconceptions or reasoning failures with why_plausible and repair_strategy."
        in feedback
    )
    assert "Do not create another variant with the same reasoning template or changed numbers only." in feedback


def test_retry_feedback_summarizes_evidence_analysis_and_testwise_errors(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    evidence_error = (
        "evidence_analysis MCQ must ask for source-evidence selection or source-grounded claim evaluation"
    )
    testwise_error = "multiple distractors use absolute wording that may cue test-wise guessing"
    feedback = service._summarize_retry_feedback([evidence_error, testwise_error])

    assert service._categorize_generation_error(evidence_error) == "evidence_analysis_structure"
    assert service._categorize_generation_error(testwise_error) == "testwise_option_cue"
    assert any("source-evidence selection or source-grounded claim evaluation" in item for item in feedback)
    assert any("avoid absolute words" in item for item in feedback)


def test_high_rigor_mcq_candidate_without_plan_fails_quick_validation(db_session):
    request = high_rigor_mcq_request()
    problem = high_rigor_multiple_choice_payload(request)
    problem.pop("mcq_plan", None)
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    errors = service._quick_validate_high_rigor_mcq_candidate(
        problem_data=problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert errors == ["missing_mcq_plan: high-rigor multiple_choice candidate must include mcq_plan"]


def test_high_rigor_mcq_candidate_with_repeated_distractor_mistake_type_fails(db_session):
    request = high_rigor_mcq_request()
    problem = high_rigor_multiple_choice_payload(request)
    for distractor in problem["mcq_plan"]["distractor_plans"]:
        distractor["mistake_type"] = "same_error"
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    errors = service._quick_validate_high_rigor_mcq_candidate(
        problem_data=problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert "indistinct_distractors: distractor mistake_type values must be distinct" in errors


def test_high_rigor_mcq_candidate_with_distinct_plan_passes_quick_validation(db_session):
    request = high_rigor_mcq_request()
    problem = high_rigor_multiple_choice_payload(request)
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    errors = service._quick_validate_high_rigor_mcq_candidate(
        problem_data=problem,
        request=request,
        high_rigor_profile=high_rigor_multiple_choice_profile(),
    )

    assert errors == []


def test_retry_feedback_summarizes_mcq_plan_categories_concisely(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
    )

    errors = [
        "missing_mcq_plan: high-rigor multiple_choice candidate must include mcq_plan",
        "indistinct_distractors: distractor mistake_type values must be distinct",
        "answer_not_evidence_bound: correct answer claim is not tied to the evidence link",
    ]
    feedback = service._summarize_retry_feedback(errors)

    assert [service._categorize_generation_error(error) for error in errors] == [
        "missing_mcq_plan",
        "indistinct_distractors",
        "answer_not_evidence_bound",
    ]
    assert feedback == [
        "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording."
    ]


def test_high_rigor_openai_candidate_count_has_minimum_three(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            LLM_FALLBACK_ENABLED=True,
            PROBLEM_AGENT_COST_PROFILE="full",
        ),
    )
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )

    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 3


def test_high_rigor_multiple_choice_candidate_count_has_minimum_three(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            LLM_FALLBACK_ENABLED=True,
            PROBLEM_AGENT_COST_PROFILE="full",
        ),
    )
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )

    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 3


def test_high_rigor_multiple_choice_candidate_count_respects_configured_minimum(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            LLM_FALLBACK_ENABLED=True,
            PROBLEM_AGENT_COST_PROFILE="full",
            PROBLEM_AGENT_HIGH_RIGOR_MCQ_MIN_CANDIDATES=4,
        ),
    )
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )

    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 4


def test_gemini_high_rigor_candidate_expansion_is_opt_in(db_session):
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    default_service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key", PROBLEM_AGENT_COST_PROFILE="full"),
    )
    expanded_service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="test-key",
            PROBLEM_AGENT_COST_PROFILE="full",
            LLM_GEMINI_HIGH_RIGOR_CANDIDATE_MULTIPLIER=2,
        ),
    )

    assert default_service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) == 1
    assert expanded_service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 3


def test_gemini_high_rigor_multiple_choice_uses_minimum_candidates(db_session):
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key", PROBLEM_AGENT_COST_PROFILE="full"),
    )

    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 3


def test_high_rigor_multiple_choice_retry_count_uses_setting(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="full", PROBLEM_AGENT_HIGH_RIGOR_MCQ_RETRY_COUNT=4),
    )
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
    )

    assert service._quality_retry_count(request=request, high_rigor_profile=HighRigorGenerationProfile(enabled=True)) == 4


def test_cost_profile_model_routing_for_high_rigor_generation():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
    )
    settings = Settings(
        PROBLEM_MODEL="gpt-cheap",
        PROBLEM_QUALITY_MODEL="gpt-premium",
        PROBLEM_AGENT_ALLOW_PREMIUM_ESCALATION=True,
    )
    agent = ProblemAgent(settings=settings)

    assert agent._select_problem_model(request, cost_profile="cheap") == "gpt-cheap"
    assert agent._select_problem_model(request, cost_profile="balanced") == "gpt-cheap"
    assert (
        agent._select_problem_model(request, cost_profile="balanced", premium_escalation=True)
        == "gpt-premium"
    )
    assert agent._select_problem_model(request, cost_profile="full") == "gpt-premium"


def test_cost_profile_candidate_and_retry_counts(db_session):
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["미분", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
    )
    cheap_service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="cheap"),
    )
    balanced_service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="balanced"),
    )

    assert cheap_service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) == 1
    assert cheap_service._quality_retry_count(request=request, high_rigor_profile=HighRigorGenerationProfile(enabled=True)) == 0
    assert balanced_service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) == 1
    assert balanced_service._quality_retry_count(request=request, high_rigor_profile=HighRigorGenerationProfile(enabled=True)) == 1
    assert balanced_service._generation_strategy(request, HighRigorGenerationProfile(enabled=True)) == "single_then_repair"
    assert balanced_service._batch_candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) == 2


def test_balanced_premium_escalation_requires_setting_category_and_zero_valid(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_COST_PROFILE="balanced",
            PROBLEM_AGENT_ALLOW_PREMIUM_ESCALATION=True,
        ),
    )

    assert service._should_escalate_to_premium_generation(
        cost_profile="balanced",
        invalid_errors=["missing_evidence_binding: explanation does not connect to evidence"],
        valid_candidate_count=0,
        user_id="user_001",
    )
    assert not service._should_escalate_to_premium_generation(
        cost_profile="balanced",
        invalid_errors=["request_mismatch: wrong type"],
        valid_candidate_count=0,
        user_id="user_001",
    )
    assert not service._should_escalate_to_premium_generation(
        cost_profile="balanced",
        invalid_errors=["missing_evidence_binding: explanation does not connect to evidence"],
        valid_candidate_count=1,
        user_id="user_001",
    )
    disabled_service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_COST_PROFILE="balanced",
            PROBLEM_AGENT_ALLOW_PREMIUM_ESCALATION=False,
        ),
    )
    assert not disabled_service._should_escalate_to_premium_generation(
        cost_profile="balanced",
        invalid_errors=["missing_evidence_binding: explanation does not connect to evidence"],
        valid_candidate_count=0,
        user_id="user_001",
    )


def test_full_profile_uses_batch_generation_strategy(db_session):
    request = high_rigor_mcq_request()
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="full"),
    )

    assert service._generation_strategy(request, HighRigorGenerationProfile(enabled=True)) == "batch_candidates"
    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) >= 3


def test_explicit_batch_generation_strategy_overrides_balanced_default(db_session):
    request = high_rigor_mcq_request()
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_COST_PROFILE="balanced",
            PROBLEM_AGENT_GENERATION_STRATEGY="batch_candidates",
        ),
    )

    assert service._generation_strategy(request, HighRigorGenerationProfile(enabled=True)) == "batch_candidates"
    assert service._candidate_generation_count(request, HighRigorGenerationProfile(enabled=True)) == 2


def test_balanced_single_then_repair_repairs_once_after_invalid_mcq(db_session):
    request = high_rigor_mcq_request()
    invalid = high_rigor_multiple_choice_payload(request)
    invalid.pop("mcq_plan", None)
    repaired = high_rigor_multiple_choice_payload(request)
    problem_agent = RepairingProblemAgent(invalid, repaired)
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(math_chunks()),
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
        settings=Settings(PROBLEM_AGENT_COST_PROFILE="balanced"),
    )

    result = service.generate_problem_batch(user_id="user_001", request=request)

    assert result.quality_summary.passed == 1
    assert len(problem_agent.calls) == 1
    assert problem_agent.calls[0]["candidate_count"] == 1
    assert len(problem_agent.repair_calls) == 1
    assert "missing_mcq_plan" in "; ".join(problem_agent.repair_calls[0]["validation_errors"])
    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.generation_strategy == "single_then_repair"
    assert performance.repair_call_count == 1
    assert performance.initial_candidate_valid is False
    assert performance.repair_successful is True
    assert performance.attempts[0].requested_candidate_count == 1
    assert performance.attempts[1].requested_candidate_count == 1


def test_retry_prompt_adds_multiple_choice_checklist_for_mcq_feedback():
    prompt = ProblemAgent(settings=Settings())._quality_retry_feedback(
        [
            "evidence_analysis_structure",
            "weak_distractor_diagnostics",
            "testwise_option_cue",
        ]
    )

    assert "객관식 재생성 체크리스트" in prompt
    assert "source-grounded claim" in prompt
    assert "choice_diagnostics" in prompt


def test_short_answer_prompt_requires_complete_answer_and_discriminative_rubric():
    request = GenerateProblemRequest(
        document_id="math_doc",
        concepts=["절차 추적", "계산"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        problem_style="trace_and_explain",
    )
    prompt = ProblemAgent(settings=Settings())._build_prompt(request, math_chunks(), candidate_count=1)

    assert "주관식 answer.text는 짧은 결론만 쓰지 말고" in prompt
    assert "모든 기준에 같은 문구를 반복하지 마라" in prompt
    assert "자료의 규칙/공식/절차 식별" in prompt
    assert "trace_process 주관식 rubric" in prompt
    assert "procedure/source step identification" in prompt
    assert "compute_from_given 주관식 rubric" in prompt
    assert "formula/rule citation" in prompt


def test_compute_from_given_prompt_includes_computation_scenario_contract():
    request = GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
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
    plan = ProblemKernelPlanner().plan(request=request, content_atoms=[atom])
    chunks = [
        RetrievedChunk(
            chunk_id="formula_chunk",
            document_id="physics_doc",
            content="For parallel capacitors, C_eq = C1 + C2.",
            score=0.9,
        )
    ]

    prompt = ProblemAgent(settings=Settings())._build_prompt(
        request,
        chunks,
        candidate_count=1,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cost_profile="cheap",
    )

    assert "Computation Scenario Contract" in prompt
    assert "generated_given_values" in prompt
    assert "C_eq = C1 + C2" in prompt
    assert "question stem" in prompt
    assert "derivation" in prompt


def test_generation_context_packer_caps_chunks_to_max_and_keeps_top_chunk(db_session):
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(indexing_chunks(14)),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=8,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )
    request = GenerateProblemRequest(
        document_id="index_doc",
        concepts=["B+ tree", "sparse index", "disk I/O"],
        type="short_answer",
        count=1,
    )

    selected = service._select_generation_context_chunks(
        request=request,
        chunks=indexing_chunks(14),
        search_query="B+ tree sparse index disk I/O",
    )

    assert len(selected) == 8
    assert selected[0].chunk_id == "idx_00"


def test_generation_context_packer_prefers_concept_overlap(db_session):
    chunks = [
        RetrievedChunk(
            chunk_id="top",
            document_id="index_doc",
            content="강의 운영 안내와 과제 제출 일정",
            page=1,
            section_title="notice",
            concepts=[],
        ),
        RetrievedChunk(
            chunk_id="noise",
            document_id="index_doc",
            content="해시 테이블 충돌과 버킷 설명",
            page=2,
            section_title="hash",
            concepts=["hash"],
        ),
        RetrievedChunk(
            chunk_id="concept_match",
            document_id="index_doc",
            content="B+ tree sparse index는 leaf와 disk I/O 비용을 줄이는 indexing 구조이다.",
            page=3,
            section_title="B+ tree",
            concepts=["B+ tree", "sparse index"],
        ),
    ]
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=2,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=2,
        ),
    )
    request = GenerateProblemRequest(
        document_id="index_doc",
        concepts=["B+ tree", "sparse index"],
        type="short_answer",
        count=1,
    )

    selected = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="B+ tree sparse index",
    )

    assert [chunk.chunk_id for chunk in selected] == ["top", "concept_match"]


def test_generation_context_packer_removes_duplicate_content(db_session):
    chunks = indexing_chunks(4)
    duplicate = chunks[1].model_copy(update={"chunk_id": "idx_duplicate"})
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=5,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )
    request = GenerateProblemRequest(
        document_id="index_doc",
        concepts=["B+ tree"],
        type="short_answer",
        count=1,
    )

    selected = service._select_generation_context_chunks(
        request=request,
        chunks=[chunks[0], chunks[1], duplicate, chunks[2]],
        search_query="B+ tree",
    )

    assert "idx_duplicate" not in [chunk.chunk_id for chunk in selected]


def test_generation_context_packer_preserves_visual_chunk_when_requested(db_session):
    chunks = indexing_chunks(6)
    visual = chunks[-1].model_copy(update={"metadata": {"image_available": True, "image": "iVBORw0KGgoAAA"}})
    chunks[-1] = visual
    service = ProblemService(
        db=db_session,
        search_service=CapturingSearchService(chunks),
        problem_agent=CapturingProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=3,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=2,
        ),
    )
    request = GenerateProblemRequest(
        document_id="index_doc",
        concepts=["B+ tree"],
        type="multiple_choice",
        count=1,
        user_requirements="그림을 보고 B+ tree 구조를 판단하는 문제",
    )

    selected = service._select_generation_context_chunks(
        request=request,
        chunks=chunks,
        search_query="B+ tree",
    )

    assert visual.chunk_id in [chunk.chunk_id for chunk in selected]


def test_problem_agent_receives_packed_generation_context_and_metrics(db_session):
    search_service = CapturingSearchService(long_math_chunks(14))
    problem_agent = CapturingProblemAgent()
    service = ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=4,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=3,
        ),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="math_doc",
            concepts=["미분", "극한", "연속"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
    )

    assert len(search_service.chunks) == 14
    assert 3 <= len(problem_agent.last_chunks) <= 4
    performance = result.quality_summary.performance
    assert performance is not None
    assert performance.retrieved_chunk_count == 14
    assert performance.generation_context_chunk_count == len(problem_agent.last_chunks)
    assert performance.generation_context_chunk_ids == [chunk.chunk_id for chunk in problem_agent.last_chunks]
    assert performance.dropped_retrieved_chunk_count == 14 - len(problem_agent.last_chunks)
    assert performance.generation_context_reduction_ratio is not None
    assert performance.generation_context_reduction_ratio > 0


def test_high_rigor_generation_warns_when_context_packing_leaves_too_few_chunks(db_session):
    search_service = CapturingSearchService([complete_math_chunk()])
    problem_agent = CapturingProblemAgent()
    service = ProblemService(
        db=db_session,
        search_service=search_service,
        problem_agent=problem_agent,
        quality_checker=ProblemQualityChecker(),
        settings=Settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=1,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=1,
        ),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="math_doc",
            concepts=["미분", "극한", "연속"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
    )

    assert "low generation context coverage" in result.quality_summary.warnings


def math_chunks():
    return [
        RetrievedChunk(
            chunk_id="math_chunk_001",
            document_id="math_doc",
            content=(
                "함수의 극한에서는 x가 한 값에 가까워질 때 함수값의 변화를 본다. "
                "연속인 함수는 좌극한과 우극한과 함수값이 모두 같다."
            ),
            page=1,
            section_title="함수의 극한과 연속",
            concepts=["함수", "극한", "연속"],
        ),
        RetrievedChunk(
            chunk_id="math_chunk_002",
            document_id="math_doc",
            content=(
                "미분계수는 함수의 순간 변화율을 뜻하며, 접선의 기울기와 연결된다. "
                "도함수의 부호 변화는 함수의 증가와 감소를 판단하는 데 사용된다."
            ),
            page=2,
            section_title="미분과 도함수",
            concepts=["미분", "도함수", "증가와 감소"],
        ),
    ]


def indexing_chunks(count: int) -> list[RetrievedChunk]:
    chunks = []
    for index in range(count):
        if index == 0:
            content = "강의 개요와 인덱싱 장의 학습 목표를 소개한다."
            concepts = ["indexing"]
        elif index % 2 == 0:
            content = (
                f"B+ tree sparse index page {index} explains fanout, leaf nodes, and disk I/O tradeoffs."
            )
            concepts = ["B+ tree", "sparse index", "disk I/O"]
        else:
            content = f"Hash index bucket page {index} discusses equality search and unrelated hashing details."
            concepts = ["hash index"]
        chunks.append(
            RetrievedChunk(
                chunk_id=f"idx_{index:02d}",
                document_id="index_doc",
                content=content,
                page=index + 1,
                section_title=f"section_{index % 4}",
                concepts=concepts,
                metadata={"score": max(0.1, 0.95 - index * 0.03)},
            )
        )
    return chunks


def complete_math_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="math_chunk_all",
        document_id="math_doc",
        content=(
            "연속 조건은 좌극한, 우극한, 함수값이 모두 같다는 뜻이다. "
            "도함수의 부호 변화는 함수의 증가와 감소를 판단하는 데 사용된다. "
            "극한 조건과 미분 조건은 함수 분석에서 서로 다른 역할을 가진다."
        ),
        page=1,
        section_title="극한과 미분 종합",
        concepts=["미분", "극한", "연속", "도함수"],
    )


def long_math_chunks(count: int) -> list[RetrievedChunk]:
    base = [
        complete_math_chunk(),
        *math_chunks(),
    ]
    chunks = []
    for index in range(count):
        source = base[index % len(base)]
        chunks.append(
            source.model_copy(
                update={
                    "chunk_id": f"math_long_{index:02d}",
                    "page": index + 1,
                    "section_title": f"math_section_{index % 5}",
                    "metadata": {"score": max(0.1, 0.98 - index * 0.02)},
                }
            )
        )
    return chunks


def high_rigor_problem_payload(request, chunks):
    return {
        "document_id": request.document_id,
        "type": request.type.value,
        "difficulty": request.difficulty.value,
        "bloom_level": request.bloom_level.value,
        "question": (
            "연속 조건과 도함수의 부호 변화를 함께 적용하여 함수의 증가 구간을 분석하고, "
            "극한 조건이 결론에 어떤 영향을 주는지 비교하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "자료의 연속 조건으로 좌극한, 우극한, 함수값의 일치를 먼저 확인한다. "
                "그 다음 도함수의 부호 변화를 이용해 증가와 감소 구간을 판단한다. "
                "따라서 극한 조건은 함수값 연결을 보장하고, 도함수 조건은 변화 방향을 결정한다."
            ),
        },
        "explanation": "연속 조건과 도함수 부호 변화를 순서대로 적용해 분석하는 문제이다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "연속 조건을 극한과 함수값의 관계로 설명했다.",
                "points": 2,
                "expected_evidence": ["좌극한", "우극한", "함수값"],
                "common_mistakes": ["극한 조건과 함수값 조건을 분리하지 못함"],
                "partial_credit_rules": ["연속 조건만 언급하면 부분 점수"],
            },
            {
                "criterion": "도함수의 부호 변화로 증가와 감소를 분석했다.",
                "points": 2,
                "expected_evidence": ["도함수", "부호 변화", "증가", "감소"],
                "common_mistakes": ["도함수 조건 없이 결론만 제시함"],
                "partial_credit_rules": ["증가와 감소 중 하나만 연결하면 부분 점수"],
            },
            {
                "criterion": "극한 조건과 미분 조건의 역할을 비교했다.",
                "points": 1,
                "expected_evidence": ["비교", "영향"],
                "common_mistakes": ["두 조건을 같은 역할로 봄"],
                "partial_credit_rules": ["역할 차이를 일부만 설명하면 부분 점수"],
            },
        ],
        "concepts": request.concepts,
        "source_chunk_ids": [chunk.chunk_id for chunk in chunks],
    }


def high_rigor_multiple_choice_profile(*, multi_step_required=True):
    return HighRigorGenerationProfile(
        enabled=True,
        intensity=HighRigorIntensity.advanced,
        multi_concept_required=True,
        multi_step_required=multi_step_required,
        signals=["조건 변화", "추론"],
    )


def high_rigor_mcq_request():
    return GenerateProblemRequest(
        document_id="math_doc",
        concepts=["연속", "도함수", "극한"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
    )


def high_rigor_multiple_choice_payload(request):
    return {
        "document_id": request.document_id,
        "type": "multiple_choice",
        "difficulty": request.difficulty.value,
        "bloom_level": request.bloom_level.value,
        "question": (
            "주어진 조건이 바뀐 사례에서 함수가 x=1에서 연속이고, x>1 구간의 도함수 부호가 "
            "양수로 변한다. 이때 극한 조건과 도함수 정보를 함께 적용해 결론을 판단한 보기로 "
            "가장 적절한 것은?"
        ),
        "choices": [
            {
                "id": "A",
                "text": "연속 조건은 함수값 연결을 보장하고, 도함수 부호 변화는 x>1에서 증가 방향을 판단하게 한다.",
            },
            {
                "id": "B",
                "text": "연속 조건만 확인하면 도함수 부호와 무관하게 x>1에서 감소한다고 판단할 수 있다.",
            },
            {
                "id": "C",
                "text": "도함수 부호가 양수이면 x=1에서의 좌극한과 우극한 일치 여부를 확인할 필요가 없다.",
            },
            {
                "id": "D",
                "text": "극한 조건과 도함수 부호는 서로 같은 정보를 주므로 둘 중 하나만 확인하면 충분하다.",
            },
        ],
        "answer": {
            "choice_id": "A",
            "text": "연속 조건은 함수값 연결을 보장하고, 도함수 부호 변화는 x>1에서 증가 방향을 판단하게 한다.",
        },
        "explanation": (
            "조건이 바뀐 사례에서 연속은 극한과 함수값의 연결을 판단하는 근거이고, "
            "도함수 부호는 증가 방향을 해석하는 근거이므로 두 정보를 비교해 적용해야 한다."
        ),
        "choice_explanations": {
            "A": "연속 조건과 도함수 부호 변화의 역할을 구분해 적용한 판단이다.",
            "B": "도함수 부호가 양수라는 조건을 무시하고 감소 결론을 내린 설명이다.",
            "C": "증가 방향 판단과 연속성 판단의 역할을 혼동한 설명이다.",
            "D": "극한 조건과 도함수 부호가 서로 다른 역할을 한다는 점을 놓친 설명이다.",
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
                "misconception_id": "derivative_sign_ignored",
                "mistake_type": "missing_key_concept",
                "why_plausible": "연속 조건만 보고 도함수 부호가 증가 방향 판단에 쓰인다는 점을 빠뜨리면 고를 수 있다.",
                "repair_strategy": "연속 조건으로 함수값 연결을 확인한 뒤 도함수 부호로 변화 방향을 따로 판단한다.",
                "followup_problem_type": "condition_application",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "misconception_id": "limit_continuity_boundary_confusion",
                "mistake_type": "term_confusion",
                "why_plausible": "도함수 부호가 주어지면 연속 조건 확인도 자동으로 끝난다고 혼동하면 고를 수 있다.",
                "repair_strategy": "극한과 함수값 일치 조건은 도함수 부호와 별개로 확인해야 함을 비교한다.",
                "followup_problem_type": "concept_comparison",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "misconception_id": "same_role_assumption",
                "mistake_type": "logic_error",
                "why_plausible": "두 조건이 모두 함수 변화와 관련된다고만 보고 역할 차이를 분석하지 않으면 고를 수 있다.",
                "repair_strategy": "극한 조건은 연결성, 도함수 부호는 증가와 감소 판단이라는 역할 차이를 표로 구분한다.",
                "followup_problem_type": "comparison_judgment",
            },
        ],
        "rubric": None,
        "concepts": request.concepts,
        "source_chunk_ids": ["math_chunk_001", "math_chunk_002"],
        "mcq_plan": {
            "kernel_type": "compare_boundary",
            "source_rule_or_evidence": "연속은 극한과 함수값 연결을 확인하고 도함수 부호는 증가 방향을 판단한다.",
            "concrete_scenario": "x=1에서 연속이고 x>1에서 도함수 부호가 양수로 바뀌는 함수 사례",
            "correct_answer_claim": "연속 조건은 함수값 연결을 보장하고 도함수 부호 변화는 증가 방향 판단에 쓰인다.",
            "correct_answer_evidence_link": "연속 조건과 도함수 부호 변화를 함께 적용한다.",
            "distractor_plans": [
                {
                    "misconception_id": "derivative_sign_ignored",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "연속 조건만 보고 도함수 부호가 증가 방향 판단에 쓰인다는 점을 빠뜨릴 수 있다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "연속 조건으로 함수값 연결을 확인한 뒤 도함수 부호로 변화 방향을 따로 판단한다.",
                },
                {
                    "misconception_id": "limit_continuity_boundary_confusion",
                    "mistake_type": "term_confusion",
                    "why_plausible": "도함수 부호가 주어지면 연속 조건 확인도 끝난다고 혼동할 수 있다.",
                    "violated_or_ignored_evidence_role": "contrast",
                    "repair_strategy": "극한과 함수값 일치 조건은 도함수 부호와 별개로 확인해야 함을 비교한다.",
                },
                {
                    "misconception_id": "same_role_assumption",
                    "mistake_type": "logic_error",
                    "why_plausible": "두 조건이 모두 함수 변화와 관련된다고만 보고 역할 차이를 분석하지 않을 수 있다.",
                    "violated_or_ignored_evidence_role": "rule",
                    "repair_strategy": "극한 조건은 연결성, 도함수 부호는 증가와 감소 판단이라는 역할 차이를 표로 구분한다.",
                },
            ],
            "prohibited_patterns": ["definition-only", "generic distractor diagnostics"],
            "required_source_chunk_ids": ["math_chunk_001", "math_chunk_002"],
        },
        "difficulty_profile": {
            "cognitive_demand_score": 0.72,
            "reasoning_steps_required": 3,
            "requires_transfer": True,
            "requires_comparison": True,
        },
    }
