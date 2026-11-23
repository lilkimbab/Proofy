from __future__ import annotations

from dataclasses import dataclass
import re

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import (
    BloomLevel,
    CognitiveLevel,
    Difficulty,
    DifficultyProfile,
    GenerateProblemRequest,
    ItemDesignBrief,
    ItemModel,
    ItemModelId,
    ProblemDepth,
    ProblemStyle,
    ProblemType,
    ProfessorGradeItemScore,
    SimulatedResponseKind,
    SimulatedResponseResult,
    SourceRef,
    StudentResponseSimulationReport,
    TeacherReviewChecklist,
    TeacherReviewDecision,
)
from app.schemas.quality import TargetRigor


DEFAULT_ITEM_MODELS = [
    ItemModel(
        id=ItemModelId.definition_with_boundary,
        name="Definition with boundary",
        description="Checks a concept definition while making the boundary condition explicit.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.recall, CognitiveLevel.understand],
        required_evidence_types=["definition", "boundary_condition"],
        disallowed_patterns=["definition_only_for_high_rigor"],
        minimum_reasoning_steps=1,
        preferred_feedback_strategy="핵심 정의와 헷갈리는 경계를 짧게 구분한다.",
    ),
    ItemModel(
        id=ItemModelId.concept_comparison,
        name="Concept comparison",
        description="Asks the learner to compare related concepts, conditions, or outcomes.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.understand, CognitiveLevel.analyze],
        required_evidence_types=["comparison_basis", "shared_or_different_condition"],
        disallowed_patterns=["comparison_without_basis"],
        minimum_reasoning_steps=2,
        preferred_feedback_strategy="비교 기준을 먼저 짚고 어느 조건에서 갈렸는지 설명한다.",
    ),
    ItemModel(
        id=ItemModelId.procedure_with_missing_step,
        name="Procedure with missing step",
        description="Requires applying a procedure, formula, or reasoning sequence with one key step exposed.",
        supported_problem_types=[ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.apply, CognitiveLevel.analyze],
        required_evidence_types=["ordered_step", "formula_or_rule"],
        disallowed_patterns=["answer_only_without_process"],
        minimum_reasoning_steps=3,
        preferred_feedback_strategy="빠진 단계와 다음에 확인할 계산 또는 절차를 분리해 알려준다.",
    ),
    ItemModel(
        id=ItemModelId.error_detection,
        name="Error detection",
        description="Requires finding and correcting a flawed explanation, calculation, or reasoning path.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.analyze, CognitiveLevel.evaluate],
        required_evidence_types=["flawed_step", "correction_reason"],
        disallowed_patterns=["obvious_error_without_explanation"],
        minimum_reasoning_steps=2,
        preferred_feedback_strategy="무엇이 틀렸는지와 어떻게 고쳐야 하는지를 함께 제시한다.",
    ),
    ItemModel(
        id=ItemModelId.case_based_application,
        name="Case-based application",
        description="Requires applying source-grounded ideas to a concrete but fair new situation.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.apply, CognitiveLevel.analyze],
        required_evidence_types=["case_condition", "source_rule_application"],
        disallowed_patterns=["external_context_required"],
        minimum_reasoning_steps=2,
        preferred_feedback_strategy="사례 조건과 자료의 규칙을 한 문장씩 연결한다.",
    ),
    ItemModel(
        id=ItemModelId.data_interpretation,
        name="Data interpretation",
        description="Requires interpreting given numbers, table-like information, or relationships.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.apply, CognitiveLevel.analyze],
        required_evidence_types=["source_value", "comparison_basis", "conclusion"],
        disallowed_patterns=["numberless_data_claim"],
        minimum_reasoning_steps=3,
        preferred_feedback_strategy="읽은 수치, 비교 기준, 결론을 순서대로 확인한다.",
    ),
    ItemModel(
        id=ItemModelId.transfer_to_new_context,
        name="Transfer to new context",
        description="Requires solving a new context using the source concept, not copying the source sentence.",
        supported_problem_types=[ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.apply, CognitiveLevel.analyze, CognitiveLevel.evaluate],
        required_evidence_types=["new_condition", "source_rule_application"],
        disallowed_patterns=["source_sentence_copy"],
        minimum_reasoning_steps=3,
        preferred_feedback_strategy="새 조건에서 자료의 관계가 어떻게 옮겨지는지 짚는다.",
    ),
    ItemModel(
        id=ItemModelId.misconception_contrast,
        name="Misconception contrast",
        description="Turns likely learner misconceptions into diagnostic answer paths.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.understand, CognitiveLevel.apply, CognitiveLevel.analyze],
        required_evidence_types=["target_misconception", "repair_strategy"],
        disallowed_patterns=["duplicate_distractor_misconception"],
        minimum_reasoning_steps=2,
        preferred_feedback_strategy="선택한 오개념과 바로잡을 비교 문제 유형을 연결한다.",
    ),
    ItemModel(
        id=ItemModelId.worked_example_completion,
        name="Worked example completion",
        description="Requires completing or repairing a partly shown solution path.",
        supported_problem_types=[ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.apply, CognitiveLevel.analyze],
        required_evidence_types=["missing_step", "completion_reason"],
        disallowed_patterns=["final_answer_only"],
        minimum_reasoning_steps=3,
        preferred_feedback_strategy="예시 풀이에서 빠진 줄과 그 이유를 따로 알려준다.",
    ),
    ItemModel(
        id=ItemModelId.evidence_selection,
        name="Evidence selection",
        description="Requires selecting the source-grounded evidence that supports a claim.",
        supported_problem_types=[ProblemType.multiple_choice, ProblemType.short_answer],
        recommended_cognitive_levels=[CognitiveLevel.analyze, CognitiveLevel.evaluate],
        required_evidence_types=["source_evidence", "claim_link"],
        disallowed_patterns=["claim_without_text_evidence"],
        minimum_reasoning_steps=2,
        preferred_feedback_strategy="판단 근거가 된 문장과 결론을 직접 연결한다.",
    ),
]


@dataclass(frozen=True)
class ItemDesignResult:
    problem_data: dict
    rejection_errors: list[str]


