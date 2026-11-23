from __future__ import annotations

import hashlib
import re

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import AtomConfidenceLevel, ContentAtom, ContentAtomType
from app.schemas.problems import ProblemStyle


class ContentAtomExtractor:
    """Deterministic source-structure extraction; never calls an external model."""

    MAX_ATOMS_PER_CHUNK = 5

    def extract(
        self,
        *,
        chunks: list[RetrievedChunk],
        concepts: list[str],
        problem_style: ProblemStyle | None = None,
        language: str | None = None,
    ) -> list[ContentAtom]:
        del problem_style, language
        atoms: list[ContentAtom] = []
        seen: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            for atom in self._extract_from_chunk(chunk=chunk, request_concepts=concepts)[: self.MAX_ATOMS_PER_CHUNK]:
                key = (atom.source_chunk_id, atom.atom_type.value, self._normalize(atom.statement))
                if key in seen:
                    continue
                seen.add(key)
                atoms.append(atom)
        return atoms

    def _extract_from_chunk(self, *, chunk: RetrievedChunk, request_concepts: list[str]) -> list[ContentAtom]:
        text = self._clean_text(chunk.content)
        atoms: list[ContentAtom] = []
        for sentence in self._sentences(text):
            for atom_type in self._atom_types(sentence):
                atoms.append(
                    self._atom(
                        chunk=chunk,
                        atom_type=atom_type,
                        statement=sentence,
                        request_concepts=request_concepts,
                    )
                )
            paired_comparison_confidence = self._paired_concept_comparison_confidence(sentence, request_concepts)
            if paired_comparison_confidence is not None:
                atoms.append(
                    self._atom(
                        chunk=chunk,
                        atom_type=ContentAtomType.comparison,
                        statement=sentence,
                        request_concepts=request_concepts,
                        confidence=paired_comparison_confidence,
                    )
                )
            if self._looks_like_relational_evidence_claim(sentence, request_concepts=request_concepts):
                atoms.append(
                    self._atom(
                        chunk=chunk,
                        atom_type=ContentAtomType.evidence_claim,
                        statement=sentence,
                        request_concepts=request_concepts,
                        confidence=0.60,
                    )
                )
            if self._looks_like_humanities_evidence_claim(sentence, chunk=chunk, request_concepts=request_concepts):
                atoms.append(
                    self._atom(
                        chunk=chunk,
                        atom_type=ContentAtomType.evidence_claim,
                        statement=sentence,
                        request_concepts=request_concepts,
                        confidence=0.62,
                    )
                )
        if not atoms and text:
            atoms.append(
                self._atom(
                    chunk=chunk,
                    atom_type=ContentAtomType.example_case if self._looks_like_example(text) else ContentAtomType.definition,
                    statement=text[:500],
                    request_concepts=request_concepts,
                    confidence=0.35,
                )
            )
        return atoms

    def _atom_types(self, text: str) -> list[ContentAtomType]:
        lowered = text.lower()
        checks: list[tuple[ContentAtomType, bool]] = [
            (ContentAtomType.formula, self._looks_like_formula(text)),
            (ContentAtomType.code_state, self._looks_like_code_state(text)),
            (ContentAtomType.data_table, self._looks_like_data_table(text)),
            (ContentAtomType.condition_exception, self._has_any(lowered, self.CONDITION_EXCEPTION_CUES)),
            (ContentAtomType.procedure, self._looks_like_procedure(text)),
            (ContentAtomType.comparison, self._has_any(lowered, self.COMPARISON_CUES)),
            (ContentAtomType.cause_effect, self._has_any(lowered, self.CAUSE_EFFECT_CUES)),
            (ContentAtomType.evidence_claim, self._has_any(lowered, self.EVIDENCE_CLAIM_CUES)),
            (ContentAtomType.classification, self._has_any(lowered, self.CLASSIFICATION_CUES)),
            (ContentAtomType.rule, self._has_any(lowered, self.RULE_CUES)),
            (ContentAtomType.definition, self._has_any(lowered, self.DEFINITION_CUES)),
            (ContentAtomType.example_case, self._looks_like_example(text)),
        ]
        return [atom_type for atom_type, matched in checks if matched]

    def _atom(
        self,
        *,
        chunk: RetrievedChunk,
        atom_type: ContentAtomType,
        statement: str,
        request_concepts: list[str],
        confidence: float | None = None,
    ) -> ContentAtom:
        concepts = self._concept_overlap(statement, [*request_concepts, *chunk.concepts])
        score = confidence if confidence is not None else self._confidence(atom_type=atom_type, concepts=concepts)
        return ContentAtom(
            atom_id=self._atom_id(chunk.chunk_id, atom_type, statement),
            atom_type=atom_type,
            source_chunk_id=chunk.chunk_id,
            statement=statement[:1000].strip(),
            evidence_quote=statement[:500].strip() or None,
            concepts=concepts,
            symbols=self._symbols(statement),
            variables=self._variables(statement),
            conditions=self._cue_phrases(statement, self.CONDITION_EXCEPTION_CUES),
            exceptions=self._cue_phrases(statement, ("unless", "except", "however", "단", "예외", "제외", "다만")),
            examples=self._cue_phrases(statement, ("example", "예", "간단예제")),
            confidence=score,
            confidence_level=self._confidence_level(score),
        )

    def _confidence(self, *, atom_type: ContentAtomType, concepts: list[str]) -> float:
        base = {
            ContentAtomType.formula: 0.88,
            ContentAtomType.rule: 0.78,
            ContentAtomType.procedure: 0.76,
            ContentAtomType.evidence_claim: 0.74,
            ContentAtomType.data_table: 0.74,
            ContentAtomType.code_state: 0.74,
            ContentAtomType.comparison: 0.72,
            ContentAtomType.condition_exception: 0.72,
        }.get(atom_type, 0.62)
        return min(1.0, base + (0.08 if concepts else 0.0))

    def _confidence_level(self, confidence: float) -> AtomConfidenceLevel:
        if confidence >= 0.75:
            return AtomConfidenceLevel.high
        if confidence >= 0.55:
            return AtomConfidenceLevel.medium
        return AtomConfidenceLevel.low

    def _sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?。])\s+|[\n\r]+", text)
        return [part.strip(" -•\t") for part in parts if len(part.strip()) >= 12]

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _has_any(self, text: str, cues: tuple[str, ...]) -> bool:
        return any(cue in text for cue in cues)

    def _looks_like_formula(self, text: str) -> bool:
        return bool(
            re.search(r"[A-Za-z가-힣][\w가-힣\s()+\\/-]{0,40}=\s*[-A-Za-z0-9가-힣$]", text)
            or re.search(r"\d+(?:\.\d+)?\s*[+\-*/x×÷%]\s*\d+", text)
            or re.search(r"\b(?:log|max|min|sum|avg|mean)\s*\(", text.lower())
        )

    def _looks_like_procedure(self, text: str) -> bool:
        return bool(re.search(r"(?:^|\s)(?:\d+[\).]|step\s+\d+)", text.lower())) or self._has_any(
            text.lower(), self.PROCEDURE_CUES
        )

    def _looks_like_data_table(self, text: str) -> bool:
        return bool(text.count("|") >= 2 or re.search(r"\b(row|column|table|dataset)\b", text.lower())) or self._has_any(
            text.lower(), ("표", "그래프", "데이터", "행", "열")
        )

    def _looks_like_code_state(self, text: str) -> bool:
        lowered = text.lower()
        return bool(re.search(r"\b(class|function|return|for|while|if)\b", lowered)) or self._has_any(
            lowered, ("stack", "queue", "state", "객체", "메모리", "스택", "큐")
        )

    def _looks_like_example(self, text: str) -> bool:
        lowered = text.lower()
        return self._has_any(lowered, ("example", "예", "간단예제")) or bool(
            re.search(r"\b(?:given|suppose|assume)\b", lowered)
        )

    def _paired_concept_comparison_confidence(self, text: str, request_concepts: list[str]) -> float | None:
        mentioned = self._concept_overlap(text, request_concepts)
        if len(mentioned) < 2:
            return None
        if self._has_peer_acronym_pair(mentioned):
            return 0.58
        if self._has_peer_ascii_concept_pair(mentioned):
            return 0.55
        return None

    def _has_peer_acronym_pair(self, concepts: list[str]) -> bool:
        acronym_count = 0
        for concept in concepts:
            compact = re.sub(r"[^A-Za-z0-9]", "", concept)
            if 2 <= len(compact) <= 8 and compact.upper() == compact and any(char.isalpha() for char in compact):
                acronym_count += 1
        return acronym_count >= 2

    def _has_peer_ascii_concept_pair(self, concepts: list[str]) -> bool:
        ascii_concepts = [concept.lower().strip() for concept in concepts if concept.isascii()]
        if len(ascii_concepts) < 2:
            return False
        for left_index, left in enumerate(ascii_concepts):
            for right in ascii_concepts[left_index + 1 :]:
                if left in right or right in left:
                    continue
                if 1 <= len(left.split()) <= 3 and 1 <= len(right.split()) <= 3:
                    return True
        return False

    def _looks_like_relational_evidence_claim(self, text: str, *, request_concepts: list[str]) -> bool:
        if len(self._concept_overlap(text, request_concepts)) < 2:
            return False
        lowered = text.lower()
        return self._has_any(
            lowered,
            (
                "uses",
                "using",
                "requires",
                "depends on",
                "is needed",
                "needed for",
                "needed to",
                "이용",
                "필요",
                "통해",
                "근거",
                "조건",
                "과정",
            ),
        )

    def _looks_like_humanities_evidence_claim(
        self,
        text: str,
        *,
        chunk: RetrievedChunk,
        request_concepts: list[str],
    ) -> bool:
        lowered = text.lower()
        searchable_concepts = " ".join([*request_concepts, *chunk.concepts]).lower()
        discourse_or_feature = self._has_any(
            f"{lowered} {searchable_concepts}",
            (
                "discourse",
                "genre",
                "context",
                "register",
                "textual feature",
                "feature",
                "interpretation",
                "담화",
                "장르",
                "맥락",
                "문체",
                "텍스트 특징",
                "해석",
            ),
        )
        relation_or_interpretation = self._has_any(
            lowered,
            (
                "suggests",
                "indicates",
                "shows",
                "implies",
                "according to",
                "based on",
                "interpretation",
                "relates",
                "signals",
                "시사한다",
                "보여준다",
                "나타낸다",
                "해석",
                "자료에 따르면",
                "패턴",
            ),
        )
        return discourse_or_feature and relation_or_interpretation

    def _concept_overlap(self, text: str, concepts: list[str]) -> list[str]:
        lowered = text.lower()
        result: list[str] = []
        for concept in concepts:
            concept_text = str(concept or "").strip()
            if concept_text and concept_text.lower() in lowered and concept_text not in result:
                result.append(concept_text)
        return result[:12]

    def _symbols(self, text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"\$([^$]{1,40})\$", text)))[:20]

    def _variables(self, text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"\b[A-Za-z]\w{0,5}\b(?=\s*=)", text)))[:20]

    def _cue_phrases(self, text: str, cues: tuple[str, ...]) -> list[str]:
        lowered = text.lower()
        return [cue for cue in cues if cue in lowered][:10]

    def _atom_id(self, chunk_id: str, atom_type: ContentAtomType, statement: str) -> str:
        digest = hashlib.sha1(f"{chunk_id}:{atom_type.value}:{statement}".encode("utf-8")).hexdigest()[:12]
        return f"atom_{digest}"

    DEFINITION_CUES = ("is defined as", " is a ", "means", "definition", "정의", "란 ", "란?", "의미")
    CLASSIFICATION_CUES = ("types", "kinds", "classified as", "구분", "종류", "분류")
    RULE_CUES = (
        "must",
        "should",
        "if ",
        " then",
        "requires",
        "원칙",
        "요건",
        "조건",
        "해야 한다",
        "기록한다",
        "인식한다",
        "사용된다",
        "연결된다",
        "판단한다",
    )
    PROCEDURE_CUES = ("process", "sequence", "algorithm", "순서", "과정", "단계")
    COMPARISON_CUES = (
        "versus",
        "compared with",
        "compared to",
        "while",
        "whereas",
        "in contrast",
        "unlike",
        "on the other hand",
        "differs",
        "similarity",
        "distinction",
        "tradeoff",
        "advantage",
        "limitation",
        "비교",
        "차이",
        "반면",
        "반대로",
        "유사",
        "구분",
        "장점",
        "단점",
        "한계",
        "와 달리",
        "과 달리",
        "에 비해",
    )
    CAUSE_EFFECT_CUES = (
        "because",
        "therefore",
        "leads to",
        "causes",
        "영향",
        "증가하면",
        "감소하면",
        "결과",
        "변화",
        "작용할 때",
    )
    CONDITION_EXCEPTION_CUES = ("unless", "except", "only if", "however", "단", "예외", "제외", "다만")
    EVIDENCE_CLAIM_CUES = (
        "evidence",
        "claim",
        "supports",
        "suggests",
        "indicates",
        "shows",
        "implies",
        "according to",
        "based on",
        "observation",
        "result",
        "finding",
        "pattern",
        "interpretation",
        "근거",
        "주장",
        "뒷받침",
        "자료에 따르면",
        "시사한다",
        "보여준다",
        "나타낸다",
        "결과",
        "해석",
        "관찰",
        "패턴",
    )
