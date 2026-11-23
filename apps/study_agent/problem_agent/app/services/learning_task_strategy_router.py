from __future__ import annotations

import re
from collections import Counter

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    CognitiveOperation,
    ContentForm,
    LearningTaskStrategyProfile,
    ProblemStrategy,
    ResponseMode,
    SubjectDomain,
    TargetRigor,
)


class LearningTaskStrategyRouter:
    """Low-cost heuristic router for learning task strategy.

    Subject labels are only hints. The actual generation strategy is selected
    from content forms, cognitive operations, and response modes so unknown
    subjects can still receive a useful generic strategy.
    """

    _FORMULA_RE = re.compile(
        r"([A-Za-z가-힣]\w*\s*=\s*[A-Za-z0-9가-힣]|"
        r"\d+(?:\.\d+)?\s*[+\-*/^]\s*\d+(?:\.\d+)?|"
        r"∝|≤|≥|√|Σ|∫)"
    )
    _TABLE_RE = re.compile(r"(\t|\|.+\||\brow\b|\bcolumn\b|(?:^|\s)표\s*\d+|표\s*[:：])", re.IGNORECASE)
    _CODE_RE = re.compile(r"\b(def|class|return|for|while|if|else|SELECT|function|const|let|var)\b")
    _CONTENT_TYPE_LABELS = {
        "flashcard": "개념 카드",
        "cloze": "빈칸",
        "true_false": "OX",
        "ordering": "순서 배열",
        "matching": "매칭",
        "worked_example": "풀이 예시",
        "mistake_drill": "오답 맞춤 연습",
        "mini_exam": "미니 시험",
        "concept_summary_card": "핵심 정리 카드",
    }
    _FORM_LABELS = {
        ContentForm.definition: "개념 설명",
        ContentForm.formula: "수식",
        ContentForm.procedure: "절차",
        ContentForm.concept_relation: "개념 관계",
        ContentForm.passage: "지문",
        ContentForm.case: "사례",
        ContentForm.data_table: "표",
        ContentForm.graph: "그래프",
        ContentForm.code: "코드",
        ContentForm.argument: "논증",
        ContentForm.timeline: "시간 흐름",
    }

    def route(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
    ) -> LearningTaskStrategyProfile:
        text = self._combined_text(request=request, chunks=chunks)
        subject_domain, subject_score = self._detect_subject_domain(text)
        topic_label, core_keywords = self._extract_topic(request=request, chunks=chunks, text=text)
        content_forms = self._detect_content_forms(text=text, chunks=chunks, request=request)
        cognitive_operations = self._select_operations(request=request, content_forms=content_forms)
        response_modes = self._select_response_modes(request=request, content_forms=content_forms)
        recommended_strategies = self._select_strategies(
            request=request,
            content_forms=content_forms,
            cognitive_operations=cognitive_operations,
        )
        avoid_strategies = self._select_avoid_strategies(
            content_forms=content_forms,
            recommended_strategies=recommended_strategies,
        )
        confidence = self._confidence(
            subject_score=subject_score,
            content_forms=content_forms,
            chunks=chunks,
        )
        strategy_id = self._strategy_id(
            content_forms=content_forms,
            cognitive_operations=cognitive_operations,
            response_modes=response_modes,
        )
        (
            selectable_content_types,
            available_content_types,
            recommended_content_types,
            not_recommended_content_types,
            content_type_reason,
        ) = self._select_learning_content_types(
            request=request,
            chunks=chunks,
            content_forms=content_forms,
            core_keywords=core_keywords,
        )

        return LearningTaskStrategyProfile(
            subject_domain=subject_domain,
            confidence=confidence,
            topic_label=topic_label,
            core_keywords=core_keywords,
            content_forms=content_forms,
            cognitive_operations=cognitive_operations,
            response_modes=response_modes,
            recommended_strategies=recommended_strategies,
            avoid_strategies=avoid_strategies,
            selectable_learning_content_types=selectable_content_types,
            available_learning_content_types=available_content_types,
            recommended_learning_content_types=recommended_content_types,
            not_recommended_learning_content_types=not_recommended_content_types,
            learning_content_type_reason=content_type_reason,
            strategy_id=strategy_id,
            reason=self._reason(content_forms=content_forms, cognitive_operations=cognitive_operations),
        )

    def _combined_text(self, *, request: GenerateProblemRequest, chunks: list[RetrievedChunk]) -> str:
        parts = [*request.concepts]
        for chunk in chunks:
            parts.extend(
                [
                    chunk.section_title or "",
                    chunk.content,
                    *chunk.concepts,
                    *chunk.tags,
                    self._metadata_text(chunk.metadata),
                ]
            )
        return "\n".join(parts).lower()

    def _detect_subject_domain(self, text: str) -> tuple[SubjectDomain, int]:
        keyword_map: list[tuple[SubjectDomain, tuple[str, ...]]] = [
            (
                SubjectDomain.math,
                ("함수", "방정식", "미분", "적분", "확률", "기하", "행렬", "수열", "공식", "계산"),
            ),
            (
                SubjectDomain.science,
                ("실험", "가설", "법칙", "반응", "세포", "에너지", "가속도", "질량", "힘", "전류"),
            ),
            (
                SubjectDomain.korean_language,
                ("지문", "화자", "서술자", "작품", "문학", "주제", "비유", "문맥", "표현"),
            ),
            (
                SubjectDomain.social_studies,
                ("역사", "정책", "제도", "사건", "원인", "결과", "사회", "경제", "정치"),
            ),
            (
                SubjectDomain.english_or_foreign_language,
                ("grammar", "vocabulary", "reading", "문법", "독해", "어휘", "빈칸"),
            ),
            (
                SubjectDomain.computer_science,
                ("알고리즘", "복잡도", "배열", "함수", "코드", "데이터베이스", "class", "def ", "return"),
            ),
        ]
        scored = [
            (domain, sum(1 for keyword in keywords if keyword in text))
            for domain, keywords in keyword_map
        ]
        domain, score = max(scored, key=lambda item: item[1])
        if score == 0:
            return SubjectDomain.unknown, 0
        if score == 1:
            return SubjectDomain.general_concept, score
        return domain, score

    def _detect_content_forms(
        self,
        *,
        text: str,
        chunks: list[RetrievedChunk],
        request: GenerateProblemRequest,
    ) -> list[ContentForm]:
        global_forms = self._detect_content_forms_in_text(text, include_definition=False)
        chunk_forms = [
            self._dedupe(
                [
                    *self._detect_content_forms_in_text(self._chunk_text(chunk), include_definition=False),
                    *self._detect_content_forms_from_metadata(chunk),
                ]
            )
            for chunk in chunks
        ]
        form_counts = Counter(form for forms in chunk_forms for form in forms)
        relevant_chunk_forms = [
            form
            for chunk, forms in zip(chunks, chunk_forms)
            if self._chunk_matches_request(chunk=chunk, request=request)
            for form in forms
        ]

        forms: list[ContentForm] = []
        chunk_count = len(chunks)
        for form in ContentForm:
            if form == ContentForm.definition:
                continue
            if form in relevant_chunk_forms:
                forms.append(form)
                continue
            if chunk_count <= 2 and form in global_forms:
                forms.append(form)
                continue
            if form_counts[form] >= 2:
                forms.append(form)

        if not forms:
            forms.append(ContentForm.definition)
        elif ContentForm.definition not in forms and any(keyword in text for keyword in ("정의", "의미", "개념", "란 ", "이란")):
            forms.insert(0, ContentForm.definition)
        return self._dedupe(forms)

    def _detect_content_forms_in_text(self, text: str, *, include_definition: bool) -> list[ContentForm]:
        forms: list[ContentForm] = []
        if self._FORMULA_RE.search(text) or any(keyword in text for keyword in ("공식", "수식", "formula", "equation", "비례", "반비례", "계산")):
            forms.append(ContentForm.formula)
        if any(keyword in text for keyword in ("절차", "단계", "방법", "순서", "과정", "프로세스", "procedure", "process", "sequence")):
            forms.append(ContentForm.procedure)
        if any(keyword in text for keyword in ("관계", "영향", "원인", "결과", "클수록", "작아", "증가", "감소", "relation", "cause", "effect")):
            forms.append(ContentForm.concept_relation)
        if any(keyword in text for keyword in ("예시", "사례", "상황", "case", "scenario")):
            forms.append(ContentForm.case)
        if self._TABLE_RE.search(text):
            forms.append(ContentForm.data_table)
        if any(keyword in text for keyword in ("그래프", "도표", "축", "기울기", "graph", "chart")):
            forms.append(ContentForm.graph)
        if self._looks_like_code(text):
            forms.append(ContentForm.code)
        if any(keyword in text for keyword in ("주장", "근거", "반박", "논증", "관점", "argument", "claim", "evidence")):
            forms.append(ContentForm.argument)
        if any(keyword in text for keyword in ("연도", "시기", "이후", "이전", "timeline", "chronology")):
            forms.append(ContentForm.timeline)
        if any(keyword in text for keyword in ("지문", "문단", "문장", "글쓴이", "passage", "paragraph")):
            forms.append(ContentForm.passage)
        if include_definition and not forms:
            forms.append(ContentForm.definition)
        if include_definition and ContentForm.definition not in forms and any(
            keyword in text for keyword in ("정의", "의미", "개념", "란 ", "이란")
        ):
            forms.insert(0, ContentForm.definition)
        return self._dedupe(forms)

    def _extract_topic(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        text: str,
    ) -> tuple[str, list[str]]:
        explicit_concepts = [concept.strip() for concept in request.concepts if concept.strip()]
        chunk_concepts = [concept.strip() for chunk in chunks for concept in chunk.concepts if concept.strip()]
        section_titles = [chunk.section_title.strip() for chunk in chunks if chunk.section_title and chunk.section_title.strip()]
        topic_sources = [*chunk_concepts, *section_titles]
        repeated_topic = self._dominant_topic(topic_sources)
        if explicit_concepts and not self._is_generic_topic(explicit_concepts[0]):
            topic_label = explicit_concepts[0]
        else:
            topic_label = repeated_topic or (section_titles[0] if section_titles else "unknown")
        token_counts = Counter(
            token
            for token in re.findall(r"[A-Za-z0-9가-힣]+", text)
            if len(token) >= 2 and token not in self._stopwords()
        )
        frequent_tokens = [token for token, _count in token_counts.most_common(12)]
        keywords = self._dedupe([*explicit_concepts, *chunk_concepts, *section_titles, *frequent_tokens])
        return topic_label[:80], keywords[:12]

    def _select_operations(
        self,
        *,
        request: GenerateProblemRequest,
        content_forms: list[ContentForm],
    ) -> list[CognitiveOperation]:
        operations: list[CognitiveOperation] = [CognitiveOperation.explain]
        if ContentForm.formula in content_forms:
            operations.extend([CognitiveOperation.apply, CognitiveOperation.calculate])
        if ContentForm.concept_relation in content_forms:
            operations.extend([CognitiveOperation.apply, CognitiveOperation.compare])
        if ContentForm.procedure in content_forms:
            operations.append(CognitiveOperation.apply)
        if ContentForm.passage in content_forms or ContentForm.argument in content_forms:
            operations.extend([CognitiveOperation.infer, CognitiveOperation.analyze])
        if ContentForm.case in content_forms:
            operations.extend([CognitiveOperation.apply, CognitiveOperation.analyze])
        if ContentForm.code in content_forms:
            operations.extend([CognitiveOperation.analyze, CognitiveOperation.design])
        if request.target_rigor == TargetRigor.high:
            operations.append(CognitiveOperation.analyze)
        return self._dedupe(operations)

    def _select_response_modes(
        self,
        *,
        request: GenerateProblemRequest,
        content_forms: list[ContentForm],
    ) -> list[ResponseMode]:
        modes = [ResponseMode(request.type.value)]
        if ContentForm.formula in content_forms:
            modes.append(ResponseMode.calculation)
        if ContentForm.code in content_forms:
            modes.append(ResponseMode.code_answer)
        if ContentForm.argument in content_forms and request.type.value == "short_answer":
            modes.append(ResponseMode.essay)
        return self._dedupe(modes)

    def _select_strategies(
        self,
        *,
        request: GenerateProblemRequest,
        content_forms: list[ContentForm],
        cognitive_operations: list[CognitiveOperation],
    ) -> list[ProblemStrategy]:
        strategies: list[ProblemStrategy] = [ProblemStrategy.basic_concept_check]
        if CognitiveOperation.apply in cognitive_operations:
            strategies.append(ProblemStrategy.near_transfer_application)
        if ContentForm.formula in content_forms:
            strategies.extend([ProblemStrategy.formula_application, ProblemStrategy.calculation])
        if ContentForm.concept_relation in content_forms:
            strategies.extend([ProblemStrategy.comparison_judgment, ProblemStrategy.variable_prediction])
        if ContentForm.passage in content_forms or ContentForm.argument in content_forms:
            strategies.append(ProblemStrategy.passage_evidence)
        if ContentForm.case in content_forms:
            strategies.append(ProblemStrategy.case_analysis)
        if ContentForm.code in content_forms:
            strategies.append(ProblemStrategy.code_reasoning)
        if request.target_rigor == TargetRigor.high and ProblemStrategy.near_transfer_application not in strategies:
            strategies.append(ProblemStrategy.near_transfer_application)
        return self._dedupe(strategies)

    def _select_avoid_strategies(
        self,
        *,
        content_forms: list[ContentForm],
        recommended_strategies: list[ProblemStrategy],
    ) -> list[ProblemStrategy]:
        avoid: list[ProblemStrategy] = []
        if ContentForm.formula not in content_forms:
            avoid.extend([ProblemStrategy.calculation, ProblemStrategy.formula_application])
        if ContentForm.code not in content_forms:
            avoid.append(ProblemStrategy.code_reasoning)
        if ContentForm.case not in content_forms and ProblemStrategy.case_analysis not in recommended_strategies:
            avoid.append(ProblemStrategy.case_analysis)
        return self._dedupe(avoid)

    def _select_learning_content_types(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        content_forms: list[ContentForm],
        core_keywords: list[str],
    ) -> tuple[list[str], list[str], list[str], list[str], str]:
        selectable = [
            "concept_summary_card",
            "flashcard",
            "true_false",
            "cloze",
            "matching",
            "ordering",
            "worked_example",
            "mini_exam",
        ]
        forms = set(content_forms)
        available = ["concept_summary_card", "flashcard", "true_false"]
        recommended = ["concept_summary_card", "flashcard"]

        if forms & {
            ContentForm.definition,
            ContentForm.formula,
            ContentForm.concept_relation,
            ContentForm.procedure,
            ContentForm.passage,
            ContentForm.argument,
            ContentForm.case,
        }:
            recommended.append("true_false")
        if forms & {
            ContentForm.definition,
            ContentForm.formula,
            ContentForm.concept_relation,
            ContentForm.passage,
            ContentForm.argument,
        }:
            available.append("cloze")
            recommended.append("cloze")
        if forms & {
            ContentForm.formula,
            ContentForm.procedure,
            ContentForm.data_table,
            ContentForm.graph,
            ContentForm.code,
        }:
            available.append("worked_example")
            recommended.append("worked_example")

        if forms & {ContentForm.procedure, ContentForm.timeline, ContentForm.code}:
            available.append("ordering")
            recommended.append("ordering")

        if self._has_matching_material(content_forms=content_forms, core_keywords=core_keywords):
            available.append("matching")
            recommended.append("matching")

        if len(chunks) >= 2 or len(request.concepts) >= 2 or request.count >= 3:
            available.append("mini_exam")
            recommended.append("mini_exam")

        available = self._dedupe(available)
        recommended = self._dedupe(recommended)
        all_content_types = [
            "flashcard",
            "cloze",
            "true_false",
            "ordering",
            "matching",
            "worked_example",
            "mistake_drill",
            "mini_exam",
            "concept_summary_card",
        ]
        not_recommended = [content_type for content_type in all_content_types if content_type not in recommended]
        return selectable, available, recommended, not_recommended, self._learning_content_type_reason(
            recommended=recommended,
            not_recommended=not_recommended,
            content_forms=content_forms,
        )

    def _confidence(
        self,
        *,
        subject_score: int,
        content_forms: list[ContentForm],
        chunks: list[RetrievedChunk],
    ) -> str:
        total_chars = sum(len(chunk.content) for chunk in chunks)
        if subject_score >= 2 and total_chars >= 500 and len(content_forms) >= 2:
            return "high"
        if total_chars >= 160 or content_forms != [ContentForm.definition]:
            return "medium"
        return "low"

    def _strategy_id(
        self,
        *,
        content_forms: list[ContentForm],
        cognitive_operations: list[CognitiveOperation],
        response_modes: list[ResponseMode],
    ) -> str:
        form = content_forms[0].value
        operation = cognitive_operations[-1].value if cognitive_operations else "explain"
        mode = response_modes[0].value
        return f"{form}_{operation}_{mode}_v1"

    def _reason(
        self,
        *,
        content_forms: list[ContentForm],
        cognitive_operations: list[CognitiveOperation],
    ) -> str:
        forms = ", ".join(form.value for form in content_forms)
        operations = ", ".join(operation.value for operation in cognitive_operations)
        return f"자료 형태({forms})와 필요한 풀이 방식({operations})을 보고 전략을 골랐다."

    def _learning_content_type_reason(
        self,
        *,
        recommended: list[str],
        not_recommended: list[str],
        content_forms: list[ContentForm],
    ) -> str:
        form_labels = ", ".join(self._FORM_LABELS.get(form, form.value) for form in content_forms)
        recommended_labels = ", ".join(
            self._CONTENT_TYPE_LABELS.get(content_type, content_type) for content_type in recommended[:4]
        )
        parts = [f"자료에서 {form_labels} 신호가 보여 {recommended_labels}부터 추천한다."]
        if "ordering" in not_recommended:
            parts.append("절차나 시간 흐름이 뚜렷하지 않으면 순서 배열은 우선 추천하지 않는다.")
        if "matching" in not_recommended:
            parts.append("서로 연결할 용어-설명 쌍이 충분하지 않으면 매칭은 우선 추천하지 않는다.")
        return " ".join(parts)

    def _dedupe(self, values: list) -> list:
        return list(dict.fromkeys(values))

    def _chunk_text(self, chunk: RetrievedChunk) -> str:
        return "\n".join(
            [
                chunk.section_title or "",
                chunk.content,
                " ".join(chunk.concepts),
                " ".join(chunk.tags),
                self._metadata_text(chunk.metadata),
            ]
        ).lower()

    def _metadata_text(self, metadata: dict) -> str:
        values: list[str] = []
        for value in metadata.values():
            if isinstance(value, str | int | float | bool):
                values.append(str(value))
            elif isinstance(value, list):
                values.extend(str(item) for item in value if isinstance(item, str | int | float | bool))
        return " ".join(values)

    def _detect_content_forms_from_metadata(self, chunk: RetrievedChunk) -> list[ContentForm]:
        aliases = {
            "definition": ContentForm.definition,
            "개념": ContentForm.definition,
            "정의": ContentForm.definition,
            "formula": ContentForm.formula,
            "equation": ContentForm.formula,
            "수식": ContentForm.formula,
            "공식": ContentForm.formula,
            "procedure": ContentForm.procedure,
            "process": ContentForm.procedure,
            "sequence": ContentForm.procedure,
            "절차": ContentForm.procedure,
            "순서": ContentForm.procedure,
            "concept_relation": ContentForm.concept_relation,
            "relation": ContentForm.concept_relation,
            "관계": ContentForm.concept_relation,
            "passage": ContentForm.passage,
            "지문": ContentForm.passage,
            "case": ContentForm.case,
            "사례": ContentForm.case,
            "data_table": ContentForm.data_table,
            "table": ContentForm.data_table,
            "표": ContentForm.data_table,
            "graph": ContentForm.graph,
            "chart": ContentForm.graph,
            "그래프": ContentForm.graph,
            "code": ContentForm.code,
            "코드": ContentForm.code,
            "argument": ContentForm.argument,
            "claim": ContentForm.argument,
            "논증": ContentForm.argument,
            "timeline": ContentForm.timeline,
            "chronology": ContentForm.timeline,
            "시간흐름": ContentForm.timeline,
        }
        tokens = [*chunk.tags]
        for value in chunk.metadata.values():
            if isinstance(value, str):
                tokens.extend(value.replace(";", ",").split(","))
            elif isinstance(value, list):
                tokens.extend(str(item) for item in value)
        forms = [aliases[token.strip().lower()] for token in tokens if token.strip().lower() in aliases]
        return self._dedupe(forms)

    def _has_matching_material(self, *, content_forms: list[ContentForm], core_keywords: list[str]) -> bool:
        if len([keyword for keyword in core_keywords if len(keyword.strip()) >= 2]) < 2:
            return False
        return bool(set(content_forms) & {ContentForm.definition, ContentForm.concept_relation, ContentForm.passage})

    def _chunk_matches_request(self, *, chunk: RetrievedChunk, request: GenerateProblemRequest) -> bool:
        chunk_text = self._chunk_text(chunk)
        concept_tokens = [
            token
            for concept in request.concepts
            for token in re.findall(r"[A-Za-z0-9가-힣]+", concept.lower())
            if len(token) >= 2 and token not in self._stopwords() and not self._is_generic_topic(token)
        ]
        if not concept_tokens:
            return True
        return any(token in chunk_text for token in concept_tokens)

    def _dominant_topic(self, topics: list[str]) -> str | None:
        cleaned = [topic.strip() for topic in topics if topic.strip() and not self._is_generic_topic(topic)]
        if not cleaned:
            return None
        counts = Counter(cleaned)
        topic, count = counts.most_common(1)[0]
        if count >= 2:
            return topic
        return cleaned[0]

    def _is_generic_topic(self, topic: str) -> bool:
        normalized = topic.strip().lower()
        generic_topics = {
            "전체",
            "전체 범위",
            "자료",
            "내용",
            "개념",
            "학습",
            "시험",
            "문제",
            "요약",
            "chapter",
            "unit",
            "all",
        }
        return normalized in generic_topics

    def _looks_like_code(self, text: str) -> bool:
        if "코드" in text:
            return True
        matches = self._CODE_RE.findall(text)
        if len(matches) >= 2:
            return True
        code_markers = ("{", "}", "();", "==", "!=", "=>", "import ", "from ")
        return bool(matches) and any(marker in text for marker in code_markers)

    def _stopwords(self) -> set[str]:
        return {
            "그리고",
            "그러나",
            "또는",
            "자료",
            "내용",
            "개념",
            "설명",
            "문제",
            "정답",
            "경우",
            "통해",
            "대한",
            "있는",
            "한다",
            "이다",
            "가장",
            "적절",
            "the",
            "and",
            "or",
            "for",
            "with",
            "that",
            "this",
        }