class ItemModelSelector:
    def select(
        self,
        *,
        request: GenerateProblemRequest,
        problem_data: dict,
        chunks: list[RetrievedChunk],
    ) -> ItemModelId:
        question_text = str(problem_data.get("question") or "").lower()
        task_text = self._problem_task_text(problem_data)
        source_text = self._source_text(chunks)
        if self._has_error_cue(self._problem_text(problem_data)):
            return ItemModelId.error_detection
        if self._has_data_cue(task_text):
            return ItemModelId.data_interpretation
        if self._has_evidence_selection_cue(question_text):
            return ItemModelId.evidence_selection
        if self._has_calculation_cue(task_text) and problem_data.get("type") == ProblemType.short_answer.value:
            return ItemModelId.procedure_with_missing_step
        if self._has_comparison_cue(task_text):
            return ItemModelId.concept_comparison
        if (
            request.problem_style == ProblemStyle.evidence_analysis
            and self._has_data_cue(source_text)
            and self._has_interpretation_cue(task_text)
        ):
            return ItemModelId.data_interpretation
        if problem_data.get("choice_diagnostics"):
            return ItemModelId.misconception_contrast
        if request.difficulty == Difficulty.hard or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}:
            if problem_data.get("type") == ProblemType.short_answer.value:
                return ItemModelId.transfer_to_new_context
            return ItemModelId.case_based_application
        return ItemModelId.definition_with_boundary

    def _source_text(self, chunks: list[RetrievedChunk]) -> str:
        return " ".join(chunk.content for chunk in chunks).lower()

    def _problem_text(self, problem_data: dict) -> str:
        return f"{problem_data.get('question', '')} {problem_data.get('explanation', '')}".lower()

    def _problem_task_text(self, problem_data: dict) -> str:
        parts = [
            str(problem_data.get("question") or ""),
            str((problem_data.get("answer") or {}).get("text") or ""),
            str(problem_data.get("explanation") or ""),
        ]
        choices = problem_data.get("choices") or []
        parts.extend(str(choice.get("text") or "") for choice in choices if isinstance(choice, dict))
        choice_explanations = problem_data.get("choice_explanations") or {}
        parts.extend(str(value) for value in choice_explanations.values())
        diagnostics = problem_data.get("choice_diagnostics") or []
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            parts.extend(
                str(diagnostic.get(field) or "")
                for field in ("mistake_type", "misconception_id", "why_plausible", "repair_strategy")
            )
        rubric = problem_data.get("rubric") or []
        for item in rubric:
            if not isinstance(item, dict):
                continue
            parts.extend(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in item.get("expected_evidence") or []),
                    " ".join(str(value) for value in item.get("partial_credit_rules") or []),
                ]
            )
        return " ".join(parts).lower()

    def _has_error_cue(self, text: str) -> bool:
        return any(cue in text for cue in ("오류", "틀린", "잘못", "반례", "error", "wrong"))

    def _has_data_cue(self, text: str) -> bool:
        return bool(re.search(r"(?:^|\s)(table|graph)(?:\s|$)", text)) or any(
            cue in text
            for cue in (
                "표에서",
                "표를",
                "표의",
                "표 ",
                "그래프",
                "자료값",
                "데이터",
            )
        )

    def _has_calculation_cue(self, text: str) -> bool:
        return bool(re.search(r"\$[^$]*=[^$]*\$|[A-Za-z가-힣]\w*\s*=\s*[A-Za-z0-9가-힣]", text)) or any(
            cue in text for cue in ("계산", "공식", "대입", "값을 구", "수식")
        )

    def _has_comparison_cue(self, text: str) -> bool:
        return any(cue in text for cue in ("비교", "차이", "같은", "다른", "클수록", "작을수록", "관계"))

    def _has_interpretation_cue(self, text: str) -> bool:
        return any(cue in text for cue in ("해석", "판단", "결론", "평가", "타당", "일치", "interpret", "conclusion"))

    def _has_evidence_selection_cue(self, text: str) -> bool:
        source_evidence_cues = ("자료", "지문", "문장", "부분", "인용", "evidence", "source")
        selection_cues = (
            "고르",
            "선택",
            "찾",
            "제시",
            "뒷받침",
            "support",
        )
        alignment_cues = (
            *selection_cues,
            "판단",
            "평가",
            "타당",
            "일치",
            "가장 적절",
            "가장 잘",
            "연결",
            "결론",
            "주장",
            "source-aligned",
            "supported conclusion",
        )
        asks_explicit_evidence_selection = "근거" in text and any(cue in text for cue in selection_cues)
        has_source_evidence = any(cue in text for cue in source_evidence_cues) or asks_explicit_evidence_selection or (
            "근거" in text and any(cue in text for cue in ("자료", "지문", "source", "evidence"))
        )
        return has_source_evidence and any(cue in text for cue in alignment_cues)


class ProfessorGradeItemDesigner:
    def __init__(self, selector: ItemModelSelector | None = None):
        self.selector = selector or ItemModelSelector()

    def enrich(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
    ) -> ItemDesignResult:
        item_model_id = self.selector.select(request=request, problem_data=problem_data, chunks=chunks)
        source_refs = self._source_refs(problem_data=problem_data, chunks=chunks)
        difficulty_profile = self._difficulty_profile(problem_data=problem_data, request=request, item_model_id=item_model_id)
        design_brief = self._design_brief(
            problem_data=problem_data,
            request=request,
            item_model_id=item_model_id,
            difficulty_profile=difficulty_profile,
        )
        checklist = self._teacher_review_checklist(
            problem_data=problem_data,
            request=request,
            source_refs=source_refs,
            design_brief=design_brief,
            difficulty_profile=difficulty_profile,
        )
        simulation_report = self._student_response_simulation(problem_data=problem_data)
        score = self._professor_grade_score(
            problem_data=problem_data,
            request=request,
            checklist=checklist,
            difficulty_profile=difficulty_profile,
            simulation_report=simulation_report,
            item_model_id=item_model_id,
            source_refs=source_refs,
            chunks=chunks,
        )
        source_grounding_notes = self._source_grounding_notes(source_refs=source_refs, chunks=chunks)
        enriched = {
            **problem_data,
            "source_refs": [ref.model_dump(mode="json") for ref in source_refs],
            "source_grounding_notes": source_grounding_notes,
            "item_model_id": item_model_id.value,
            "item_design_brief": design_brief.model_dump(mode="json"),
            "difficulty_profile": difficulty_profile.model_dump(mode="json"),
            "teacher_review_checklist": checklist.model_dump(mode="json"),
            "professor_grade_score": score.model_dump(mode="json"),
            "student_response_simulation": simulation_report.model_dump(mode="json"),
        }
        return ItemDesignResult(problem_data=enriched, rejection_errors=self.rejection_errors(enriched))

    def rejection_errors(self, problem_data: dict) -> list[str]:
        checklist = problem_data.get("teacher_review_checklist") or {}
        score = problem_data.get("professor_grade_score") or {}
        errors = []
        if checklist.get("decision") == TeacherReviewDecision.rejected.value:
            errors.extend(checklist.get("required_revisions") or ["teacher review checklist rejected item"])
        errors.extend(score.get("reject_reasons") or [])
        simulation_report = problem_data.get("student_response_simulation") or {}
        if simulation_report and simulation_report.get("passed") is False:
            errors.extend(simulation_report.get("flags") or ["student response simulation failed"])
        return list(dict.fromkeys(str(error) for error in errors if str(error).strip()))

    def _source_refs(self, *, problem_data: dict, chunks: list[RetrievedChunk]) -> list[SourceRef]:
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        refs = []
        for chunk_id in problem_data.get("source_chunk_ids") or []:
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                continue
            refs.append(
                SourceRef(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    page=chunk.page,
                    section_title=chunk.section_title,
                )
            )
        return refs

    def _difficulty_profile(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        item_model_id: ItemModelId,
    ) -> DifficultyProfile:
        cognitive_level = self._cognitive_level(problem_data=problem_data, request=request)
        text = self._problem_text(problem_data).lower()
        requires_calculation = bool(re.search(r"\$[^$]*=[^$]*\$|\d+(?:\.\d+)?\s*[+\-*/÷]", text)) or any(
            cue in text for cue in ("계산", "대입", "공식", "값을 구", "단위")
        )
        requires_comparison = any(cue in text for cue in ("비교", "차이", "같은", "다른", "클수록", "작을수록"))
        requires_error_analysis = item_model_id == ItemModelId.error_detection or any(cue in text for cue in ("오류", "잘못", "틀린"))
        requires_transfer = item_model_id in {
            ItemModelId.case_based_application,
            ItemModelId.transfer_to_new_context,
            ItemModelId.data_interpretation,
        }
        model = self._item_model(item_model_id)
        reasoning_steps = 1
        if requires_calculation:
            reasoning_steps += 2
        if requires_comparison:
            reasoning_steps += 1
        if requires_error_analysis:
            reasoning_steps += 1
        if requires_transfer:
            reasoning_steps += 1
        if problem_data.get("type") == ProblemType.short_answer.value:
            reasoning_steps = max(reasoning_steps, min(6, len(problem_data.get("rubric") or []) + 1))
        reasoning_steps = max(reasoning_steps, model.minimum_reasoning_steps)
        if (
            problem_data.get("type") == ProblemType.multiple_choice.value
            and (request.target_rigor == TargetRigor.high or request.difficulty == Difficulty.hard)
            and item_model_id
            in {
                ItemModelId.evidence_selection,
                ItemModelId.concept_comparison,
                ItemModelId.case_based_application,
                ItemModelId.data_interpretation,
                ItemModelId.error_detection,
                ItemModelId.misconception_contrast,
            }
        ):
            reasoning_steps = max(reasoning_steps, 2)
            if request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}:
                reasoning_steps = max(reasoning_steps, 3)

        base_by_level = {
            CognitiveLevel.recall: 0.20,
            CognitiveLevel.understand: 0.35,
            CognitiveLevel.apply: 0.55,
            CognitiveLevel.analyze: 0.72,
            CognitiveLevel.evaluate: 0.82,
            CognitiveLevel.create: 0.90,
        }
        difficulty_bonus = {Difficulty.easy: 0.0, Difficulty.medium: 0.05, Difficulty.hard: 0.12}[request.difficulty]
        demand_score = min(
            1.0,
            base_by_level[cognitive_level]
            + difficulty_bonus
            + min(0.18, (reasoning_steps - 1) * 0.04)
            + (0.05 if requires_transfer else 0)
            + (0.06 if model.minimum_reasoning_steps >= 2 else 0),
        )
        prerequisites = self._prerequisite_concepts(problem_data=problem_data, request=request)
        return DifficultyProfile(
            difficulty=request.difficulty,
            cognitive_level=cognitive_level,
            reasoning_steps_required=min(12, reasoning_steps),
            prerequisite_count=len(prerequisites),
            cognitive_demand_score=round(demand_score, 3),
            requires_transfer=requires_transfer,
            requires_calculation=requires_calculation,
            requires_comparison=requires_comparison,
            requires_error_analysis=requires_error_analysis,
        )

    def _item_model(self, item_model_id: ItemModelId) -> ItemModel:
        for model in DEFAULT_ITEM_MODELS:
            if model.id == item_model_id:
                return model
        return DEFAULT_ITEM_MODELS[0]

    def _cognitive_level(self, *, problem_data: dict, request: GenerateProblemRequest) -> CognitiveLevel:
        mapping = {
            BloomLevel.remember: CognitiveLevel.recall,
            BloomLevel.understand: CognitiveLevel.understand,
            BloomLevel.apply: CognitiveLevel.apply,
            BloomLevel.analyze: CognitiveLevel.analyze,
            BloomLevel.evaluate: CognitiveLevel.evaluate,
            BloomLevel.create: CognitiveLevel.create,
        }
        requested = mapping[request.bloom_level]
        text = self._problem_text(problem_data).lower()
        if requested in {CognitiveLevel.recall, CognitiveLevel.understand}:
            if any(cue in text for cue in ("계산", "대입", "적용", "조건", "값을 구")):
                return CognitiveLevel.apply
            if any(cue in text for cue in ("비교", "분석", "판단", "오류", "왜")):
                return CognitiveLevel.analyze
        return requested

    def _design_brief(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        item_model_id: ItemModelId,
        difficulty_profile: DifficultyProfile,
    ) -> ItemDesignBrief:
        target_concept = self._target_concept(problem_data=problem_data, request=request)
        prerequisites = self._prerequisite_concepts(problem_data=problem_data, request=request)
        misconceptions = self._common_misconceptions(problem_data)
        target_misconception = misconceptions[0] if misconceptions else None
        observable_evidence = self._observable_evidence(problem_data)
        expected_steps = self._expected_reasoning_steps(problem_data=problem_data, difficulty_profile=difficulty_profile)
        scoring_strategy = (
            "정답 선택과 선택지별 진단 정보로 채점한다."
            if problem_data.get("type") == ProblemType.multiple_choice.value
            else "분석적 rubric 기준별로 부분 점수를 채점한다."
        )
        return ItemDesignBrief(
            target_concept=target_concept,
            prerequisite_concepts=prerequisites,
            learning_objective=f"{target_concept}을(를) 자료 근거에 맞게 {self._korean_cognitive_verb(difficulty_profile.cognitive_level)}한다.",
            cognitive_level=difficulty_profile.cognitive_level,
            assessment_claim=f"이 문항은 학습자가 {target_concept}의 핵심 관계를 문제 상황에서 사용할 수 있는지 확인한다.",
            observable_evidence=observable_evidence,
            expected_reasoning_steps=expected_steps,
            common_misconceptions=misconceptions,
            target_misconception=target_misconception,
            item_type=ProblemType(problem_data.get("type")),
            difficulty=request.difficulty,
            context_strategy=self._context_strategy(item_model_id=item_model_id, difficulty_profile=difficulty_profile),
            scoring_strategy=scoring_strategy,
        )

    def _teacher_review_checklist(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        source_refs: list[SourceRef],
        design_brief: ItemDesignBrief,
        difficulty_profile: DifficultyProfile,
    ) -> TeacherReviewChecklist:
        revisions: list[str] = []
        notes: list[str] = []
        problem_type = problem_data.get("type")
        question = str(problem_data.get("question") or "")
        answer_text = str((problem_data.get("answer") or {}).get("text") or "")
        source_grounded = bool(source_refs)
        answer_unambiguous = bool(answer_text.strip())
        if problem_type == ProblemType.multiple_choice.value:
            diagnostics = [item for item in (problem_data.get("choice_diagnostics") or []) if isinstance(item, dict)]
            correct_count = sum(1 for item in diagnostics if item.get("is_correct") is True)
            distractors_plausible = bool(diagnostics) and all(
                item.get("is_correct") is True or str(item.get("why_plausible") or "").strip()
                for item in diagnostics
            )
            distractors_diagnostic = bool(diagnostics) and all(
                item.get("is_correct") is True or str(item.get("repair_strategy") or "").strip()
                for item in diagnostics
            )
            answer_unambiguous = answer_unambiguous and correct_count == 1
        else:
            distractors_plausible = None
            distractors_diagnostic = None

        rubric = [item for item in (problem_data.get("rubric") or []) if isinstance(item, dict)]
        rubric_observable = None
        if problem_type == ProblemType.short_answer.value:
            rubric_observable = bool(rubric) and any(
                str(item.get("criterion") or "").strip() and (
                    item.get("expected_evidence") or any(cue in str(item.get("criterion") or "") for cue in ("근거", "조건", "계산", "비교", "설명"))
                )
                for item in rubric
            )

        no_hidden_answer_clue = not (answer_text and len(answer_text) >= 12 and answer_text in question)
        no_unnecessary_trick = not any(cue in question for cue in ("속임수", "함정", "말장난"))
        difficulty_appropriate = not (
            request.difficulty == Difficulty.hard and difficulty_profile.cognitive_demand_score < 0.55
        )
        cognitive_level_appropriate = not (
            request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
            and not (
                difficulty_profile.requires_error_analysis
                or difficulty_profile.requires_comparison
                or difficulty_profile.requires_transfer
                or difficulty_profile.requires_calculation
            )
        )
        vague_constructed_response = self._vague_constructed_response(problem_data=problem_data, request=request)
        if vague_constructed_response:
            cognitive_level_appropriate = False
            revisions.append("shallow_deep_question: constructed-response prompt must include observable response requirements")
        if not source_grounded:
            revisions.append("item must cite at least one retrieved source chunk")
        if not answer_unambiguous:
            revisions.append("item answer must be unambiguous")
        if not no_hidden_answer_clue:
            revisions.append("question leaks the answer text")
        if problem_type == ProblemType.multiple_choice.value:
            if not distractors_plausible:
                revisions.append("distractors must be plausible")
            if not distractors_diagnostic:
                revisions.append("distractors must include diagnostic feedback")
        if problem_type == ProblemType.short_answer.value and not rubric_observable:
            revisions.append("weak_rubric_evidence: constructed response item needs an observable analytic rubric")
        if not difficulty_appropriate:
            revisions.append("hard item must require application, analysis, or transfer")
        if not cognitive_level_appropriate:
            revisions.append("shallow_deep_question: cognitive level must match the requested assessment demand")

        fair_and_accessible = source_grounded and no_hidden_answer_clue and no_unnecessary_trick
        if not fair_and_accessible:
            notes.append("문항의 공정성이나 접근성을 다시 확인해야 한다.")
        decision = TeacherReviewDecision.approved
        if revisions:
            decision = TeacherReviewDecision.rejected
        elif not fair_and_accessible:
            decision = TeacherReviewDecision.needs_revision

        return TeacherReviewChecklist(
            learning_objective_clear=bool(design_brief.learning_objective.strip()),
            observable_evidence_clear=bool(design_brief.observable_evidence),
            source_grounded=source_grounded,
            answer_unambiguous=answer_unambiguous,
            no_hidden_answer_clue=no_hidden_answer_clue,
            no_unnecessary_trick=no_unnecessary_trick,
            distractors_plausible=distractors_plausible,
            distractors_diagnostic=distractors_diagnostic,
            rubric_observable=rubric_observable,
            difficulty_appropriate=difficulty_appropriate,
            cognitive_level_appropriate=cognitive_level_appropriate,
            fair_and_accessible=fair_and_accessible,
            reviewer_notes=notes,
            required_revisions=list(dict.fromkeys(revisions)),
            decision=decision,
        )

    def _professor_grade_score(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        checklist: TeacherReviewChecklist,
        difficulty_profile: DifficultyProfile,
        simulation_report: StudentResponseSimulationReport,
        item_model_id: ItemModelId,
        source_refs: list[SourceRef],
        chunks: list[RetrievedChunk],
    ) -> ProfessorGradeItemScore:
        is_mcq = problem_data.get("type") == ProblemType.multiple_choice.value
        is_short_answer = problem_data.get("type") == ProblemType.short_answer.value
        calibration_notes: list[str] = []
        distractor_quality = (
            1.0
            if not is_mcq
            else self._multiple_choice_distractor_quality(problem_data=problem_data, calibration_notes=calibration_notes)
        )
        rubric_quality = (
            1.0
            if not is_short_answer
            else self._short_answer_rubric_quality(problem_data=problem_data, calibration_notes=calibration_notes)
        )
        if is_short_answer:
            answer_rubric_similarity = self._answer_rubric_similarity(problem_data)
            if answer_rubric_similarity > 0.80:
                rubric_quality = min(rubric_quality, 0.72)
                calibration_notes.append("rubric expected evidence is too close to the model answer")
            elif answer_rubric_similarity > 0.62:
                rubric_quality = min(rubric_quality, 0.84)
                calibration_notes.append("rubric and model answer are partially redundant")

        source_grounding = self._source_grounding_score(
            problem_data=problem_data,
            source_refs=source_refs,
            chunks=chunks,
            calibration_notes=calibration_notes,
        )
        answer_clarity = float(checklist.answer_unambiguous)
        fairness_accessibility = float(checklist.fair_and_accessible)
        question_length = len(str(problem_data.get("question") or ""))
        if question_length > 900:
            answer_clarity = min(answer_clarity, 0.70)
            fairness_accessibility = min(fairness_accessibility, 0.80)
            calibration_notes.append("question stem is overlong")
        elif question_length > 650:
            answer_clarity = min(answer_clarity, 0.86)
            calibration_notes.append("question stem is long")

        mismatch_penalty = self._item_model_mismatch_penalty(
            problem_data=problem_data,
            item_model_id=item_model_id,
            calibration_notes=calibration_notes,
        )
        misconception_diagnosticity = self._misconception_score(problem_data)
        components = {
            "objective_alignment": float(checklist.learning_objective_clear and checklist.observable_evidence_clear),
            "source_grounding": source_grounding,
            "cognitive_demand": max(0.0, difficulty_profile.cognitive_demand_score - mismatch_penalty),
            "misconception_diagnosticity": misconception_diagnosticity,
            "answer_clarity": answer_clarity,
            "distractor_quality": distractor_quality,
            "rubric_quality": rubric_quality,
            "fairness_accessibility": fairness_accessibility,
            "leakage_resistance": float(checklist.no_hidden_answer_clue),
            "remediation_value": max(misconception_diagnosticity, rubric_quality if is_short_answer else 0.0),
        }
        if not simulation_report.passed:
            components["rubric_quality"] = min(components["rubric_quality"], 0.4)
            components["answer_clarity"] = min(components["answer_clarity"], 0.5)
        if request.target_rigor == TargetRigor.high:
            operation_label = self._reasoning_operation_label(problem_data)
            if operation_label in {"definition_recall", "generic_application"}:
                components["cognitive_demand"] = min(components["cognitive_demand"], 0.72)
                calibration_notes.append("high-rigor operation is too generic")

        structural_score = round(
            (
                components["answer_clarity"]
                + components["fairness_accessibility"]
                + components["leakage_resistance"]
                + (components["distractor_quality"] if is_mcq else components["rubric_quality"])
            )
            / 4,
            3,
        )
        pedagogical_score = round(
            (
                components["objective_alignment"]
                + components["cognitive_demand"]
                + components["misconception_diagnosticity"]
                + components["remediation_value"]
            )
            / 4,
            3,
        )
        grounding_score = round(components["source_grounding"], 3)
        assessment_design_score = round(
            (
                components["cognitive_demand"]
                + (components["distractor_quality"] if is_mcq else components["rubric_quality"])
                + components["answer_clarity"]
            )
            / 3,
            3,
        )
        weighted_score = (
            0.18 * components["objective_alignment"]
            + 0.18 * components["source_grounding"]
            + 0.17 * components["cognitive_demand"]
            + 0.10 * components["misconception_diagnosticity"]
            + 0.12 * components["answer_clarity"]
            + 0.10 * components["distractor_quality"]
            + 0.10 * components["rubric_quality"]
            + 0.05 * components["fairness_accessibility"]
        )
        final_score = min(weighted_score, self._calibrated_score_cap(calibration_notes))
        final_score = round(final_score, 3)
        reject_reasons = [*checklist.required_revisions, *simulation_report.flags]
        return ProfessorGradeItemScore(
            **components,
            final_score=final_score,
            reject_reasons=list(dict.fromkeys(reject_reasons)),
            structural_score=structural_score,
            pedagogical_score=pedagogical_score,
            grounding_score=grounding_score,
            assessment_design_score=assessment_design_score,
            calibration_notes=list(dict.fromkeys(calibration_notes)),
        )

    def _short_answer_rubric_quality(self, *, problem_data: dict, calibration_notes: list[str]) -> float:
        rubric = [item for item in (problem_data.get("rubric") or []) if isinstance(item, dict)]
        if not rubric:
            calibration_notes.append("short-answer item is missing rubric")
            return 0.0

        criteria = [str(item.get("criterion") or "").strip() for item in rubric]
        expected_evidence = [
            " ".join(str(value) for value in (item.get("expected_evidence") or [])).strip()
            for item in rubric
        ]
        common_mistakes = [
            " ".join(str(value) for value in (item.get("common_mistakes") or [])).strip()
            for item in rubric
        ]
        partial_credit = [
            " ".join(str(value) for value in (item.get("partial_credit_rules") or [])).strip()
            for item in rubric
        ]
        points = [item.get("points") for item in rubric]
        distinct_criteria_ratio = self._distinct_text_ratio(criteria)
        distinct_evidence_ratio = self._distinct_text_ratio(expected_evidence)
        positive_points = bool(points) and all(isinstance(point, int | float) and point > 0 for point in points)
        specific_evidence_ratio = self._meaningful_text_ratio(expected_evidence, minimum_length=14)
        common_mistake_ratio = self._meaningful_text_ratio(common_mistakes, minimum_length=10)
        partial_credit_ratio = self._meaningful_text_ratio(partial_credit, minimum_length=10)

        score = (
            0.20 * distinct_criteria_ratio
            + 0.20 * distinct_evidence_ratio
            + 0.15 * float(positive_points)
            + 0.20 * specific_evidence_ratio
            + 0.12 * common_mistake_ratio
            + 0.13 * partial_credit_ratio
        )
        if distinct_evidence_ratio < 0.75 and len(rubric) > 1:
            calibration_notes.append("rubric expected_evidence is repetitive")
        discriminability_issues = self._rubric_discriminability_issues(rubric)
        calibration_notes.extend(discriminability_issues)
        if partial_credit_ratio < 0.5:
            calibration_notes.append("rubric lacks partial-credit discrimination")
        if common_mistake_ratio < 0.5:
            calibration_notes.append("rubric common mistakes are weak or missing")
        return round(min(1.0, max(0.0, score)), 3)

    def _rubric_discriminability_issues(self, rubric: list[dict]) -> list[str]:
        if len(rubric) < 2:
            return []
        item_texts = [
            " ".join(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                ]
            )
            for item in rubric
        ]
        normalized_items = [self._normalize_score_text(text) for text in item_texts if self._normalize_score_text(text)]
        expected_evidence = [
            " ".join(str(value) for value in (item.get("expected_evidence") or [])).strip()
            for item in rubric
        ]
        normalized_evidence = [
            self._normalize_score_text(text) for text in expected_evidence if self._normalize_score_text(text)
        ]
        issues: list[str] = []
        if normalized_items and len(set(normalized_items)) < len(normalized_items):
            issues.append("rubric_items_not_distinct")
        if normalized_evidence and len(set(normalized_evidence)) < len(normalized_evidence):
            issues.append("rubric_expected_evidence_too_overlapping")
        if self._max_pairwise_token_similarity(expected_evidence) > 0.84:
            issues.append("rubric_expected_evidence_too_overlapping")

        token_sets = [self._content_tokens(text) for text in item_texts]
        all_tokens: dict[str, int] = {}
        for tokens in token_sets:
            for token in tokens:
                all_tokens[token] = all_tokens.get(token, 0) + 1
        weak_unique_count = sum(1 for tokens in token_sets if not any(all_tokens.get(token, 0) == 1 for token in tokens))
        if weak_unique_count == len(token_sets):
            issues.append("rubric_items_not_distinct")
        return list(dict.fromkeys(issues))

    def _multiple_choice_distractor_quality(self, *, problem_data: dict, calibration_notes: list[str]) -> float:
        choices = [item for item in (problem_data.get("choices") or []) if isinstance(item, dict)]
        diagnostics = [item for item in (problem_data.get("choice_diagnostics") or []) if isinstance(item, dict)]
        incorrect_diagnostics = [item for item in diagnostics if item.get("is_correct") is not True]
        incorrect_choices = [
            str(choice.get("text") or "")
            for choice in choices
            if str(choice.get("id") or "") not in {str(item.get("choice_id") or "") for item in diagnostics if item.get("is_correct") is True}
        ]
        if not choices or len(choices) < 4:
            calibration_notes.append("multiple-choice item has fewer than four choices")
            return 0.35
        diagnostic_ratio = min(1.0, len(incorrect_diagnostics) / max(1, len(choices) - 1))
        why_ratio = self._meaningful_text_ratio(
            [str(item.get("why_plausible") or "") for item in incorrect_diagnostics],
            minimum_length=12,
        )
        repair_ratio = self._meaningful_text_ratio(
            [str(item.get("repair_strategy") or "") for item in incorrect_diagnostics],
            minimum_length=12,
        )
        signal_texts = [
            f"{item.get('mistake_type') or ''} {item.get('misconception_id') or ''} {item.get('why_plausible') or ''}"
            for item in incorrect_diagnostics
        ]
        distinct_signal_ratio = self._distinct_text_ratio(signal_texts)
        similarity_penalty = 0.0
        if self._max_pairwise_token_similarity(incorrect_choices) > 0.78:
            similarity_penalty = 0.18
            calibration_notes.append("multiple-choice distractors are too similar")
        absolute_count = sum(
            1
            for choice in incorrect_choices
            if any(cue in choice.lower() for cue in ("항상", "절대", "무조건", "전혀", "반드시", "always", "never"))
        )
        absolute_penalty = 0.0
        if absolute_count > 1:
            absolute_penalty = 0.18
            calibration_notes.append("multiple-choice distractors use repeated absolute wording")
        score = (
            0.22 * diagnostic_ratio
            + 0.22 * why_ratio
            + 0.22 * repair_ratio
            + 0.22 * distinct_signal_ratio
            + 0.12 * float(len(choices) == 4)
            - similarity_penalty
            - absolute_penalty
        )
        return round(min(1.0, max(0.0, score)), 3)

    def _source_grounding_score(
        self,
        *,
        problem_data: dict,
        source_refs: list[SourceRef],
        chunks: list[RetrievedChunk],
        calibration_notes: list[str],
    ) -> float:
        if not source_refs:
            calibration_notes.append("item has no valid source references")
            return 0.0
        cited_ids = [ref.chunk_id for ref in source_refs]
        cited_count = len(cited_ids)
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        cited_text = " ".join(chunk_by_id[chunk_id].content for chunk_id in cited_ids if chunk_id in chunk_by_id)
        generated_text = " ".join(
            str(value or "")
            for value in (
                problem_data.get("question"),
                (problem_data.get("answer") or {}).get("text") if isinstance(problem_data.get("answer"), dict) else "",
                problem_data.get("explanation"),
            )
        )
        overlap = self._content_term_overlap(generated_text, cited_text)
        cited_count_score = 1.0
        if cited_count > 6:
            cited_count_score = 0.62
            calibration_notes.append("source_chunk_ids are broad and need clearer roles")
        elif cited_count > 4:
            cited_count_score = 0.78
            calibration_notes.append("source_chunk_ids are somewhat broad")
        unsupported_numbers = self._unsupported_numeric_terms(problem_data=problem_data, cited_text=cited_text)
        assumption_score = 1.0
        if unsupported_numbers and not self._has_given_condition_framing(problem_data):
            assumption_score = 0.72
            calibration_notes.append("synthetic numeric assumptions are not clearly framed as given conditions")
        score = 0.35 + 0.30 * overlap + 0.20 * cited_count_score + 0.15 * assumption_score
        if overlap < 0.20:
            calibration_notes.append("answer/explanation has weak overlap with cited source chunks")
        return round(min(1.0, max(0.0, score)), 3)

    def _item_model_mismatch_penalty(
        self,
        *,
        problem_data: dict,
        item_model_id: ItemModelId,
        calibration_notes: list[str],
    ) -> float:
        task_text = self.selector._problem_task_text(problem_data)
        declared = str(problem_data.get("item_model_id") or "").strip()
        penalty = 0.0
        if declared and declared != item_model_id.value:
            penalty = max(penalty, 0.06)
            calibration_notes.append("generated item_model_id differed from selected task model")
        mismatch = False
        if item_model_id == ItemModelId.evidence_selection:
            mismatch = not self.selector._has_evidence_selection_cue(task_text)
        elif item_model_id == ItemModelId.data_interpretation:
            mismatch = not self.selector._has_data_cue(task_text)
        elif item_model_id == ItemModelId.error_detection:
            mismatch = not self.selector._has_error_cue(task_text)
        elif item_model_id == ItemModelId.concept_comparison:
            mismatch = not self.selector._has_comparison_cue(task_text)
        elif item_model_id == ItemModelId.procedure_with_missing_step:
            mismatch = not self.selector._has_calculation_cue(task_text) and not any(
                cue in task_text for cue in ("단계", "절차", "과정", "step", "procedure")
            )
        if mismatch:
            penalty = max(penalty, 0.12)
            calibration_notes.append("item_model_id does not match the generated task")
        return penalty

    def _answer_rubric_similarity(self, problem_data: dict) -> float:
        answer_text = str((problem_data.get("answer") or {}).get("text") or "")
        rubric_text = " ".join(
            " ".join(str(value) for value in (item.get("expected_evidence") or []))
            for item in (problem_data.get("rubric") or [])
            if isinstance(item, dict)
        )
        return self._token_similarity(answer_text, rubric_text)

    def _content_term_overlap(self, generated_text: str, source_text: str) -> float:
        generated_tokens = self._content_tokens(generated_text)
        source_tokens = self._content_tokens(source_text)
        if not generated_tokens or not source_tokens:
            return 0.0
        return len(generated_tokens & source_tokens) / len(generated_tokens)

    def _unsupported_numeric_terms(self, *, problem_data: dict, cited_text: str) -> set[str]:
        generated_text = " ".join(
            str(value or "")
            for value in (problem_data.get("answer"), problem_data.get("explanation"))
        )
        question_text = str(problem_data.get("question") or "")
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", cited_text))
        question_numbers = set(re.findall(r"\d+(?:\.\d+)?", question_text))
        generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", generated_text))
        return {number for number in generated_numbers if number not in source_numbers and number not in question_numbers}

    def _has_given_condition_framing(self, problem_data: dict) -> bool:
        question = str(problem_data.get("question") or "").lower()
        return any(cue in question for cue in ("주어진", "다음", "가정", "조건", "given", "assume", "if", "when"))

    def _reasoning_operation_label(self, problem_data: dict) -> str:
        text = self.selector._problem_task_text(problem_data)
        if any(cue in text for cue in ("오류", "잘못", "틀린", "수정", "error", "bug", "debug")):
            return "error_diagnosis"
        if any(cue in text for cue in ("조건", "변화", "바뀌", "달라지", "changed")):
            return "condition_mutation"
        if any(cue in text for cue in ("비교", "차이", "compare")):
            return "concept_comparison"
        if any(cue in text for cue in ("근거", "자료", "표", "그래프", "evidence", "data", "graph", "table")):
            return "evidence_interpretation"
        if any(cue in text for cue in ("추적", "상태", "코드", "배열", "trace", "state", "code")):
            return "trace_and_explain"
        if any(cue in text for cue in ("설계", "제약", "선택", "최적", "constraint", "tradeoff")):
            return "design_under_constraint"
        if any(cue in text for cue in ("계산", "공식", "수식", "calculate", "formula")):
            return "calculation_reasoning"
        if any(cue in text for cue in ("정의", "무엇", "define", "definition")):
            return "definition_recall"
        return "generic_application"

    def _calibrated_score_cap(self, calibration_notes: list[str]) -> float:
        if not calibration_notes:
            return 0.98
        severe_notes = sum(
            1
            for note in calibration_notes
            if any(cue in note for cue in ("weak", "missing", "mismatch", "repetitive", "unsupported", "broad"))
        )
        if severe_notes >= 3:
            return 0.82
        if severe_notes == 2:
            return 0.88
        return 0.93

    def _distinct_text_ratio(self, texts: list[str]) -> float:
        non_empty = [self._normalize_score_text(text) for text in texts if self._normalize_score_text(text)]
        if not non_empty:
            return 0.0
        return len(set(non_empty)) / len(non_empty)

    def _meaningful_text_ratio(self, texts: list[str], *, minimum_length: int) -> float:
        non_empty = [str(text or "").strip() for text in texts]
        if not non_empty:
            return 0.0
        generic_cues = ("설명", "확인", "검토", "자료", "근거")
        meaningful = [
            text
            for text in non_empty
            if len(text) >= minimum_length and not (len(text) < minimum_length * 2 and text in generic_cues)
        ]
        return len(meaningful) / len(non_empty)

    def _max_pairwise_token_similarity(self, texts: list[str]) -> float:
        max_similarity = 0.0
        token_sets = [self._content_tokens(text) for text in texts if self._content_tokens(text)]
        for index, left in enumerate(token_sets):
            for right in token_sets[index + 1 :]:
                max_similarity = max(max_similarity, len(left & right) / max(1, len(left | right)))
        return max_similarity

    def _token_similarity(self, left_text: str, right_text: str) -> float:
        left = self._content_tokens(left_text)
        right = self._content_tokens(right_text)
        if not left or not right:
            return 0.0
        return len(left & right) / max(1, len(left | right))

    def _content_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9가-힣_]{2,}", str(text or "").lower())
            if token not in {"the", "and", "for", "with", "자료", "문제", "정답", "해설"}
        }

    def _normalize_score_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    def _student_response_simulation(self, *, problem_data: dict) -> StudentResponseSimulationReport:
        if problem_data.get("type") == ProblemType.multiple_choice.value:
            return self._multiple_choice_simulation(problem_data)
        return self._short_answer_simulation(problem_data)

    def _multiple_choice_simulation(self, problem_data: dict) -> StudentResponseSimulationReport:
        answer_id = str((problem_data.get("answer") or {}).get("choice_id") or "").strip()
        diagnostics = [item for item in (problem_data.get("choice_diagnostics") or []) if isinstance(item, dict)]
        incorrect_ids = [str(item.get("choice_id") or "").strip() for item in diagnostics if item.get("is_correct") is not True]
        misconception_choice_id = incorrect_ids[0] if incorrect_ids else ""
        condition_missing_choice_id = incorrect_ids[-1] if incorrect_ids else misconception_choice_id

        cases = [
            self._simulation_case(
                SimulatedResponseKind.full_correct,
                answer_summary=f"selects {answer_id}",
                expected_score_ratio=1.0,
                observed_score_ratio=1.0 if answer_id else 0.0,
                notes=["dry-run uses deterministic choice-id grading"],
            ),
            self._simulation_case(
                SimulatedResponseKind.partial_correct,
                answer_summary="selects a plausible but incorrect distractor",
                expected_score_ratio=0.0,
                observed_score_ratio=0.0,
                notes=["multiple-choice has no partial credit in this product policy"],
            ),
            self._simulation_case(
                SimulatedResponseKind.misconception,
                answer_summary=f"selects {misconception_choice_id or 'an incorrect choice'}",
                expected_score_ratio=0.0,
                observed_score_ratio=0.0 if misconception_choice_id else 1.0,
                notes=["misconception path should not be scored as correct"],
            ),
            self._simulation_case(
                SimulatedResponseKind.condition_missing,
                answer_summary=f"selects {condition_missing_choice_id or 'an incomplete-condition choice'}",
                expected_score_ratio=0.0,
                observed_score_ratio=0.0 if condition_missing_choice_id else 1.0,
                notes=["missing-condition path should not be scored as correct"],
            ),
        ]
        return self._simulation_report(cases)

    def _short_answer_simulation(self, problem_data: dict) -> StudentResponseSimulationReport:
        rubric = [item for item in (problem_data.get("rubric") or []) if isinstance(item, dict)]
        full_answer_text = self._full_correct_simulated_answer(problem_data)
        full_score = self._simulate_rubric_score(answer_text=full_answer_text, rubric=rubric)
        partial_answer = self._partial_correct_simulated_answer(rubric)
        partial_score = self._simulate_rubric_score(answer_text=partial_answer, rubric=rubric)
        misconception_answer = self._first_common_mistake(problem_data) or "answer follows a common misconception"
        misconception_score = self._simulate_rubric_score(
            answer_text=misconception_answer,
            rubric=rubric,
            allow_unstructured_fallback=False,
        )
        condition_missing_answer = self._condition_missing_simulated_answer(rubric)
        condition_missing_score = self._simulate_rubric_score(answer_text=condition_missing_answer, rubric=rubric)
        cases = [
            self._simulation_case(
                SimulatedResponseKind.full_correct,
                answer_summary=full_answer_text[:240] or "model answer covers all rubric criteria",
                expected_score_ratio=1.0,
                observed_score_ratio=full_score["score_ratio"],
                matched_rubric_indices=full_score["matched_indices"],
                unmatched_rubric_indices=full_score["unmatched_indices"],
                notes=["dry-run checks whether the model answer plus explanation covers rubric evidence"],
            ),
            self._simulation_case(
                SimulatedResponseKind.partial_correct,
                answer_summary=partial_answer or "answer covers only one rubric criterion",
                expected_score_ratio=min(0.7, max(0.2, partial_score["score_ratio"])),
                observed_score_ratio=partial_score["score_ratio"],
                matched_rubric_indices=partial_score["matched_indices"],
                unmatched_rubric_indices=partial_score["unmatched_indices"],
                notes=["partial answer should receive partial, not full, credit"],
            ),
            self._simulation_case(
                SimulatedResponseKind.misconception,
                answer_summary=misconception_answer,
                expected_score_ratio=0.0,
                observed_score_ratio=misconception_score["score_ratio"],
                matched_rubric_indices=misconception_score["matched_indices"],
                unmatched_rubric_indices=misconception_score["unmatched_indices"],
                notes=["common-misconception answer should stay below passing score"],
            ),
            self._simulation_case(
                SimulatedResponseKind.condition_missing,
                answer_summary=condition_missing_answer or "answer misses the highest-value condition or reasoning step",
                expected_score_ratio=min(0.75, condition_missing_score["score_ratio"]),
                observed_score_ratio=condition_missing_score["score_ratio"],
                matched_rubric_indices=condition_missing_score["matched_indices"],
                unmatched_rubric_indices=condition_missing_score["unmatched_indices"],
                notes=["missing a major condition should not still receive near-full score"],
            ),
        ]
        return self._simulation_report(cases)

    def _full_correct_simulated_answer(self, problem_data: dict) -> str:
        answer_text = str((problem_data.get("answer") or {}).get("text") or "").strip()
        explanation = self._compact_simulation_explanation(str(problem_data.get("explanation") or ""))
        evidence_links = self._evidence_link_simulation_text(problem_data)
        parts = [answer_text, explanation, evidence_links]
        return " ".join(part for part in parts if part).strip()

    def _compact_simulation_explanation(self, explanation: str) -> str:
        text = str(explanation or "").strip()
        if len(text) <= 900:
            return text
        sentences = [part.strip() for part in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", text) if part.strip()]
        if not sentences:
            return text[:900]
        compact = " ".join(sentences[:3]).strip()
        return compact if compact else text[:900]

    def _evidence_link_simulation_text(self, problem_data: dict) -> str:
        design_brief = problem_data.get("item_design_brief")
        if not isinstance(design_brief, dict):
            return ""
        links = [link for link in (design_brief.get("evidence_links") or []) if isinstance(link, dict)]
        parts: list[str] = []
        for link in links[:3]:
            parts.append(str(link.get("evidence_quote") or "").strip())
            parts.append(str(link.get("supported_claim") or "").strip())
        return " ".join(part for part in parts if part)

    def _simulation_case(
        self,
        kind: SimulatedResponseKind,
        *,
        answer_summary: str,
        expected_score_ratio: float,
        observed_score_ratio: float,
        matched_rubric_indices: list[int] | None = None,
        unmatched_rubric_indices: list[int] | None = None,
        notes: list[str],
    ) -> SimulatedResponseResult:
        passed = abs(observed_score_ratio - expected_score_ratio) <= 0.35
        if kind == SimulatedResponseKind.full_correct:
            passed = observed_score_ratio >= 0.8
        elif kind == SimulatedResponseKind.misconception:
            passed = observed_score_ratio < 0.7
        elif kind == SimulatedResponseKind.condition_missing:
            passed = observed_score_ratio < 1.0
        return SimulatedResponseResult(
            kind=kind,
            answer_summary=answer_summary or kind.value,
            expected_score_ratio=round(expected_score_ratio, 3),
            observed_score_ratio=round(observed_score_ratio, 3),
            matched_rubric_indices=matched_rubric_indices or [],
            unmatched_rubric_indices=unmatched_rubric_indices or [],
            passed=passed,
            notes=notes,
        )

    def _simulate_rubric_score(
        self,
        *,
        answer_text: str,
        rubric: list[dict],
        allow_unstructured_fallback: bool = True,
    ) -> dict:
        total_points = sum(float(item.get("points") or 0) for item in rubric)
        if total_points <= 0:
            return {"score_ratio": 0.0, "matched_indices": [], "unmatched_indices": []}

        awarded = 0.0
        matched_indices: list[int] = []
        unmatched_indices: list[int] = []
        for index, item in enumerate(rubric):
            points = float(item.get("points") or 0)
            matched = self._rubric_item_matches_answer(
                item=item,
                answer_text=answer_text,
                allow_unstructured_fallback=allow_unstructured_fallback,
            )
            if matched:
                awarded += points
                matched_indices.append(index)
            else:
                unmatched_indices.append(index)
        return {
            "score_ratio": round(awarded / total_points, 3),
            "matched_indices": matched_indices,
            "unmatched_indices": unmatched_indices,
        }

    def _rubric_item_matches_answer(
        self,
        *,
        item: dict,
        answer_text: str,
        allow_unstructured_fallback: bool,
    ) -> bool:
        expected_evidence = [
            str(value).strip()
            for value in (item.get("expected_evidence") or [])
            if str(value).strip()
        ]
        if expected_evidence:
            matched = sum(1 for evidence in expected_evidence if self._term_present(evidence, answer_text))
            if len(expected_evidence) <= 2:
                required = 1
            elif len(expected_evidence) <= 4:
                required = len(expected_evidence) - 1
            else:
                required = max(2, (len(expected_evidence) + 1) // 2)
            return matched >= required

        criterion_tokens = self._meaningful_tokens(str(item.get("criterion") or ""))
        if not criterion_tokens:
            return bool(str(answer_text or "").strip())
        answer_tokens = set(self._meaningful_tokens(answer_text))
        if len(set(criterion_tokens) & answer_tokens) >= min(2, len(set(criterion_tokens))):
            return True
        return allow_unstructured_fallback and len(answer_tokens) >= 3

    def _partial_correct_simulated_answer(self, rubric: list[dict]) -> str:
        if not rubric:
            return "answer covers only one rubric criterion"
        return self._rubric_item_answer_fragment(rubric[0])

    def _condition_missing_simulated_answer(self, rubric: list[dict]) -> str:
        if not rubric:
            return "answer misses the highest-value condition or reasoning step"
        largest_index = max(range(len(rubric)), key=lambda index: float(rubric[index].get("points") or 0))
        fragments = [
            self._rubric_item_answer_fragment(item)
            for index, item in enumerate(rubric)
            if index != largest_index
        ]
        return " ".join(fragment for fragment in fragments if fragment).strip()

    def _rubric_item_answer_fragment(self, item: dict) -> str:
        expected_evidence = [
            str(value).strip()
            for value in (item.get("expected_evidence") or [])
            if str(value).strip()
        ]
        if expected_evidence:
            return " ".join(expected_evidence[:2])
        return str(item.get("criterion") or "").strip()

    def _term_present(self, term: str, text: str) -> bool:
        normalized_term = self._normalize_evidence_text(term)
        normalized_text = self._normalize_evidence_text(text)
        if not normalized_term:
            return False
        if normalized_term in normalized_text:
            return True

        term_structures = self._structured_evidence_tokens(term)
        if term_structures:
            return all(structure in normalized_text for structure in term_structures)

        term_tokens = self._meaningful_tokens(term)
        answer_tokens = self._meaningful_tokens(text)
        if not term_tokens or not answer_tokens:
            return False
        matched = sum(
            1
            for term_token in term_tokens
            if any(self._tokens_match(term_token, answer_token) for answer_token in answer_tokens)
        )
        if len(term_tokens) <= 2:
            return matched == len(term_tokens)
        required = max(2, min(len(term_tokens), round(len(term_tokens) * 0.5)))
        return matched >= required

    def _structured_evidence_tokens(self, text: str) -> list[str]:
        structures = []
        for value in re.findall(r"\[[^\]]+\]|\([^\)]+\)|\{[^\}]+\}", str(text or "")):
            normalized = self._normalize_evidence_text(value)
            if len(normalized) >= 3 and any(char.isdigit() for char in normalized):
                structures.append(normalized)
        return structures

    def _token_is_meaningful(self, token: str, stopwords: set[str]) -> bool:
        if token in stopwords:
            return False
        if token.isdigit():
            return True
        return len(token) >= 2

    def _tokens_match(self, left: str, right: str) -> bool:
        if left in right or right in left:
            return True
        if len(left) >= 3 and len(right) >= 3:
            return left[:2] == right[:2]
        return False

    def _meaningful_tokens(self, text: str) -> list[str]:
        stopwords = {
            "자료",
            "근거",
            "설명",
            "설명한다",
            "한다",
            "했다",
            "있는",
            "없는",
            "기준",
            "답안",
            "제시",
            "제시한다",
            "서술",
            "서술한다",
            "작성",
            "작성한다",
            "밝힌다",
        }
        return [
            token
            for token in re.findall(r"[A-Za-z0-9가-힣]+", str(text or "").lower())
            if self._token_is_meaningful(token, stopwords)
        ]

    def _normalize_evidence_text(self, text: str) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(text or "").lower())

    def _simulation_report(self, cases: list[SimulatedResponseResult]) -> StudentResponseSimulationReport:
        flags = []
        for case in cases:
            if case.passed:
                continue
            if case.kind == SimulatedResponseKind.full_correct:
                flags.append("student_simulation_full_correct_scores_too_low")
            elif case.kind == SimulatedResponseKind.misconception:
                flags.append("student_simulation_misconception_scores_too_high")
            elif case.kind == SimulatedResponseKind.condition_missing:
                flags.append("student_simulation_condition_missing_scores_too_high")
            else:
                flags.append(f"student_simulation_{case.kind.value}_unexpected_score")
        return StudentResponseSimulationReport(cases=cases, passed=not flags, flags=list(dict.fromkeys(flags)))

    def _first_common_mistake(self, problem_data: dict) -> str | None:
        for item in (problem_data.get("rubric") or []):
            if not isinstance(item, dict):
                continue
            for mistake in item.get("common_mistakes") or []:
                mistake_text = str(mistake).strip()
                if mistake_text:
                    return mistake_text
        for item in (problem_data.get("choice_diagnostics") or []):
            if isinstance(item, dict) and item.get("is_correct") is not True:
                text = str(item.get("why_plausible") or "").strip()
                if text:
                    return text
        return None

    def _source_grounding_notes(self, *, source_refs: list[SourceRef], chunks: list[RetrievedChunk]) -> list[str]:
        if not source_refs:
            return ["retrieved evidence was insufficient for this item"]
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        notes = []
        for ref in source_refs:
            chunk = chunk_by_id.get(ref.chunk_id)
            if chunk is None:
                continue
            label = ref.section_title or "source section"
            notes.append(f"{ref.chunk_id} supports this item from {label}.")
        return notes

    def _target_concept(self, *, problem_data: dict, request: GenerateProblemRequest) -> str:
        concepts = [str(concept).strip() for concept in (problem_data.get("concepts") or []) if str(concept).strip()]
        return concepts[0] if concepts else request.concepts[0]

    def _prerequisite_concepts(self, *, problem_data: dict, request: GenerateProblemRequest) -> list[str]:
        concepts = [str(concept).strip() for concept in (problem_data.get("concepts") or request.concepts) if str(concept).strip()]
        target = concepts[0] if concepts else None
        return [concept for concept in concepts[1:] if concept != target][:12]

    def _observable_evidence(self, problem_data: dict) -> list[str]:
        if problem_data.get("type") == ProblemType.multiple_choice.value:
            return ["정답 보기를 고른다.", "오답 보기에 담긴 오개념을 피한다."]
        rubric = [item for item in (problem_data.get("rubric") or []) if isinstance(item, dict)]
        evidence = []
        for item in rubric:
            criterion = str(item.get("criterion") or "").strip()
            if criterion:
                evidence.append(criterion)
        return evidence or ["답안에 핵심 개념과 근거를 포함한다."]

    def _expected_reasoning_steps(self, *, problem_data: dict, difficulty_profile: DifficultyProfile) -> list[str]:
        steps = ["문제 조건에서 묻는 개념을 확인한다."]
        if difficulty_profile.requires_calculation:
            steps.append("자료의 공식이나 관계식을 조건에 맞게 적용한다.")
            steps.append("값과 단위를 확인해 결론을 낸다.")
        if difficulty_profile.requires_comparison:
            steps.append("비교 대상의 공통점과 차이를 구분한다.")
        if difficulty_profile.requires_error_analysis:
            steps.append("틀린 추론이나 빠진 조건을 찾아 바로잡는다.")
        if difficulty_profile.requires_transfer:
            steps.append("자료의 관계를 새로운 상황에 옮겨 적용한다.")
        if problem_data.get("type") == ProblemType.multiple_choice.value:
            steps.append("각 보기가 어떤 오개념과 연결되는지 점검한다.")
        return list(dict.fromkeys(steps))[:12]

    def _common_misconceptions(self, problem_data: dict) -> list[str]:
        misconceptions = []
        for item in (problem_data.get("choice_diagnostics") or []):
            if not isinstance(item, dict) or item.get("is_correct") is True:
                continue
            value = str(item.get("why_plausible") or item.get("misconception_id") or "").strip()
            if value:
                misconceptions.append(value)
        for item in (problem_data.get("rubric") or []):
            if isinstance(item, dict):
                misconceptions.extend(str(value).strip() for value in item.get("common_mistakes") or [] if str(value).strip())
        return list(dict.fromkeys(misconceptions))[:12]

    def _context_strategy(self, *, item_model_id: ItemModelId, difficulty_profile: DifficultyProfile) -> str:
        if difficulty_profile.requires_transfer:
            return "자료의 핵심 관계는 유지하되, 문제 상황은 새 조건으로 바꾼다."
        if item_model_id == ItemModelId.misconception_contrast:
            return "오답 보기에 흔한 오개념을 반영해 진단 가능하게 만든다."
        if item_model_id == ItemModelId.procedure_with_missing_step:
            return "풀이 절차의 핵심 단계를 드러내고 그 단계의 수행 여부를 본다."
        return "자료에 근거한 핵심 개념을 직접 확인한다."

    def _korean_cognitive_verb(self, level: CognitiveLevel) -> str:
        return {
            CognitiveLevel.recall: "기억",
            CognitiveLevel.understand: "이해",
            CognitiveLevel.apply: "적용",
            CognitiveLevel.analyze: "분석",
            CognitiveLevel.evaluate: "평가",
            CognitiveLevel.create: "구성",
        }[level]

    def _vague_constructed_response(self, *, problem_data: dict, request: GenerateProblemRequest) -> bool:
        if problem_data.get("type") != ProblemType.short_answer.value:
            return False
        if not (
            request.difficulty == Difficulty.hard
            or request.depth == ProblemDepth.deep
            or request.target_rigor == TargetRigor.high
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
        ):
            return False
        question = str(problem_data.get("question") or "").strip()
        vague_patterns = ("설명해", "서술하", "무엇인지", "정의하", "의미를 쓰")
        requirement_cues = ("조건", "근거", "비교", "계산", "단계", "예측", "판단", "오류", "자료", "관계")
        return any(pattern in question for pattern in vague_patterns) and not any(cue in question for cue in requirement_cues)

    def _misconception_score(self, problem_data: dict) -> float:
        if problem_data.get("type") == ProblemType.multiple_choice.value:
            diagnostics = [item for item in (problem_data.get("choice_diagnostics") or []) if isinstance(item, dict)]
            incorrect = [item for item in diagnostics if item.get("is_correct") is not True]
            if not incorrect:
                return 0.0
            useful = [
                item
                for item in incorrect
                if str(item.get("why_plausible") or "").strip() and str(item.get("repair_strategy") or "").strip()
            ]
            return round(len(useful) / len(incorrect), 3)
        misconceptions = self._common_misconceptions(problem_data)
        return 1.0 if misconceptions else 0.5

    def _problem_text(self, problem_data: dict) -> str:
        parts = [
            str(problem_data.get("question") or ""),
            str((problem_data.get("answer") or {}).get("text") or ""),
            str(problem_data.get("explanation") or ""),
        ]
        parts.extend(str(choice.get("text") or "") for choice in (problem_data.get("choices") or []) if isinstance(choice, dict))
        parts.extend(str(value) for value in (problem_data.get("choice_explanations") or {}).values())
        for item in (problem_data.get("rubric") or []):
            if not isinstance(item, dict):
                continue
            parts.append(str(item.get("criterion") or ""))
            parts.extend(str(value) for value in item.get("expected_evidence") or [])
        return " ".join(parts)
