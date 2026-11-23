import csv
import json
from pathlib import Path
import time
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.llm import LLMOutputValidationError
from app.schemas.problems import GenerateProblemRequest
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.quality import ProblemAnswerVerificationReport
from app.services.live_problem_generation_eval import (
    REPORT_HUMAN_REVIEW_CSV_NAME,
    REPORT_HUMAN_REVIEW_SUMMARY_JSON_NAME,
    REPORT_HUMAN_REVIEW_SUMMARY_MARKDOWN_NAME,
    REPORT_JSONL_NAME,
    REPORT_JSON_NAME,
    REPORT_MARKDOWN_NAME,
    LIVE_EVAL_REPORT_SCHEMA_VERSION,
    HumanReviewRecord,
    LiveProblemGenerationEvalCase,
    LiveProblemGenerationEvalReport,
    LiveProblemQualityDiagnostic,
    LIVE_EVAL_DATABASE_URL_WARNING,
    _commercial_quality_score_for_diagnostic,
    _problem_quality_diagnostic,
    _eval_database_url,
    _classify_bottleneck,
    _failed_case_result,
    _file_sha256,
    _percentile,
    _term_coverage,
    _threshold_failure_categories,
    _threshold_failures,
    load_live_problem_generation_cases,
    load_human_review_csv,
    live_eval_preflight_skip_message,
    live_problem_generation_preflight_from_env,
    run_live_problem_generation_eval,
    run_live_problem_generation_eval_from_env,
    summarize_human_review,
    validate_live_eval_report_freshness,
    write_human_review_summary,
)
from app.services.problem_answer_verifier import ProblemAnswerVerifier
from app.services.rejected_candidate_artifact_writer import (
    EVAL_USAGE_LEDGER_JSONL_NAME,
    REJECTED_CANDIDATES_JSONL_NAME,
    RejectedCandidateArtifactWriter,
)


class FakeSearchService:
    def __init__(self):
        self.chunks = [
            RetrievedChunk(
                chunk_id="chunk_force",
                document_id="physics_doc",
                content="뉴턴의 제2법칙은 F = ma이다. 같은 힘에서 질량이 커지면 가속도는 감소한다.",
                page=1,
                section_title="운동 법칙",
                concepts=["뉴턴 제2법칙", "질량", "가속도"],
                metadata={"score": 0.91},
            ),
            RetrievedChunk(
                chunk_id="chunk_relation",
                document_id="physics_doc",
                content="힘, 질량, 가속도의 관계를 조건에 적용해서 판단할 수 있다.",
                page=2,
                section_title="관계 적용",
                concepts=["힘", "질량", "가속도"],
                metadata={"distance": 0.12},
            ),
        ]

    def search_chunks(self, **kwargs):
        return self.chunks[: kwargs.get("top_k", len(self.chunks))]

    def get_chunks_by_ids(self, **kwargs):
        requested = set(kwargs.get("chunk_ids") or [])
        return [chunk for chunk in self.chunks if chunk.chunk_id in requested]


class ManyChunkSearchService(FakeSearchService):
    def __init__(self, count: int = 14):
        super().__init__()
        self.chunks = [
            RetrievedChunk(
                chunk_id=f"chunk_force_{index:02d}",
                document_id="physics_doc",
                content=(
                    "뉴턴의 제2법칙은 F = ma이다. 같은 힘에서 질량이 커지면 가속도는 감소한다. "
                    f"variation {index}"
                ),
                page=index + 1,
                section_title=f"운동 법칙 {index % 4}",
                concepts=["뉴턴 제2법칙", "질량", "가속도"],
                metadata={"score": max(0.1, 0.95 - index * 0.02)},
            )
            for index in range(count)
        ]

    def search_chunks(self, **kwargs):
        return list(self.chunks)


class CSE321IndexingSearchService:
    def __init__(self):
        self.chunks = [
            RetrievedChunk(
                chunk_id="6_CSE321_2026_Ch 11 Indexing.pdf_37_fe82fd3c5b91",
                document_id="cse321_indexing_live",
                content=(
                    "B[+] -Tree search performance: every node access may need a disk I/O. "
                    "Root caching and higher fanout can reduce tree height and disk I/O."
                ),
                page=22,
                section_title="B+ Tree Performance",
                concepts=["B+ tree", "disk I/O"],
                metadata={"score": 0.96},
            ),
            RetrievedChunk(
                chunk_id="6_CSE321_2026_Ch 11 Indexing.pdf_35_b2db4b0d271c",
                document_id="cse321_indexing_live",
                content=(
                    "Sparse indices form a hierarchy of sparse indices. "
                    "A sparse index stores entries for only some search-key values."
                ),
                page=24,
                section_title="Sparse Indices",
                concepts=["sparse index", "B+ tree"],
                metadata={"score": 0.93},
            ),
            RetrievedChunk(
                chunk_id="6_CSE321_2026_Ch 11 Indexing.pdf_16_7cb390f998f1",
                document_id="cse321_indexing_live",
                content=(
                    "Ordered Index Performance. Point queries search for one key value. "
                    "Range queries: search key value falling in a specified range. "
                    "We want to have balanced index trees for predictable lookup cost."
                ),
                page=11,
                section_title="Ordered Index Performance",
                concepts=["ordered index", "range query", "balanced index tree"],
                metadata={"score": 0.94},
            ),
            RetrievedChunk(
                chunk_id="6_CSE321_2026_Ch 11 Indexing.pdf_24_ee9cc148a35a",
                document_id="cse321_indexing_live",
                content="B[+] -Tree Index is a balanced tree index structure used for database indexing.",
                page=15,
                section_title="B+ Tree Index",
                concepts=["B+ tree", "index"],
                metadata={"score": 0.90},
            ),
        ]

    def search_chunks(self, **kwargs):
        return list(self.chunks)

    def get_chunks_by_ids(self, **kwargs):
        requested = set(kwargs.get("chunk_ids") or [])
        return [chunk for chunk in self.chunks if chunk.chunk_id in requested]


class QueryAwareSearchService:
    def __init__(self, *, enhanced_better: bool, latency_seconds: float = 0.005):
        self.enhanced_better = enhanced_better
        self.latency_seconds = latency_seconds
        self.calls = []

    def search_chunks(self, **kwargs):
        query = kwargs["query"]
        self.calls.append(query)
        time.sleep(self.latency_seconds)
        enhanced_query = query != "뉴턴 제2법칙 가속도"
        if enhanced_query:
            return [self._chunk("enhanced_chunk", self._enhanced_content())]
        return [self._chunk("baseline_chunk", self._baseline_content())]

    def get_chunks_by_ids(self, **kwargs):
        return []

    def _baseline_content(self) -> str:
        if self.enhanced_better:
            return "뉴턴의 제2법칙은 힘과 운동 상태를 다룬다."
        return "뉴턴의 제2법칙 baseline_only 질량 가속도 F = ma 관계를 설명한다."

    def _enhanced_content(self) -> str:
        if self.enhanced_better:
            return "뉴턴의 제2법칙 enhanced_only 질량 가속도 F = ma 관계를 조건에 적용한다."
        return "뉴턴의 제2법칙 질량 가속도 F = ma 관계를 조건에 적용한다."

    def _chunk(self, chunk_id: str, content: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id,
            document_id="physics_doc",
            content=content,
            page=1,
            section_title="운동 법칙",
            concepts=["뉴턴 제2법칙", "가속도"],
        )


class QueryModeSweepSearchService:
    def __init__(self, *, best_mode: str):
        self.best_mode = best_mode
        self.calls = []

    def search_chunks(self, **kwargs):
        query = kwargs["query"]
        mode = self._mode_from_query(query)
        self.calls.append((mode, query))
        return [self._chunk(mode)]

    def get_chunks_by_ids(self, **kwargs):
        return []

    def _mode_from_query(self, query: str) -> str:
        normalized = query.lower()
        if query == "뉴턴 제2법칙 가속도":
            return "baseline"
        if "조건을" in query or "application" in normalized or "transfer" in normalized or "analyze" in normalized:
            return "expanded"
        if any(term in query for term in ("적용", "사례", "조건", "상황", "비교")):
            return "hybrid"
        return "compact"

    def _chunk(self, mode: str) -> RetrievedChunk:
        if mode == self.best_mode:
            content = f"뉴턴 제2법칙 {mode}_marker 질량 가속도 F = ma 관계를 설명한다."
        else:
            content = "뉴턴 제2법칙은 질량 가속도 F = ma 관계를 설명한다."
        return RetrievedChunk(
            chunk_id=f"{mode}_chunk",
            document_id="physics_doc",
            content=content,
            page=1,
            section_title="운동 법칙",
            concepts=["뉴턴 제2법칙", "가속도"],
        )


class FakeProblemAgent:
    def __init__(self):
        self.llm = None
        self.last_generation_mode = None

    def generate(self, request, chunks, **kwargs):
        self.last_generation_mode = "llm"
        chunk_id = chunks[0].chunk_id
        return [
            {
                "document_id": request.document_id,
                "type": request.type.value,
                "difficulty": request.difficulty.value,
                "bloom_level": request.bloom_level.value,
                "question": "같은 힘이 작용할 때 질량이 커지면 가속도는 어떻게 변하는가?",
                "choices": None,
                "answer": {
                    "choice_id": None,
                    "text": "가속도는 감소한다. F = ma에서 힘이 같으면 가속도는 질량에 반비례하기 때문이다.",
                },
                "explanation": "자료의 F = ma 관계를 조건에 적용하면 질량 증가가 가속도 감소로 이어진다.",
                "choice_explanations": None,
                "choice_diagnostics": None,
                "rubric": [
                    {
                        "criterion": "F = ma 관계를 조건에 적용한다.",
                        "points": 1,
                        "expected_evidence": ["F = ma", "가속도"],
                    }
                ],
                "concepts": list(request.concepts),
                "source_chunk_ids": [chunk_id],
            }
        ]


class FakeUsageLLM:
    def __init__(self):
        self.last_usage = None
        self.last_model = None
        self.last_request_id = "req_fake_usage"

    def reset_last_call(self):
        self.last_usage = None
        self.last_model = None


class UsageTrackingProblemAgent(FakeProblemAgent):
    def __init__(self, *, model: str, input_tokens: int = 1000, output_tokens: int = 250):
        super().__init__()
        self.llm = FakeUsageLLM()
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.last_prompt_char_count = None

    def generate(self, request, chunks, **kwargs):
        self.llm.last_model = self.model
        self.llm.last_usage = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }
        self.last_prompt_char_count = 4321
        return super().generate(request, chunks, **kwargs)


class RejectingProblemAgent(FakeProblemAgent):
    def generate(self, request, chunks, **kwargs):
        problems = super().generate(request, chunks, **kwargs)
        problems[0]["concepts"] = ["unrequested concept"]
        return problems


class SchemaFailureProblemAgent(FakeProblemAgent):
    def __init__(self):
        super().__init__()
        self.llm = FakeUsageLLM()
        self.last_prompt_char_count = 777
        self.last_evidence_pack_atom_count = 2
        self.last_raw_context_char_count = 300
        self.last_compressed_prompt_enabled = True
        self.last_invalid_payload = None

    def generate(self, request, chunks, **kwargs):
        candidate = super().generate(request, chunks, **kwargs)[0]
        candidate["answer"] = {"choice_id": None, "text": "민감한 정답"}
        candidate["explanation"] = "민감한 해설"
        candidate["rubric"] = [{"criterion": "민감한 루브릭", "points": 1}]
        self.last_invalid_payload = {"problems": [candidate]}
        self.last_generation_mode = "llm"
        self.llm.last_model = "gpt-5.4-mini"
        self.llm.last_usage = {"input_tokens": 123, "output_tokens": 45, "total_tokens": 168}
        raise LLMOutputValidationError("fake schema validation failure")


class CountingProblemAgent(FakeProblemAgent):
    def __init__(self):
        super().__init__()
        self.generate_call_count = 0

    def generate(self, request, chunks, **kwargs):
        self.generate_call_count += 1
        problems = super().generate(request, chunks, **kwargs)
        problems[0]["question"] = (
            "조건: 같은 힘이 작용하는 두 물체 중 한 물체의 질량이 더 큰 상황에서, "
            "F = ma 관계를 적용하면 가속도는 어떻게 달라지는가?"
        )
        problems[0]["explanation"] = (
            "자료의 F = ma 관계에 따르면 힘이 일정할 때 가속도는 질량에 반비례한다. "
            "따라서 질량이 더 큰 물체의 가속도는 더 작아진다."
        )
        problems[0]["rubric"] = [
            {
                "criterion": "F = ma 관계를 조건에 적용한다.",
                "points": 1,
                "expected_evidence": ["힘이 일정할 때 질량과 가속도의 관계"],
                "common_mistakes": ["질량이 커져도 가속도가 변하지 않는다고 판단함"],
                "partial_credit_rules": ["관계식만 언급하면 부분 점수"],
            },
            {
                "criterion": "가속도 변화 방향을 해석한다.",
                "points": 1,
                "expected_evidence": ["질량이 더 크면 가속도는 더 작아짐"],
                "common_mistakes": ["질량과 가속도가 비례한다고 해석함"],
                "partial_credit_rules": ["감소 방향은 맞지만 이유가 부족하면 부분 점수"],
            },
        ]
        return problems


class CSE321IndexingProblemAgent:
    def __init__(self):
        self.llm = None
        self.last_generation_mode = None

    def generate(self, request, chunks, **kwargs):
        self.last_generation_mode = "llm"
        if request.type.value == "multiple_choice":
            return [self._ordered_index_mcq(request, chunks)]
        if "sparse index" in request.concepts:
            return [self._btree_short_answer(request, chunks)]
        return [self._control_short_answer(request, chunks)]

    def _btree_short_answer(self, request, chunks):
        cited = [
            chunk.chunk_id
            for chunk in chunks
            if chunk.chunk_id
            in {
                "6_CSE321_2026_Ch 11 Indexing.pdf_37_fe82fd3c5b91",
                "6_CSE321_2026_Ch 11 Indexing.pdf_35_b2db4b0d271c",
            }
        ]
        return {
            "document_id": request.document_id,
            "type": request.type.value,
            "difficulty": request.difficulty.value,
            "bloom_level": request.bloom_level.value,
            "question": (
                "B+ tree에서 fanout이 커지고 root가 메모리에 캐시되는 조건이 주어졌을 때, "
                "sparse index 계층과 disk I/O 비용 관점에서 검색 성능 변화를 분석하시오."
            ),
            "choices": None,
            "answer": {
                "choice_id": None,
                "text": (
                    "fanout이 커지면 트리 높이가 줄어 접근해야 할 노드 수가 감소하고, root 캐시는 "
                    "root 접근의 disk I/O를 줄인다. sparse index 계층은 일부 key entry로 상위 "
                    "index를 구성하므로 전체 검색 비용은 높이와 각 노드 접근 I/O에 의해 좌우된다."
                ),
            },
            "explanation": (
                "자료의 every node access may need a disk I/O 설명과 sparse indices hierarchy 설명을 "
                "함께 적용해야 한다."
            ),
            "choice_explanations": None,
            "choice_diagnostics": None,
            "rubric": [
                {
                    "criterion": "B+ tree fanout 변화가 트리 높이에 미치는 영향을 설명한다.",
                    "points": 2,
                    "expected_evidence": ["fanout", "tree height", "node access", "disk I/O"],
                    "common_mistakes": ["fanout 변화와 height 변화를 연결하지 않음"],
                    "partial_credit_rules": ["fanout 또는 height 중 하나만 설명하면 부분 점수"],
                },
                {
                    "criterion": "sparse index hierarchy와 root caching 조건을 disk I/O와 연결한다.",
                    "points": 2,
                    "expected_evidence": ["sparse indices", "hierarchy", "root caching", "disk I/O"],
                    "common_mistakes": ["sparse index를 dense index처럼 모든 key entry 저장으로 설명함"],
                    "partial_credit_rules": ["root caching 또는 sparse hierarchy 중 하나만 연결하면 부분 점수"],
                },
            ],
            "concepts": list(request.concepts),
            "source_chunk_ids": cited or [chunks[0].chunk_id],
        }

    def _ordered_index_mcq(self, request, chunks):
        chunk_id = "6_CSE321_2026_Ch 11 Indexing.pdf_16_7cb390f998f1"
        return {
            "document_id": request.document_id,
            "type": request.type.value,
            "difficulty": request.difficulty.value,
            "bloom_level": request.bloom_level.value,
            "question": (
                "자료 근거에 비추어, ordered index가 point query와 range query를 모두 처리하고 "
                "index tree가 skewed해질 수 있는 조건에서 가장 타당한 판단은?"
            ),
            "choices": [
                {
                    "id": "A",
                    "text": "range query는 지정된 search-key 범위를 찾으므로, predictable lookup cost를 위해 balanced index tree가 필요하다.",
                },
                {
                    "id": "B",
                    "text": "point query만 지원하면 range query도 같은 비용으로 자동 처리되므로 tree balance는 중요하지 않다.",
                },
                {
                    "id": "C",
                    "text": "ordered index는 key 순서를 쓰지 않으므로 range query에서 별도 이점이 없다.",
                },
                {
                    "id": "D",
                    "text": "balanced index tree는 sparse index에만 쓰이고 ordered index performance와는 관련이 없다.",
                },
            ],
            "answer": {
                "choice_id": "A",
                "text": "range query는 지정된 search-key 범위를 찾으므로, predictable lookup cost를 위해 balanced index tree가 필요하다.",
            },
            "explanation": (
                "자료는 range query를 specified range의 search-key value를 찾는 것으로 설명하고, "
                "balanced index trees가 필요하다고 말한다. 따라서 조건 판단은 range query와 "
                "balanced tree의 비용 안정성을 함께 연결해야 한다."
            ),
            "choice_explanations": {
                "A": "자료의 range query 설명과 balanced index tree 필요성을 직접 연결한다.",
                "B": "point query와 range query의 요구를 같게 보는 오개념이다.",
                "C": "ordered index의 정렬된 key 구조가 range query에 주는 이점을 놓쳤다.",
                "D": "balanced tree 필요성을 특정 index 형태로 과도하게 제한했다.",
            },
            "choice_diagnostics": [
                {"choice_id": "A", "is_correct": True, "mistake_type": "none"},
                {
                    "choice_id": "B",
                    "is_correct": False,
                    "mistake_type": "condition_ignored",
                    "misconception_id": "point_range_same_cost",
                    "why_plausible": "point query 설명만 보면 range query도 같은 탐색처럼 보일 수 있다.",
                    "repair_strategy": "specified range 조건이 추가 탐색 범위를 만든다는 점을 확인한다.",
                    "followup_problem_type": "range_query_boundary",
                },
                {
                    "choice_id": "C",
                    "is_correct": False,
                    "mistake_type": "wrong_concept_boundary",
                    "misconception_id": "ordered_index_not_ordered",
                    "why_plausible": "index라는 일반 용어만 보고 key order의 역할을 생략했다.",
                    "repair_strategy": "ordered index에서 search-key 순서가 range retrieval에 쓰이는지 분리한다.",
                    "followup_problem_type": "concept_boundary",
                },
                {
                    "choice_id": "D",
                    "is_correct": False,
                    "mistake_type": "overgeneralization",
                    "misconception_id": "balanced_tree_scope_error",
                    "why_plausible": "B+ tree나 sparse index 설명과 balanced tree 설명을 한 범위로 혼동했다.",
                    "repair_strategy": "balanced tree가 lookup cost 안정화와 연결되는 조건을 자료에서 찾는다.",
                    "followup_problem_type": "evidence_alignment",
                },
            ],
            "rubric": None,
            "concepts": list(request.concepts),
            "source_chunk_ids": [chunk_id],
        }

    def _control_short_answer(self, request, chunks):
        chunk_id = "6_CSE321_2026_Ch 11 Indexing.pdf_24_ee9cc148a35a"
        return {
            "document_id": request.document_id,
            "type": request.type.value,
            "difficulty": request.difficulty.value,
            "bloom_level": request.bloom_level.value,
            "question": "B+ tree index가 데이터베이스 indexing에서 쓰이는 핵심 이유를 간단히 설명하시오.",
            "choices": None,
            "answer": {
                "choice_id": None,
                "text": "B+ tree index는 balanced tree 구조로 search-key 기반 탐색을 효율적으로 지원한다.",
            },
            "explanation": "자료의 B[+] -Tree Index 설명은 balanced tree index structure와 database indexing 사용을 연결한다.",
            "choice_explanations": None,
            "choice_diagnostics": None,
            "rubric": [
                {
                    "criterion": "B+ tree index의 balanced tree 구조와 indexing 목적을 설명한다.",
                    "points": 1,
                    "expected_evidence": ["B+ tree", "balanced tree", "database indexing"],
                    "common_mistakes": ["일반 tree와 index 목적을 구분하지 않음"],
                    "partial_credit_rules": ["B+ tree 또는 index 목적 중 하나만 맞으면 부분 점수"],
                }
            ],
            "concepts": list(request.concepts),
            "source_chunk_ids": [chunk_id],
        }


class FailsFirstProblemAgent(FakeProblemAgent):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def generate(self, request, chunks, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(
                "Only 0 valid problems were generated out of 1: "
                "high-rigor multi-step item must require at least three reasoning steps; "
                'rejection_category_counts={"missing_reasoning_steps":2}; '
                'top_rejection_categories=["missing_reasoning_steps"]'
            )
        return super().generate(request, chunks, **kwargs)


class AlwaysFailsProblemAgent(FakeProblemAgent):
    def generate(self, request, chunks, **kwargs):
        raise RuntimeError(
            "Only 0 valid problems were generated out of 1: "
            "high-rigor multiple-choice item must require reasoning beyond recall; "
            'rejection_category_counts={"low_cognitive_demand":2}; '
            'top_rejection_categories=["low_cognitive_demand"]'
        )


class CitesAllRetrievedChunksProblemAgent(FakeProblemAgent):
    def generate(self, request, chunks, **kwargs):
        problems = super().generate(request, chunks, **kwargs)
        problems[0]["source_chunk_ids"] = [chunk.chunk_id for chunk in chunks]
        return problems


class SlowGenerationProblemAgent(FakeProblemAgent):
    def generate(self, request, chunks, **kwargs):
        time.sleep(0.2)
        return super().generate(request, chunks, **kwargs)


class FakePublisher:
    def __init__(self):
        self.published = []

    def publish_problem(self, problem):
        self.published.append(problem.id)
        return True


class FakeLLMJudge:
    def __init__(self):
        self.calls = []

    def judge_problem(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "problem_id": kwargs["problem"].id,
            "source_grounding_score": 0.9,
            "cognitive_rigor_score": 0.8,
            "distractor_quality_score": 0.7,
            "explanation_quality_score": 0.85,
            "difficulty_fit_score": 0.75,
            "overall_score": 0.82,
            "failure_reasons": [],
            "recommended_action": "pass",
        }


class FakeAnswerVerifier:
    def __init__(self):
        self.calls = []

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        problem = kwargs["problem"]
        return ProblemAnswerVerificationReport(
            verified=True,
            confidence="high",
            answer_correctness_score=0.45,
            ambiguity_score=0.1,
            grounding_score=0.8,
            issues=["fake verifier found answer correctness risk"],
            recommended_action="reject",
        )


def _settings(**overrides) -> Settings:
    data = {
        "DATABASE_URL": "sqlite+pysqlite://",
        "RAG_AGENT_URL": None,
        "SEARCH_AGENT_URL": None,
        "OPENAI_API_KEY": None,
        "LLM_FALLBACK_ENABLED": True,
        "GENERATED_ARTIFACT_PUBLISH_ENABLED": True,
    }
    data.update(overrides)
    return Settings(**data)


def _write_cases(path: Path, *rows: dict) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_human_review_csv(path: Path, *rows: dict) -> None:
    fieldnames = [
        "case_id",
        "problem_id",
        "reviewer_problem_quality_score",
        "reviewer_source_grounding_score",
        "reviewer_difficulty_fit_score",
        "reviewer_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_live_preflight_reports_missing_required_env_vars(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case())
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.delenv("RAG_AGENT_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    report = live_problem_generation_preflight_from_env()

    assert report.enabled is True
    assert report.can_run is False
    assert "RAG_AGENT_URL" in report.missing_env_vars
    assert "OPENAI_API_KEY" in report.missing_env_vars
    assert report.cases_path_exists is True
    assert report.case_count == 1


def test_live_preflight_reports_placeholder_document_ids(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(
        cases_path,
        _base_case(
            id="placeholder_case",
            document_id="REPLACE_WITH_REAL_DOCUMENT_TITLE",
        ),
    )
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.setenv("RAG_AGENT_URL", "http://localhost:8001")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")

    report = live_problem_generation_preflight_from_env()

    assert report.can_run is False
    assert report.placeholder_case_ids == ["placeholder_case"]
    assert report.placeholder_document_ids == ["REPLACE_WITH_REAL_DOCUMENT_TITLE"]


def test_live_preflight_blocks_placeholder_concepts_and_expected_terms(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(
        cases_path,
        _base_case(
            id="placeholder_terms",
            concepts=["REPLACE_WITH_CONCEPT"],
            expected_search_terms=["REPLACE_WITH_SEARCH_TERM"],
            expected_problem_terms=["REPLACE_WITH_PROBLEM_TERM"],
        ),
    )
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.setenv("RAG_AGENT_URL", "http://localhost:8001")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")

    report = live_problem_generation_preflight_from_env()

    assert report.can_run is False
    assert report.placeholder_case_ids == ["placeholder_terms"]
    assert report.placeholder_document_ids == []


def test_live_preflight_can_run_with_real_env_and_real_case_ids(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case(document_id="physics_doc_uploaded"))
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.setenv("RAG_AGENT_URL", "http://localhost:8001")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")

    report = live_problem_generation_preflight_from_env()

    assert report.can_run is True
    assert report.missing_env_vars == []
    assert report.placeholder_case_ids == []
    assert report.case_count == 1


def test_live_preflight_warns_when_database_url_opt_in_is_enabled(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case(document_id="physics_doc_uploaded"))
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL", "true")
    monkeypatch.setenv("RAG_AGENT_URL", "http://localhost:8001")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")

    report = live_problem_generation_preflight_from_env()

    assert report.can_run is True
    assert LIVE_EVAL_DATABASE_URL_WARNING in report.warnings


def test_live_preflight_skip_message_lists_names_without_secret_values(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case())
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.delenv("RAG_AGENT_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-key")

    report = live_problem_generation_preflight_from_env()
    message = live_eval_preflight_skip_message(report)

    assert "RAG_AGENT_URL" in message
    assert "OPENAI_API_KEY" not in message
    assert "secret-test-key" not in message


def test_live_preflight_requires_openai_key_when_llm_judge_enabled(tmp_path, monkeypatch):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case(document_id="physics_doc_uploaded"))
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "true")
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_CASES", str(cases_path))
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_LLM_JUDGE_ENABLED", "true")
    monkeypatch.setenv("RAG_AGENT_URL", "http://localhost:8001")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    report = live_problem_generation_preflight_from_env()

    assert report.can_run is False
    assert "OPENAI_API_KEY" in report.missing_env_vars
    assert any("LLM judge" in warning for warning in report.warnings)


def _base_case(**overrides):
    row = {
        "id": "physics_force_application",
        "description": "뉴턴 제2법칙 조건 적용형 주관식 생성",
        "document_id": "physics_doc",
        "concepts": ["뉴턴 제2법칙", "가속도"],
        "request": {
            "type": "short_answer",
            "count": 1,
            "difficulty": "medium",
            "bloom_level": "understand",
            "user_requirements": "조건을 적용해서 가속도 변화를 판단하는 문제",
        },
        "expected_search_terms": ["뉴턴", "질량", "가속도"],
        "expected_problem_terms": ["질량", "가속도"],
        "min_returned_chunks": 1,
        "min_cited_chunks_per_problem": 1,
        "min_average_quality_score": 0.0,
        "max_reject_rate": 0.60,
        "max_total_ms": 60000,
    }
    row.update(overrides)
    return row


def _high_rigor_threshold_request(problem_type: str = "short_answer") -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["뉴턴 제2법칙", "가속도"],
        type=problem_type,
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
    )


def _threshold_failure_kwargs(**overrides):
    data = {
        "case": load_live_problem_generation_cases_from_row(_base_case(expected_search_terms=[], expected_problem_terms=[])),
        "request": _high_rigor_threshold_request(),
        "generated_count": 1,
        "passed_count": 1,
        "returned_chunk_count": 1,
        "wrong_document_chunk_count": 0,
        "cited_chunk_count_avg": 1.0,
        "average_quality_score": 0.8,
        "reject_rate": 0.0,
        "total_ms": 1000.0,
        "expected_search_term_coverage": 1.0,
        "hit_at_k": None,
        "mrr_at_k": None,
        "precision_at_k": None,
        "source_span_coverage": None,
        "cited_hit_at_k": None,
        "cited_expected_chunk_recall": None,
        "cited_expected_chunk_precision": None,
        "cited_source_span_coverage": None,
        "generation_context_hit_at_k": None,
        "generation_context_expected_chunk_recall": None,
        "generation_context_source_span_coverage": None,
        "selected_kernel_atom_chunk_ids": [],
        "generation_context_selected_atom_recall": None,
        "expected_problem_term_coverage": 1.0,
        "high_rigor_operation_counts": {"condition_mutation": 1},
        "high_rigor_mc_choice_diagnostics_coverage": None,
        "short_answer_rubric_coverage": 1.0,
    }
    data.update(overrides)
    return data


def load_live_problem_generation_cases_from_row(row: dict):
    return LiveProblemGenerationEvalCase.model_validate(row)


def test_percentile_uses_linear_interpolation():
    assert _percentile([10, 20, 30, 40], 50) == 25
    assert _percentile([10, 20, 30, 40], 95) == pytest.approx(38.5)
    assert _percentile([None, 5], 95) == 5
    assert _percentile([], 50) is None


def test_bottleneck_classification_picks_largest_component():
    bottleneck = _classify_bottleneck(
        total_ms=100,
        search_ms=5,
        candidate_generation_total_ms=60,
        quality_filter_total_ms=20,
        db_write_ms=3,
        db_commit_ms=2,
        db_refresh_ms=1,
        artifact_publish_ms=4,
    )

    assert bottleneck["component"] == "generation"
    assert bottleneck["component_ms"] == 60
    assert bottleneck["component_ratio"] == pytest.approx(0.6)


def test_eval_database_url_defaults_to_isolated_sqlite_even_when_database_url_is_set(tmp_path, monkeypatch):
    database_url = "postgresql+psycopg://user:pass@localhost:5432/devdb"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL", raising=False)
    settings = Settings(DATABASE_URL=database_url)

    eval_database_url = _eval_database_url(output_dir=tmp_path, settings=settings)

    assert eval_database_url == f"sqlite+pysqlite:///{tmp_path / 'live_problem_generation_eval.sqlite'}"


def test_eval_database_url_uses_settings_database_url_when_explicitly_enabled(tmp_path, monkeypatch):
    database_url = "postgresql+psycopg://user:pass@localhost:5432/live_eval"
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL", "true")
    settings = Settings(DATABASE_URL=database_url)

    assert _eval_database_url(output_dir=tmp_path, settings=settings) == database_url


def test_eval_database_url_rejects_suspicious_database_without_override(tmp_path, monkeypatch):
    database_url = "postgresql+psycopg://user:pass@prod-db.example.com:5432/study_agent"
    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL", "true")
    monkeypatch.delenv("PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE", raising=False)
    settings = Settings(DATABASE_URL=database_url)

    with pytest.raises(ValueError, match="Unsafe live eval DATABASE_URL"):
        _eval_database_url(output_dir=tmp_path, settings=settings)

    monkeypatch.setenv("PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE", "true")

    assert _eval_database_url(output_dir=tmp_path, settings=settings) == database_url


def test_live_materials_readme_documents_database_safety():
    readme = Path("evals/live_materials/README.md").read_text(encoding="utf-8")

    assert "live_problem_generation_eval.sqlite" in readme
    assert "PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL" in readme
    assert "PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE" in readme
    assert "expected_chunk_ids" in readme
    assert "expected_pages" in readme
    assert "expected_source_spans" in readme
    assert "RAG `/search`" in readme
    assert "cse321_indexing_cases.jsonl" in readme
    assert "cse321_indexing_live" in readme
    assert "previously failed strict quality checks" in readme
    assert "Do not add `min_precision_at_k`" in readme
    assert "failure-analysis template" in readme


def test_threshold_fails_when_average_quality_score_is_missing_by_default():
    failures = _threshold_failures(**_threshold_failure_kwargs(average_quality_score=None))

    assert "average_quality_score is missing" in failures


def test_threshold_failure_categories_split_quality_performance_and_stability():
    categories = _threshold_failure_categories(
        [
            "total_ms 209322.8 > 180000.0",
            "reject_rate 0.667 > 0.6",
            "no generated problem cited any expected evidence chunk",
        ]
    )

    assert categories["performance"] == ["total_ms 209322.8 > 180000.0"]
    assert categories["stability"] == ["reject_rate 0.667 > 0.6"]
    assert categories["quality"] == ["no generated problem cited any expected evidence chunk"]


def test_threshold_allows_missing_quality_score_when_case_opt_in():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            allow_missing_quality_score=True,
        )
    )

    failures = _threshold_failures(**_threshold_failure_kwargs(case=case, average_quality_score=None))

    assert "average_quality_score is missing" not in failures
    assert failures == []


def test_threshold_fails_wrong_document_chunks():
    failures = _threshold_failures(**_threshold_failure_kwargs(wrong_document_chunk_count=1))

    assert "wrong_document_chunk_count 1 > 0" in failures


def test_threshold_fails_when_no_problems_pass_or_no_candidates_generated():
    failures = _threshold_failures(**_threshold_failure_kwargs(generated_count=0, passed_count=0))

    assert "no passed problems generated" in failures
    assert "no candidates generated" in failures


def test_threshold_fails_generic_only_high_rigor_operations():
    failures = _threshold_failures(
        **_threshold_failure_kwargs(high_rigor_operation_counts={"generic_application": 1})
    )

    assert "high-rigor problems lack specific thinking operations" in failures


def test_threshold_allows_specific_high_rigor_operation():
    failures = _threshold_failures(
        **_threshold_failure_kwargs(high_rigor_operation_counts={"condition_mutation": 1})
    )

    assert "high-rigor problems lack specific thinking operations" not in failures
    assert failures == []


def test_threshold_fails_high_rigor_multiple_choice_without_full_diagnostics():
    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            request=_high_rigor_threshold_request("multiple_choice"),
            short_answer_rubric_coverage=None,
            high_rigor_mc_choice_diagnostics_coverage=0.5,
        )
    )

    assert "high_rigor_mc_choice_diagnostics_coverage 0.500 < 1.0" in failures


def test_threshold_fails_short_answer_without_full_rubric_coverage():
    failures = _threshold_failures(**_threshold_failure_kwargs(short_answer_rubric_coverage=0.0))

    assert "short_answer_rubric_coverage 0.000 < 1.0" in failures


def test_threshold_fails_high_rigor_when_selected_kernel_atoms_are_dropped():
    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            selected_kernel_atom_chunk_ids=["formula_chunk"],
            generation_context_selected_atom_recall=0.0,
        )
    )

    assert "generation context dropped selected kernel atom chunks" in failures


def test_threshold_does_not_enforce_precision_for_partial_golden_labels():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
            min_precision_at_k=0.9,
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=0.1,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=1.0,
            cited_expected_chunk_precision=1.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=1.0,
        )
    )

    assert not any("precision_at_k" in failure for failure in failures)


def test_threshold_enforces_precision_for_exhaustive_golden_labels():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
            golden_label_mode="exhaustive",
            min_precision_at_k=0.9,
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=0.1,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=1.0,
            cited_expected_chunk_precision=1.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=1.0,
        )
    )

    assert "precision_at_k 0.100 < 0.9" in failures


def test_threshold_fails_high_rigor_when_no_expected_chunk_is_cited():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=1.0,
            cited_hit_at_k=0.0,
            cited_expected_chunk_recall=0.0,
            cited_expected_chunk_precision=0.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=1.0,
        )
    )

    assert "no generated problem cited any expected evidence chunk" in failures


def test_threshold_fails_when_generation_context_drops_expected_chunks():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=1.0,
            generation_context_hit_at_k=0.0,
            generation_context_expected_chunk_recall=0.0,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=1.0,
            cited_expected_chunk_precision=1.0,
        )
    )

    assert "generation context dropped all expected evidence chunks" in failures


def test_threshold_accepts_default_high_rigor_generation_context_recall_at_half():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force", "chunk_relation"],
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=1.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=0.5,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=1.0,
            cited_expected_chunk_precision=1.0,
        )
    )

    assert not any("generation_context_expected_chunk_recall" in failure for failure in failures)
    assert "generation context dropped all expected evidence chunks" not in failures


def test_threshold_accepts_default_high_rigor_cited_recall_at_half():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force", "chunk_relation"],
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            hit_at_k=1.0,
            mrr_at_k=1.0,
            precision_at_k=1.0,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=0.5,
            cited_expected_chunk_precision=1.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=1.0,
        )
    )

    assert not any("cited_expected_chunk_recall" in failure for failure in failures)
    assert "no generated problem cited any expected evidence chunk" not in failures


def _diagnostic_request() -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="physics_doc",
        concepts=["뉴턴 제2법칙", "가속도"],
        type="multiple_choice",
        count=1,
    )


def _mc_problem(**overrides):
    problem = {
        "id": "prob_mc",
        "type": "multiple_choice",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "item_model_id": "case_based_application",
        "quality_status": "passed",
        "professor_grade_score": {"final_score": 0.91},
        "source_chunk_ids": ["chunk_force"],
        "source_evidence_snapshot": [{"chunk_id": "chunk_force"}],
        "question": "조건이 바뀔 때 뉴턴 제2법칙에서 가속도 변화를 판단하시오.",
        "choices": [
            {"id": "A", "text": "가속도는 감소한다."},
            {"id": "B", "text": "가속도는 증가한다."},
            {"id": "C", "text": "질량과 무관하다."},
            {"id": "D", "text": "힘과 무관하다."},
        ],
        "answer": {"choice_id": "A", "text": "가속도는 감소한다."},
        "explanation": "F = ma에서 같은 힘이면 질량 증가 조건은 가속도 감소로 이어진다.",
        "choice_explanations": {
            "A": "자료의 관계를 조건에 적용했다.",
            "B": "질량과 가속도의 반비례 관계를 반대로 본 것이다.",
            "C": "질량 변수를 무시했다.",
            "D": "힘이 같다는 조건을 놓쳤다.",
        },
        "choice_diagnostics": [
            {"choice_id": "A", "is_correct": True, "mistake_type": "none"},
            {
                "choice_id": "B",
                "is_correct": False,
                "mistake_type": "logic_error",
                "why_plausible": "증가 방향만 보고 반비례 관계를 놓쳤다.",
                "repair_strategy": "F = ma를 a = F/m으로 바꿔 확인한다.",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "mistake_type": "missing_key_concept",
                "why_plausible": "힘만 보고 질량 조건을 생략했다.",
                "repair_strategy": "문제의 변화 조건을 표시한다.",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "mistake_type": "misread_question",
                "why_plausible": "같은 힘 조건을 반대로 읽었다.",
                "repair_strategy": "고정된 변수와 변하는 변수를 분리한다.",
            },
        ],
        "rubric": None,
        "item_design_brief": None,
    }
    problem.update(overrides)
    return SimpleNamespace(**problem)


def _sa_problem(**overrides):
    problem = {
        "id": "prob_sa",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "item_model_id": "case_based_application",
        "quality_status": "passed",
        "professor_grade_score": {"final_score": 0.9},
        "source_chunk_ids": ["chunk_force"],
        "source_evidence_snapshot": [{"chunk_id": "chunk_force"}],
        "question": "조건이 바뀔 때 뉴턴 제2법칙에서 가속도 변화를 설명하시오.",
        "choices": None,
        "answer": {"choice_id": None, "text": "가속도는 감소한다."},
        "explanation": "F = ma에서 같은 힘이면 질량 증가 조건은 가속도 감소로 이어진다.",
        "choice_explanations": None,
        "choice_diagnostics": None,
        "rubric": [{"criterion": "조건을 적용한다.", "points": 1}],
        "item_design_brief": None,
    }
    problem.update(overrides)
    return SimpleNamespace(**problem)


def test_runner_loads_jsonl_cases(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case())

    cases = load_live_problem_generation_cases(cases_path)

    assert len(cases) == 1
    assert cases[0].id == "physics_force_application"
    assert cases[0].request["type"] == "short_answer"


def test_cse321_indexing_case_file_loads_successfully():
    cases = load_live_problem_generation_cases(Path("evals/live_materials/cse321_indexing_cases.jsonl"))

    assert [case.id for case in cases] == [
        "cse321_indexing_btree_hard_short_answer",
        "cse321_indexing_ordered_index_hard_mcq",
        "cse321_indexing_control_medium_concept",
    ]
    assert all(case.document_id == "cse321_indexing_live" for case in cases)


def test_term_coverage_normalizes_b_plus_tree_variants():
    assert _term_coverage(["B+ tree"], "The slide title says B[+] -Tree Index.") == 1.0
    assert _term_coverage(["B[+] -Tree"], "The generated problem discusses a B+-Tree index.") == 1.0


def test_term_coverage_normalizes_disk_io_variants():
    assert _term_coverage(["disk I/O"], "The answer explains disk io cost.") == 1.0
    assert _term_coverage(["disk io"], "The chunk says every node access may need a disk I/O.") == 1.0


def test_term_coverage_uses_alias_dictionary():
    coverage = _term_coverage(
        ["fanout"],
        "The generated problem asks about branching factor changes.",
        aliases={"fanout": ["branching factor"]},
    )

    assert coverage == 1.0


def test_term_coverage_counts_unmatched_canonical_and_aliases_as_missing():
    coverage = _term_coverage(
        ["fanout", "disk I/O"],
        "The generated problem only mentions disk io.",
        aliases={"fanout": ["branching factor"]},
    )

    assert coverage == 0.5


def test_cse321_indexing_cases_include_term_aliases():
    cases = load_live_problem_generation_cases(Path("evals/live_materials/cse321_indexing_cases.jsonl"))
    btree_case = next(case for case in cases if case.id == "cse321_indexing_btree_hard_short_answer")

    assert "B[+] -Tree" in btree_case.expected_search_term_aliases
    assert "disk I/O" in btree_case.expected_search_term_aliases
    assert "B+" in btree_case.expected_problem_term_aliases


def test_cse321_indexing_cases_use_partial_golden_labels_without_precision_gate():
    cases = load_live_problem_generation_cases(Path("evals/live_materials/cse321_indexing_cases.jsonl"))

    assert all(case.golden_label_mode == "partial" for case in cases)
    assert all(case.min_precision_at_k is None for case in cases)


def test_cse321_high_rigor_mc_case_requires_diagnostics_coverage():
    cases = load_live_problem_generation_cases(Path("evals/live_materials/cse321_indexing_cases.jsonl"))
    case = next(case for case in cases if case.id == "cse321_indexing_ordered_index_hard_mcq")
    request = GenerateProblemRequest.model_validate(
        {
            "document_id": case.document_id,
            "concepts": case.concepts,
            **case.request,
        }
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            request=request,
            returned_chunk_count=2,
            average_quality_score=0.8,
            expected_search_term_coverage=1.0,
            hit_at_k=1.0,
            mrr_at_k=0.5,
            source_span_coverage=1.0,
            cited_hit_at_k=1.0,
            cited_expected_chunk_recall=1.0,
            generation_context_hit_at_k=1.0,
            generation_context_expected_chunk_recall=1.0,
            expected_problem_term_coverage=1.0,
            high_rigor_operation_counts={"evidence_interpretation": 1},
            high_rigor_mc_choice_diagnostics_coverage=0.0,
            short_answer_rubric_coverage=None,
        )
    )

    assert "high_rigor_mc_choice_diagnostics_coverage 0.000 < 1.0" in failures


def test_cse321_indexing_case_file_can_run_with_fake_live_benchmark(tmp_path):
    output_dir = tmp_path / "reports"

    report = run_live_problem_generation_eval(
        cases_path=Path("evals/live_materials/cse321_indexing_cases.jsonl"),
        output_dir=output_dir,
        settings=_settings(),
        search_service=CSE321IndexingSearchService(),
        problem_agent=CSE321IndexingProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert report.case_count == 3
    assert [case.case_id for case in report.cases] == [
        "cse321_indexing_btree_hard_short_answer",
        "cse321_indexing_ordered_index_hard_mcq",
        "cse321_indexing_control_medium_concept",
    ]
    assert (output_dir / REPORT_JSON_NAME).exists()
    assert (output_dir / REPORT_MARKDOWN_NAME).exists()


def test_runner_writes_reports_and_calculates_metrics(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    publisher = FakePublisher()
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=publisher,
    )

    result = report.cases[0]
    assert (output_dir / REPORT_JSON_NAME).exists()
    assert (output_dir / REPORT_JSONL_NAME).exists()
    assert (output_dir / REPORT_MARKDOWN_NAME).exists()
    assert (output_dir / REPORT_HUMAN_REVIEW_CSV_NAME).exists()
    assert result.generated_count == 1
    assert report.search_query_mode == "compact"
    assert report.repeat_count == 1
    assert report.logical_case_count == 1
    assert report.total_run_count == 1
    assert result.repeat_index == 0
    assert result.repeated_case_group_id == "physics_force_application"
    assert report.report_schema_version == LIVE_EVAL_REPORT_SCHEMA_VERSION
    assert report.cases_sha256 == _file_sha256(cases_path)
    assert report.settings_snapshot["problem_agent_search_query_mode"] == "compact"
    assert "OPENAI_API_KEY" not in report.settings_snapshot
    assert "GEMINI_API_KEY" not in report.settings_snapshot
    assert result.search_query_mode == "compact"
    assert result.passed_count == 1
    assert result.rejected_count == 0
    assert result.reject_rate == 0
    assert result.pass_rate == 1
    assert result.expected_search_term_coverage == 1
    assert result.expected_problem_term_coverage == 1
    assert result.returned_chunk_count == 2
    assert result.unique_returned_chunk_count == 2
    assert result.cited_chunk_count_avg == 1
    assert result.search_query is not None
    assert result.search_ms is not None
    assert result.service_internal_search_ms is not None
    assert result.effective_search_ms == result.search_ms
    assert result.baseline_search_ms is None
    assert result.enhanced_search_ms is None
    assert result.bottleneck_component is not None
    assert result.bottleneck_component_ms is not None
    assert result.search_latency_note == "search_ms measured inside ProblemService"
    assert result.db_commit_ms is not None
    assert result.artifact_publish_success_count == 1
    assert publisher.published == result.generated_problem_ids
    assert report.passed_count == 1
    assert result.problem_quality_diagnostics
    assert result.problem_quality_diagnostics[0].professor_score_band in {"excellent", "good", "needs_review", "weak"}
    assert result.professor_score_band_counts
    assert report.professor_score_band_counts
    assert result.high_rigor_operation_counts
    assert report.high_rigor_operation_counts
    assert result.high_quality_problem_count == 1
    assert report.high_quality_problem_count == 1
    assert result.commercial_quality_band_counts == {"usable_with_review": 1}
    assert report.commercial_score_band_counts == {"usable_with_review": 1}
    assert report.p50_total_ms is not None
    assert report.p95_total_ms is not None
    assert report.bottleneck_counts
    assert report.human_review_export_mode == "full"
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Latency Percentiles" in summary
    assert "## Bottleneck Distribution" in summary
    assert "human_review_export_mode: full" in summary
    review_rows = list(csv.DictReader((output_dir / REPORT_HUMAN_REVIEW_CSV_NAME).open(encoding="utf-8")))
    assert len(review_rows) == 1
    assert review_rows[0]["case_id"] == "physics_force_application"
    assert "같은 힘이 작용할 때" in review_rows[0]["question"]
    assert "가속도는 감소한다" in review_rows[0]["answer_json"]
    assert "F = ma" in review_rows[0]["explanation"]
    assert review_rows[0]["professor_score_band"]
    assert "structural_score" in review_rows[0]
    assert "pedagogical_score" in review_rows[0]
    assert "grounding_score" in review_rows[0]
    assert review_rows[0]["reviewer_notes"] == ""
    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["report_schema_version"] == LIVE_EVAL_REPORT_SCHEMA_VERSION
    assert payload["repeat_count"] == 1
    assert payload["human_review_export_mode"] == "full"
    assert payload["logical_case_count"] == 1
    assert payload["total_run_count"] == 1
    assert payload["case_stability_summary"]["physics_force_application"]["run_count"] == 1
    assert payload["cases_sha256"] == _file_sha256(cases_path)
    assert payload["settings_snapshot"]["problem_model"]
    assert all("KEY" not in key.upper() for key in payload["settings_snapshot"])
    assert payload["search_query_mode"] == "compact"
    assert payload["professor_score_band_counts"]
    assert payload["cases"][0]["search_query_mode"] == "compact"
    assert "human_review_rows" not in payload["cases"][0]


def test_rejected_candidate_writer_redacts_sensitive_fields_by_default(tmp_path):
    writer = RejectedCandidateArtifactWriter(tmp_path)

    writer.write_rejected_candidate(
        case_id="case_redacted",
        repeat_index=0,
        attempt_index=0,
        candidate_index=0,
        candidate={
            "document_id": "doc",
            "type": "short_answer",
            "question": "What is grounded?",
            "answer": {"text": "secret answer"},
            "explanation": "secret explanation",
            "rubric": [{"criterion": "secret rubric", "points": 1}],
            "source_chunk_ids": ["chunk_1"],
        },
        kernel_type="compute_from_given",
        problem_style="calculation_practice",
        selected_atom_ids=["atom_1"],
        selected_atom_chunk_ids=["chunk_1"],
        quality_errors=["formula not linked"],
        rejection_categories={"missing_evidence_binding": 1},
        usage={"model": "gpt-5.4-mini", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )

    record = json.loads((tmp_path / REJECTED_CANDIDATES_JSONL_NAME).read_text(encoding="utf-8"))
    assert record["question_preview"] == "What is grounded?"
    assert record["answer_preview"] == "[redacted]"
    assert record["explanation_preview"] == "[redacted]"
    assert record["rubric_preview"] == "[redacted]"
    assert record["source_chunk_ids"] == ["chunk_1"]
    assert record["selected_atom_ids"] == ["atom_1"]


def test_rejected_candidate_writer_full_mode_includes_sensitive_fields(tmp_path):
    writer = RejectedCandidateArtifactWriter(tmp_path, export_mode="full")

    writer.write_rejected_candidate(
        case_id="case_full",
        repeat_index=0,
        attempt_index=0,
        candidate_index=0,
        candidate={
            "document_id": "doc",
            "type": "short_answer",
            "question": "Q",
            "answer": {"text": "visible answer"},
            "explanation": "visible explanation",
            "rubric": [{"criterion": "visible rubric", "points": 1}],
        },
        kernel_type=None,
        problem_style="concept_check",
        selected_atom_ids=[],
        selected_atom_chunk_ids=[],
    )

    record = json.loads((tmp_path / REJECTED_CANDIDATES_JSONL_NAME).read_text(encoding="utf-8"))
    assert "visible answer" in record["answer_preview"]
    assert "visible explanation" in record["explanation_preview"]
    assert "visible rubric" in record["rubric_preview"]


def test_rejected_candidate_writer_noops_without_output_dir():
    writer = RejectedCandidateArtifactWriter(None)

    writer.write_rejected_candidate(
        case_id="case_noop",
        repeat_index=0,
        attempt_index=0,
        candidate_index=0,
        candidate={"question": "Q", "answer": {"text": "A"}},
        kernel_type=None,
        problem_style="concept_check",
        selected_atom_ids=[],
        selected_atom_chunk_ids=[],
    )
    writer.write_usage(
        case_id="case_noop",
        repeat_index=0,
        attempt_index=0,
        usage={"model": "gpt-5.4-mini", "input_tokens": 1},
        generation_mode="llm",
        failure_status="generation_failed",
    )


def test_live_eval_writes_redacted_rejected_candidate_for_quality_rejection(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=RejectingProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert report.failed_execution_count == 1
    records = [
        json.loads(line)
        for line in (output_dir / REJECTED_CANDIDATES_JSONL_NAME).read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["case_id"] == "physics_force_application"
    assert records[0]["quality_errors"]
    assert records[0]["answer_preview"] == "[redacted]"


def test_live_eval_writes_failed_attempt_usage_and_invalid_payload_artifact(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=SchemaFailureProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert report.failed_execution_count == 1
    assert result.execution_status == "generation_failed"
    assert result.total_llm_input_tokens == 123
    assert result.total_llm_output_tokens == 45
    usage_record = json.loads((output_dir / EVAL_USAGE_LEDGER_JSONL_NAME).read_text(encoding="utf-8"))
    assert usage_record["case_id"] == "physics_force_application"
    assert usage_record["model"] == "gpt-5.4-mini"
    assert usage_record["input_tokens"] == 123
    assert usage_record["failure_status"] == "generation_failed"

    rejected_record = json.loads((output_dir / REJECTED_CANDIDATES_JSONL_NAME).read_text(encoding="utf-8"))
    assert rejected_record["case_id"] == "physics_force_application"
    assert rejected_record["answer_preview"] == "[redacted]"
    assert rejected_record["explanation_preview"] == "[redacted]"
    assert rejected_record["rubric_preview"] == "[redacted]"


def test_human_review_csv_redacted_mode_hides_solution_fields(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        human_review_export_mode="redacted",
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert report.human_review_export_mode == "redacted"
    review_rows = list(csv.DictReader((output_dir / REPORT_HUMAN_REVIEW_CSV_NAME).open(encoding="utf-8")))
    assert len(review_rows) == 1
    assert "같은 힘이 작용할 때" in review_rows[0]["question"]
    assert review_rows[0]["choices_json"] == "[]"
    assert review_rows[0]["source_chunk_ids_json"]
    assert review_rows[0]["answer_json"] == "[redacted]"
    assert review_rows[0]["explanation"] == "[redacted]"
    assert review_rows[0]["rubric_json"] == "[redacted]"
    assert review_rows[0]["source_evidence_snapshot_json"] == "[redacted]"
    assert review_rows[0]["reviewer_notes"] == ""

    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["human_review_export_mode"] == "redacted"
    assert "human_review_rows" not in payload["cases"][0]
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "human_review_export_mode: redacted" in summary


def test_load_human_review_csv_parses_blank_scores_as_none(tmp_path):
    path = tmp_path / "review.csv"
    _write_human_review_csv(
        path,
        {
            "case_id": "case_1",
            "problem_id": "prob_1",
            "reviewer_problem_quality_score": "",
            "reviewer_source_grounding_score": "",
            "reviewer_difficulty_fit_score": "",
            "reviewer_notes": "",
        },
    )

    records = load_human_review_csv(path)

    assert len(records) == 1
    assert records[0].reviewer_problem_quality_score is None
    assert records[0].reviewer_source_grounding_score is None
    assert records[0].reviewer_difficulty_fit_score is None
    assert records[0].reviewer_notes == ""


def test_load_human_review_csv_normalizes_five_point_scores_and_preserves_unit_scores(tmp_path):
    path = tmp_path / "review.csv"
    _write_human_review_csv(
        path,
        {
            "case_id": "case_1",
            "problem_id": "prob_1",
            "reviewer_problem_quality_score": "5",
            "reviewer_source_grounding_score": "3",
            "reviewer_difficulty_fit_score": "0.8",
            "reviewer_notes": "확인 필요",
        },
    )

    record = load_human_review_csv(path)[0]

    assert record.reviewer_problem_quality_score == 1
    assert record.reviewer_source_grounding_score == 0.6
    assert record.reviewer_difficulty_fit_score == 0.8
    assert record.reviewer_notes == "확인 필요"


def test_summarize_human_review_calculates_averages_and_low_counts():
    records = [
        HumanReviewRecord(
            case_id="case_1",
            problem_id="prob_1",
            reviewer_problem_quality_score=1.0,
            reviewer_source_grounding_score=0.8,
            reviewer_difficulty_fit_score=0.7,
            reviewer_notes="좋음",
        ),
        HumanReviewRecord(
            case_id="case_1",
            problem_id="prob_2",
            reviewer_problem_quality_score=0.4,
            reviewer_source_grounding_score=0.5,
            reviewer_difficulty_fit_score=0.9,
            reviewer_notes="정답 오류 확인",
        ),
    ]

    summary = summarize_human_review(records)

    assert summary.reviewed_problem_count == 2
    assert summary.average_problem_quality_score == 0.7
    assert summary.average_source_grounding_score == 0.65
    assert summary.average_difficulty_fit_score == 0.8
    assert summary.low_quality_review_count == 1
    assert summary.low_grounding_review_count == 1
    assert summary.low_difficulty_fit_count == 0
    assert summary.reviewer_notes_by_problem == {
        "prob_1": ["좋음"],
        "prob_2": ["정답 오류 확인"],
    }


def test_human_review_disagreement_detects_high_professor_low_human_score(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())
    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )
    diagnostic = report.cases[0].problem_quality_diagnostics[0]
    diagnostic.professor_score_band = "excellent"
    diagnostic.professor_grade_final_score = 0.95
    record = HumanReviewRecord(
        case_id=report.cases[0].case_id,
        problem_id=diagnostic.problem_id,
        reviewer_problem_quality_score=0.4,
        reviewer_source_grounding_score=0.9,
        reviewer_difficulty_fit_score=0.8,
        reviewer_notes="사람 기준으로 문제 품질이 낮음",
    )

    summary = summarize_human_review([record], report=report)

    assert len(summary.disagreements) == 1
    assert summary.disagreements[0]["problem_id"] == diagnostic.problem_id
    assert summary.disagreements[0]["professor_score_band"] == "excellent"


def test_write_human_review_summary_writes_json_and_markdown(tmp_path):
    summary = summarize_human_review(
        [
            HumanReviewRecord(
                case_id="case_1",
                problem_id="prob_1",
                reviewer_problem_quality_score=0.9,
                reviewer_source_grounding_score=0.85,
                reviewer_difficulty_fit_score=0.75,
                reviewer_notes="사용 가능",
            )
        ]
    )

    write_human_review_summary(summary, tmp_path)

    payload = json.loads((tmp_path / REPORT_HUMAN_REVIEW_SUMMARY_JSON_NAME).read_text(encoding="utf-8"))
    markdown = (tmp_path / REPORT_HUMAN_REVIEW_SUMMARY_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert payload["reviewed_problem_count"] == 1
    assert payload["average_problem_quality_score"] == 0.9
    assert "Human Review Summary" in markdown
    assert "average_source_grounding_score" in markdown


def _commercial_diagnostic(**overrides):
    payload = {
        "problem_id": "prob_1",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "quality_status": "passed",
        "professor_grade_final_score": 0.92,
        "professor_score_band": "excellent",
        "source_chunk_count": 1,
        "has_source_evidence_snapshot": True,
        "has_explanation": True,
        "has_answer": True,
        "high_rigor_operation_detected": True,
        "high_rigor_operation_label": "calculation_reasoning",
        "source_term_coverage": 1.0,
        "expected_problem_term_coverage": 1.0,
        "warning_flags": [],
        "quality_risk_level": "low",
    }
    payload.update(overrides)
    return LiveProblemQualityDiagnostic(**payload)


def test_commercial_quality_score_caps_needs_review_professor_excellent():
    diagnostic = _commercial_diagnostic(quality_status="needs_review")

    score, band = _commercial_quality_score_for_diagnostic(
        diagnostic=diagnostic,
        execution_status="completed",
    )

    assert score == 0.74
    assert band == "usable_with_review"


def test_commercial_quality_score_caps_answer_verifier_and_missing_evidence():
    diagnostic = _commercial_diagnostic(answer_verification_action="reject")

    score, band = _commercial_quality_score_for_diagnostic(
        diagnostic=diagnostic,
        execution_status="completed",
        cited_evidence_missing=True,
    )

    assert score == 0.49
    assert band == "reject"


def test_commercial_quality_score_allows_release_ready_when_grounded():
    diagnostic = _commercial_diagnostic()

    score, band = _commercial_quality_score_for_diagnostic(
        diagnostic=diagnostic,
        execution_status="completed",
    )

    assert score == 0.92
    assert band == "release_ready"


def test_problem_quality_diagnostic_includes_evidence_obligation_fields():
    problem = SimpleNamespace(
        id="problem_1",
        type="short_answer",
        difficulty="hard",
        bloom_level="analyze",
        item_model_id=None,
        quality_status="passed",
        professor_grade_score={"final_score": 0.9, "source_grounding": 0.9},
        source_chunk_ids=["chunk_1"],
        source_evidence_snapshot=[{"chunk_id": "chunk_1"}],
        explanation="Net amount = gross amount - discount.",
        answer={"choice_id": None, "text": "80"},
        choices=None,
        choice_explanations=None,
        choice_diagnostics=None,
        rubric=[{"criterion": "Uses formula", "points": 1}],
        question="Compute net amount.",
        concepts=["net amount"],
        item_design_brief={
            "evidence_links": [
                {
                    "link_id": "link_1",
                    "atom_id": "atom_formula",
                    "source_chunk_id": "chunk_1",
                    "evidence_role": "formula",
                    "evidence_quote": "Net amount = gross amount - discount.",
                    "used_in": ["answer", "explanation"],
                    "supported_claim": "Answer uses formula.",
                }
            ],
            "evidence_obligation_report": {
                "required_link_count": 3,
                "satisfied_link_count": 2,
                "missing_roles": ["formula"],
                "answer_supported": True,
                "explanation_supported": True,
                "distractors_supported": True,
                "rubric_supported": False,
                "source_formula_or_rule_cited": False,
                "generated_scenario_values_declared": True,
                "issues": ["kernel evidence rule/formula/procedure is not cited"],
            },
        },
    )

    diagnostic = _problem_quality_diagnostic(
        problem=problem,
        request=_high_rigor_threshold_request(problem_type="short_answer"),
        source_terms=["net amount"],
        expected_problem_terms=["net amount"],
    )

    assert diagnostic.evidence_link_count == 1
    assert diagnostic.evidence_obligation_satisfaction == pytest.approx(2 / 3)
    assert diagnostic.answer_supported is True
    assert diagnostic.explanation_supported is True
    assert diagnostic.rubric_supported is False
    assert diagnostic.source_formula_or_rule_cited is False
    assert diagnostic.missing_evidence_roles == ["formula"]
    assert diagnostic.evidence_obligation_issues == ["kernel evidence rule/formula/procedure is not cited"]


def test_answer_verifier_passes_simple_correct_arithmetic():
    verifier = ProblemAnswerVerifier(settings=_settings())
    problem = {
        "type": "short_answer",
        "question": "2 + 3의 값을 계산하시오.",
        "answer": {"choice_id": None, "text": "5"},
        "explanation": "2 + 3 = 5이다.",
        "rubric": [{"criterion": "계산", "points": 1, "expected_evidence": ["5"]}],
        "source_chunk_ids": ["chunk_force"],
    }

    report = verifier.verify(problem=problem, chunks=FakeSearchService().chunks)

    assert report.recommended_action == "pass"
    assert report.answer_correctness_score == 1
    assert report.issues == []


def test_answer_verifier_flags_wrong_arithmetic():
    verifier = ProblemAnswerVerifier(settings=_settings())
    problem = {
        "type": "short_answer",
        "question": "2 + 3의 값을 계산하시오.",
        "answer": {"choice_id": None, "text": "6"},
        "explanation": "2 + 3 = 6이다.",
        "rubric": [{"criterion": "계산", "points": 1, "expected_evidence": ["5"]}],
        "source_chunk_ids": ["chunk_force"],
    }

    report = verifier.verify(problem=problem, chunks=FakeSearchService().chunks)

    assert report.recommended_action == "reject"
    assert any("wrong arithmetic" in issue for issue in report.issues)


def test_answer_verifier_flags_duplicate_multiple_choice_correct_option():
    verifier = ProblemAnswerVerifier(settings=_settings())
    problem = {
        "type": "multiple_choice",
        "question": "뉴턴의 제2법칙 설명으로 적절한 것은?",
        "choices": [
            {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "B", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "C", "text": "힘은 질량과 무관하다."},
            {"id": "D", "text": "가속도는 항상 0이다."},
        ],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "A는 힘, 질량, 가속도의 관계를 설명한다.",
        "choice_explanations": {"A": "맞다.", "B": "중복.", "C": "틀림.", "D": "틀림."},
        "source_chunk_ids": ["chunk_force"],
    }

    report = verifier.verify(problem=problem, chunks=FakeSearchService().chunks)

    assert report.recommended_action == "needs_review"
    assert any("semantically equivalent" in issue for issue in report.issues)


def test_live_eval_includes_fake_answer_verifier_result(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    verifier = FakeAnswerVerifier()
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        answer_verification_enabled=True,
        answer_verifier=verifier,
    )

    result = report.cases[0]
    diagnostic = result.problem_quality_diagnostics[0]
    assert verifier.calls
    assert diagnostic.answer_verification_score == 0.45
    assert diagnostic.answer_verification_action == "reject"
    assert diagnostic.answer_verification_issues == ["fake verifier found answer correctness risk"]
    assert result.answer_verification_action_counts == {"reject": 1}
    assert result.answer_correctness_issue_count == 1
    assert report.answer_verification_action_counts == {"reject": 1}
    assert report.answer_correctness_issue_count == 1
    assert result.threshold_passed is False
    assert any("answer verification rejected" in failure for failure in result.threshold_failures)


def test_repeat_count_runs_case_multiple_times_and_summarizes_stability(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            max_repeat_duplicate_similarity=1.0,
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        repeat_count=3,
    )

    assert report.repeat_count == 3
    assert report.logical_case_count == 1
    assert report.total_run_count == 3
    assert report.case_count == 3
    assert [case.repeat_index for case in report.cases] == [0, 1, 2]
    assert {case.repeated_case_group_id for case in report.cases} == {"physics_force_application"}
    summary = report.case_stability_summary["physics_force_application"]
    assert summary["run_count"] == 3
    assert summary["pass_rate"] == 1
    assert summary["average_reject_rate"] == 0
    assert summary["average_retry_count"] == 0
    assert summary["average_quality_score"] is not None
    assert summary["quality_score_stddev"] == 0
    assert summary["duplicate_question_similarity_max"] == 1


def test_repeat_stability_summarizes_repeated_generation_failure(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=AlwaysFailsProblemAgent(),
        artifact_publisher=FakePublisher(),
        repeat_count=2,
    )

    summary = report.case_stability_summary["physics_force_application"]
    assert report.case_count == 2
    assert report.failed_execution_count == 2
    assert report.cases[0].returned_chunk_count == 2
    assert report.cases[0].expected_search_term_coverage == 1.0
    assert summary["run_count"] == 2
    assert summary["pass_rate"] == 0
    assert any("case execution failed" in message for message in summary["failure_messages"])
    assert summary["generated_operation_counts"] == {}


def test_repeat_duplicate_question_similarity_threshold_marks_runs_failed(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case(max_repeat_duplicate_similarity=0.80))

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        repeat_count=2,
    )

    summary = report.case_stability_summary["physics_force_application"]
    assert summary["duplicate_question_similarity_max"] == 1
    assert any("duplicate_question_similarity_max" in failure for failure in summary["threshold_failures"])
    assert all(case.threshold_passed is False for case in report.cases)
    assert all(any("repeat stability" in failure for failure in case.threshold_failures) for case in report.cases)


def test_runner_aggregates_generation_bottleneck_counts(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(id="physics_force_application_1"),
        _base_case(id="physics_force_application_2"),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=SlowGenerationProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert [case.bottleneck_component for case in report.cases] == ["generation", "generation"]
    assert report.bottleneck_counts == {"generation": 2}
    assert report.p50_candidate_generation_total_ms is not None
    assert report.p95_candidate_generation_total_ms is not None


def test_runner_reports_actual_generation_model_tokens_and_cost(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(
            PROBLEM_MODEL="gpt-5.4-mini",
            PROBLEM_QUALITY_MODEL="gpt-5.5",
            OPENAI_API_KEY="sk-test-secret",
            LLM_PREMIUM_INPUT_PRICE_KRW_PER_1M_TOKENS=1000.0,
            LLM_PREMIUM_OUTPUT_PRICE_KRW_PER_1M_TOKENS=2000.0,
        ),
        search_service=FakeSearchService(),
        problem_agent=UsageTrackingProblemAgent(model="gpt-5.5", input_tokens=1200, output_tokens=300),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.actual_generation_models == ["gpt-5.5"]
    assert result.total_llm_input_tokens == 1200
    assert result.total_llm_output_tokens == 300
    assert result.total_llm_tokens == 1500
    assert result.llm_call_count == 1
    assert result.generation_attempts[0].model == "gpt-5.5"
    assert result.generation_attempts[0].prompt_char_count == 4321
    assert result.generation_attempts[0].context_chunk_count == result.generation_context_chunk_count
    assert result.generation_attempts[0].candidate_count_requested == 1
    assert result.generation_attempts[0].valid_candidates_produced == 1
    assert result.generation_attempts[0].rejected_candidates_produced == 0
    assert result.total_estimated_cost_krw is not None
    assert report.total_llm_input_tokens == 1200
    assert report.total_llm_output_tokens == 300
    assert report.total_llm_tokens == 1500
    assert report.cost_profile == "balanced"
    assert result.cost_profile == "balanced"
    assert report.generation_model == "gpt-5.4-mini"
    assert report.generation_model_counts == {"gpt-5.5": 1}
    assert report.token_usage_by_model["gpt-5.5"]["total_tokens"] == 1500
    assert report.cost_by_model["gpt-5.5"] == pytest.approx(result.total_estimated_cost_krw)
    assert report.cost_by_case[result.case_id] == pytest.approx(result.total_estimated_cost_krw)
    assert report.highest_cost_cases[0]["case_id"] == result.case_id
    assert report.generation_model_mismatch_warning == (
        "configured generation model differs from actual LLM model used; "
        "high-rigor routing may be using problem_quality_model"
    )

    report_payload = (output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8")
    markdown = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "Token and Cost Summary" in markdown
    assert "gpt-5.5" in markdown
    assert "sk-test-secret" not in report_payload
    assert "sk-test-secret" not in markdown


def test_live_report_includes_full_cost_profile_warning(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_AGENT_COST_PROFILE="full"),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert report.cost_profile == "full"
    assert report.cases[0].cost_profile == "full"
    assert report.cost_profile_warning is not None
    markdown = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "- cost_profile: full" in markdown
    assert "full cost profile is enabled" in markdown


def test_live_eval_report_freshness_passes_for_fresh_fake_report(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert validate_live_eval_report_freshness(report, cases_path) == []


def test_live_eval_report_freshness_warns_for_stale_schema(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())
    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )
    stale_report = report.model_copy(update={"report_schema_version": "live_problem_generation_eval.v1"})

    warnings = validate_live_eval_report_freshness(stale_report, cases_path)

    assert any("schema version" in warning for warning in warnings)


def test_live_eval_report_freshness_warns_when_cases_file_changed(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())
    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )
    time.sleep(0.01)
    _write_cases(cases_path, _base_case(id="changed_case"))

    warnings = validate_live_eval_report_freshness(report, cases_path)

    assert "cases_sha256 does not match current cases file" in warnings
    assert "report generated_at is older than cases file modified time" in warnings


def test_live_eval_report_freshness_warns_for_zero_cases(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, _base_case())
    report = LiveProblemGenerationEvalReport(
        generated_at=datetime.now(timezone.utc),
        cases_path=str(cases_path),
        output_dir=str(tmp_path),
        search_query_mode="compact",
        case_count=0,
        passed_count=0,
        failed_count=0,
        cases=[],
        cases_sha256=_file_sha256(cases_path),
    )

    warnings = validate_live_eval_report_freshness(report, cases_path)

    assert "report has zero cases" in warnings


def test_live_eval_reports_raw_retrieved_chunk_count_when_generation_context_is_packed(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_PACKING_ENABLED=True,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=3,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=2,
        ),
        search_service=ManyChunkSearchService(count=14),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.returned_chunk_count == 14
    assert result.unique_returned_chunk_count == 14


def test_runner_records_generation_failure_and_continues_to_next_case(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(id="failing_case"),
        _base_case(id="successful_case"),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FailsFirstProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    failed_result = report.cases[0]
    successful_result = report.cases[1]
    assert report.case_count == 2
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert report.failed_execution_count == 1
    assert report.generation_failed_count == 1
    assert report.search_failed_count == 0
    assert report.db_failed_count == 0
    assert failed_result.execution_status == "generation_failed"
    assert failed_result.exception_stage == "generation"
    assert failed_result.failure_stage == "generation"
    assert failed_result.exception_type == "RuntimeError"
    assert failed_result.threshold_passed is False
    assert failed_result.generated_problem_ids == []
    assert failed_result.returned_chunk_count > 0
    assert failed_result.failure_rejection_category_counts == {"missing_reasoning_steps": 2}
    assert failed_result.failure_top_rejection_categories == ["missing_reasoning_steps"]
    assert any("case execution failed" in failure for failure in failed_result.threshold_failures)
    assert successful_result.execution_status == "completed"
    assert successful_result.threshold_passed is True

    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["failed_execution_count"] == 1
    assert payload["generation_failed_count"] == 1
    assert payload["cases"][0]["execution_status"] == "generation_failed"
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Failed Cases" in summary
    assert "failing_case" in summary
    assert "top_rejection_categories" in summary
    assert "missing_reasoning_steps" in summary


def test_failed_case_result_preserves_kernel_planning_trace():
    case = load_live_problem_generation_cases_from_row(_base_case())
    result = _failed_case_result(
        case=case,
        request=_high_rigor_threshold_request(),
        exc=ValueError("kernel planning failed: insufficient_source_structure"),
        elapsed_ms=25.0,
        trace={
            "failure_stage": "generation",
            "returned_chunk_count": 3,
            "raw_content_atom_count": 2,
            "raw_content_atom_type_counts": {"definition": 2},
            "problem_kernel_type": "recall_define",
            "kernel_planning_failure_reason": "insufficient_source_structure",
        },
    )

    assert result.returned_chunk_count == 3
    assert result.raw_content_atom_count == 2
    assert result.raw_content_atom_type_counts == {"definition": 2}
    assert result.problem_kernel_type == "recall_define"
    assert result.kernel_planning_failure_reason == "insufficient_source_structure"


def test_failed_case_result_preserves_raw_returned_count_separate_from_context():
    case = load_live_problem_generation_cases_from_row(_base_case())
    chunks = [
        RetrievedChunk(chunk_id=f"chunk_{index}", document_id="physics_doc", content="source text")
        for index in range(14)
    ]
    result = _failed_case_result(
        case=case,
        request=_high_rigor_threshold_request(),
        exc=RuntimeError("generation failed"),
        elapsed_ms=25.0,
        trace={
            "chunks": chunks,
            "returned_chunk_count": 14,
            "generation_context_chunk_ids": ["chunk_0", "chunk_2"],
            "selected_kernel_atom_chunk_ids": ["chunk_2", "chunk_9"],
            "generation_context_selected_atom_recall": 0.5,
            "kernel_atom_dropped_count": 1,
        },
    )

    assert result.returned_chunk_count == 14
    assert result.generation_context_chunk_count == 2
    assert result.selected_kernel_atom_chunk_ids == ["chunk_2", "chunk_9"]
    assert result.kernel_atom_dropped_count == 1


def test_failed_case_result_prefers_trace_rejection_categories():
    case = load_live_problem_generation_cases_from_row(_base_case())
    result = _failed_case_result(
        case=case,
        request=_high_rigor_threshold_request(),
        exc=ValueError("quality validation failed"),
        elapsed_ms=25.0,
        trace={
            "rejection_category_counts": {"weak_distractor_diagnostics": 3},
            "top_rejection_categories": ["weak_distractor_diagnostics"],
        },
    )

    assert result.failure_rejection_category_counts == {"weak_distractor_diagnostics": 3}
    assert result.failure_top_rejection_categories == ["weak_distractor_diagnostics"]


def test_runner_fail_on_threshold_raises_after_writing_failure_reports(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case(id="failing_case"))

    with pytest.raises(AssertionError, match="thresholds failed"):
        run_live_problem_generation_eval(
            cases_path=cases_path,
            output_dir=output_dir,
            settings=_settings(),
            fail_on_threshold=True,
            search_service=FakeSearchService(),
            problem_agent=FailsFirstProblemAgent(),
            artifact_publisher=FakePublisher(),
        )

    assert (output_dir / REPORT_JSON_NAME).exists()
    assert (output_dir / REPORT_JSONL_NAME).exists()
    assert (output_dir / REPORT_MARKDOWN_NAME).exists()
    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["case_count"] == 1
    assert payload["failed_execution_count"] == 1
    assert payload["cases"][0]["execution_status"] == "generation_failed"


def test_runner_includes_fake_llm_judge_results(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    fake_judge = FakeLLMJudge()
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        llm_judge_enabled=True,
        llm_judge=fake_judge,
        judge_model="fake-judge-model",
    )

    result = report.cases[0]
    assert len(fake_judge.calls) == 1
    assert fake_judge.calls[0]["judge_model"] == "fake-judge-model"
    assert fake_judge.calls[0]["request"].document_id == "physics_doc"
    assert report.llm_judge_enabled is True
    assert report.average_llm_judge_overall_score == pytest.approx(0.82)
    assert report.llm_judge_action_counts == {"pass": 1}
    assert result.average_llm_judge_overall_score == pytest.approx(0.82)
    assert result.llm_judge_action_counts == {"pass": 1}
    assert result.llm_judge_results[0].recommended_action == "pass"
    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["llm_judge_enabled"] is True
    assert payload["average_llm_judge_overall_score"] == pytest.approx(0.82)
    assert payload["llm_judge_action_counts"] == {"pass": 1}
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## LLM Judge" in summary


def test_llm_judge_same_model_warning(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_MODEL="gpt-5.4-mini", PROBLEM_QUALITY_MODEL="gpt-5.4-mini"),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        llm_judge_enabled=True,
        llm_judge=FakeLLMJudge(),
    )

    assert report.generation_model == "gpt-5.4-mini"
    assert report.judge_model == "gpt-5.4-mini"
    assert report.judge_same_model_warning is True
    assert report.judge_same_family_warning is True
    assert "same model as generation" in " ".join(report.judge_independence_notes)
    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["judge_same_model_warning"] is True


def test_llm_judge_same_family_warning(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_MODEL="gpt-5.4-mini", PROBLEM_QUALITY_MODEL="gpt-5.5"),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        llm_judge_enabled=True,
        llm_judge=FakeLLMJudge(),
    )

    assert report.judge_same_model_warning is False
    assert report.judge_same_family_warning is True
    assert "same model family" in " ".join(report.judge_independence_notes)


def test_llm_judge_different_family_has_no_same_family_warning(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_MODEL="gpt-5.4-mini", PROBLEM_QUALITY_MODEL="gemini-2.5-pro"),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        llm_judge_enabled=True,
        llm_judge=FakeLLMJudge(),
    )

    assert report.judge_model == "gemini-2.5-pro"
    assert report.judge_same_model_warning is False
    assert report.judge_same_family_warning is False
    assert report.judge_independence_notes == []


def test_llm_judge_independence_warnings_do_not_expose_api_keys(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case())

    run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_MODEL="gpt-5.4-mini", PROBLEM_QUALITY_MODEL="gpt-5.4-mini"),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
        llm_judge_enabled=True,
        llm_judge=FakeLLMJudge(),
    )

    payload_text = (output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8")
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "API_KEY" not in payload_text
    assert "OPENAI_API_KEY" not in summary
    assert "GEMINI_API_KEY" not in summary


def test_retrieval_golden_chunk_metrics_hit_and_rank(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_relation"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.hit_at_k == 1
    assert result.mrr_at_k == 0.5
    assert result.precision_at_k == 0.5
    assert result.threshold_passed is True


def test_cited_expected_chunk_metrics_are_calculated(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force", "chunk_relation"],
            expected_source_spans=["뉴턴의 제2법칙"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.cited_hit_at_k == 1
    assert result.cited_expected_chunk_recall == 0.5
    assert result.cited_expected_chunk_precision == 1
    assert result.cited_source_span_coverage == 1
    assert result.cited_expected_chunk_ids == ["chunk_force"]
    assert result.uncited_expected_chunk_ids == ["chunk_relation"]
    assert result.cited_non_expected_chunk_ids == []


def test_cited_expected_chunk_precision_counts_non_expected_citations(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=CitesAllRetrievedChunksProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.cited_expected_chunk_recall == 1
    assert result.cited_expected_chunk_precision == 0.5
    assert result.cited_non_expected_chunk_ids == ["chunk_relation"]


def test_generation_context_drop_of_retrieved_expected_chunk_fails(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_relation"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_PACKING_ENABLED=True,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=1,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=1,
        ),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.hit_at_k == 1
    assert result.generation_context_hit_at_k == 0
    assert result.generation_context_chunk_ids == ["chunk_force"]
    assert result.threshold_passed is False
    assert "generation context dropped all expected evidence chunks" in result.threshold_failures


def test_generation_context_source_span_coverage_and_ids_are_reported(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_source_spans=["F = ma"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(
            PROBLEM_AGENT_GENERATION_CONTEXT_PACKING_ENABLED=True,
            PROBLEM_AGENT_GENERATION_CONTEXT_MAX_CHUNKS=1,
            PROBLEM_AGENT_GENERATION_CONTEXT_MIN_CHUNKS=1,
        ),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.returned_chunk_count == 2
    assert result.generation_context_chunk_count == 1
    assert result.generation_context_chunk_ids == ["chunk_force"]
    assert result.generation_context_source_span_coverage == 1
    assert result.retrieved_to_context_reduction_ratio == 0.5

    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["cases"][0]["generation_context_chunk_ids"] == ["chunk_force"]


def test_partial_golden_labels_do_not_fail_low_precision_at_k(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
            min_precision_at_k=0.9,
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.golden_label_mode == "partial"
    assert result.precision_at_k == 0.5
    assert result.threshold_passed is True
    assert not any("precision_at_k" in failure for failure in result.threshold_failures)


def test_exhaustive_golden_labels_fail_low_precision_at_k(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["chunk_force"],
            golden_label_mode="exhaustive",
            min_precision_at_k=0.9,
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.golden_label_mode == "exhaustive"
    assert result.precision_at_k == 0.5
    assert result.threshold_passed is False
    assert "precision_at_k 0.500 < 0.9" in result.threshold_failures


def test_retrieval_golden_chunk_metrics_miss_fails_threshold(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_chunk_ids=["missing_chunk"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.hit_at_k == 0
    assert result.mrr_at_k == 0
    assert result.precision_at_k == 0
    assert result.threshold_passed is False
    assert "hit_at_k 0.000 < 1.0" in result.threshold_failures


def test_retrieval_golden_page_span_and_irrelevant_term_metrics(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_pages=[2],
            expected_source_spans=["같은 힘에서    질량이 커지면", "없는 근거 문장"],
            irrelevant_terms=["F = ma", "없는말"],
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.expected_page_hit == 1
    assert result.source_span_coverage == 0.5
    assert result.irrelevant_term_hit_count == 1
    assert result.threshold_passed is True


def test_threshold_fails_when_expected_source_spans_are_not_retrieved():
    case = load_live_problem_generation_cases_from_row(
        _base_case(
            expected_search_terms=[],
            expected_problem_terms=[],
            expected_source_spans=["missing source span"],
        )
    )

    failures = _threshold_failures(
        **_threshold_failure_kwargs(
            case=case,
            source_span_coverage=0.0,
        )
    )

    assert "source_span_coverage 0.000 < 0.5" in failures


def test_mc_problem_missing_diagnostics_is_marked_risky():
    diagnostic = _problem_quality_diagnostic(
        problem=_mc_problem(choice_diagnostics=None),
        request=_diagnostic_request(),
        source_terms=["뉴턴 제2법칙", "가속도"],
        expected_problem_terms=["조건", "판단"],
    )

    assert diagnostic.multiple_choice_has_choice_diagnostics is False
    assert "missing_choice_diagnostics" in diagnostic.warning_flags
    assert diagnostic.quality_risk_level in {"medium", "high"}


def test_short_answer_without_rubric_is_high_risk():
    diagnostic = _problem_quality_diagnostic(
        problem=_sa_problem(rubric=None),
        request=_diagnostic_request(),
        source_terms=["뉴턴 제2법칙", "가속도"],
        expected_problem_terms=["조건", "설명"],
    )

    assert diagnostic.short_answer_has_rubric is False
    assert "missing_rubric" in diagnostic.warning_flags
    assert diagnostic.quality_risk_level == "high"


def test_strong_multiple_choice_problem_is_low_risk():
    diagnostic = _problem_quality_diagnostic(
        problem=_mc_problem(),
        request=_diagnostic_request(),
        source_terms=["뉴턴 제2법칙", "가속도"],
        expected_problem_terms=["조건", "판단"],
    )

    assert diagnostic.multiple_choice_has_four_choices is True
    assert diagnostic.multiple_choice_has_choice_explanations is True
    assert diagnostic.multiple_choice_has_choice_diagnostics is True
    assert diagnostic.incorrect_distractor_diagnostic_count == 3
    assert diagnostic.high_rigor_operation_detected is True
    assert diagnostic.quality_risk_level == "low"


def test_search_ab_comparison_records_enhanced_search_win(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=["enhanced_only"],
            expected_chunk_ids=["enhanced_chunk"],
            expected_source_spans=["enhanced_only"],
            min_expected_search_term_coverage=0.0,
        ),
    )

    search = QueryAwareSearchService(enhanced_better=True)
    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_AGENT_SEARCH_QUERY_MODE="hybrid"),
        compare_baseline_search=True,
        search_service=search,
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert report.search_query_mode == "hybrid"
    assert result.search_query_mode == "hybrid"
    assert result.baseline_query == "뉴턴 제2법칙 가속도"
    assert result.enhanced_query is not None
    assert result.baseline_expected_search_term_coverage == 0
    assert result.enhanced_expected_search_term_coverage == 1
    assert result.baseline_hit_at_k == 0
    assert result.enhanced_hit_at_k == 1
    assert result.baseline_mrr_at_k == 0
    assert result.enhanced_mrr_at_k == 1
    assert result.baseline_precision_at_k == 0
    assert result.enhanced_precision_at_k == 1
    assert result.baseline_source_span_coverage == 0
    assert result.enhanced_source_span_coverage == 1
    assert result.hit_at_k == 1
    assert result.mrr_at_k == 1
    assert result.precision_at_k == 1
    assert result.source_span_coverage == 1
    assert result.enhanced_wins_search_quality is True
    assert result.enhanced_score_minus_baseline_score is not None
    assert result.enhanced_score_minus_baseline_score > 0
    assert result.search_query == result.enhanced_query
    assert result.baseline_search_ms is not None
    assert result.enhanced_search_ms is not None
    assert result.service_internal_search_ms is not None
    assert result.effective_search_ms == result.enhanced_search_ms
    assert result.search_ms == result.enhanced_search_ms
    assert result.search_ms > result.service_internal_search_ms
    assert result.search_latency_note is not None
    assert "primed chunks" in result.search_latency_note
    assert len(search.calls) == 2

    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["search_query_mode"] == "hybrid"
    assert payload["cases"][0]["search_query_mode"] == "hybrid"
    assert "baseline_query" in payload["cases"][0]
    assert "baseline_search_ms" in payload["cases"][0]
    assert "enhanced_search_ms" in payload["cases"][0]
    assert "baseline_hit_at_k" in payload["cases"][0]
    assert "enhanced_hit_at_k" in payload["cases"][0]
    assert "service_internal_search_ms" in payload["cases"][0]
    assert "enhanced_score_minus_baseline_score" in payload["cases"][0]
    assert "problem_quality_diagnostics" in payload["cases"][0]
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Case Summary" in summary
    assert "## Slowest Cases" in summary
    assert "## Search Latency" in summary
    assert "baseline_search_ms" in summary
    assert "enhanced_search_ms" in summary
    assert "## Highest Reject-Rate Cases" in summary
    assert "## Lowest Search-Quality Cases" in summary
    assert "context_recall" in summary
    assert "cited_recall" in summary
    assert "cited_precision" in summary
    assert "context_span_coverage" in summary
    assert "cited_span_coverage" in summary
    assert "## Lowest Problem-Quality Cases" in summary
    assert "## High-Rigor Operation Distribution" in summary


def test_search_ab_comparison_loss_does_not_fail_without_threshold_flag(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=["baseline_only"],
            min_expected_search_term_coverage=0.0,
        ),
    )

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_AGENT_SEARCH_QUERY_MODE="hybrid"),
        compare_baseline_search=True,
        fail_on_threshold=False,
        search_service=QueryAwareSearchService(enhanced_better=False),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.enhanced_wins_search_quality is False
    assert result.enhanced_score_minus_baseline_score is not None
    assert result.enhanced_score_minus_baseline_score < -0.15
    assert result.threshold_passed is True


def test_search_ab_comparison_large_loss_fails_with_threshold_flag(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=["baseline_only"],
            min_expected_search_term_coverage=0.0,
        ),
    )

    with pytest.raises(AssertionError, match="enhanced search quality score"):
        run_live_problem_generation_eval(
            cases_path=cases_path,
            output_dir=output_dir,
            settings=_settings(PROBLEM_AGENT_SEARCH_QUERY_MODE="hybrid"),
            compare_baseline_search=True,
            fail_on_threshold=True,
            search_service=QueryAwareSearchService(enhanced_better=False),
            problem_agent=FakeProblemAgent(),
            artifact_publisher=FakePublisher(),
        )


def test_search_query_mode_sweep_records_compact_as_best_without_extra_generation(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=["compact_marker"],
            expected_chunk_ids=["compact_chunk"],
            expected_source_spans=["compact_marker"],
            min_expected_search_term_coverage=0.0,
        ),
    )
    problem_agent = CountingProblemAgent()

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_AGENT_SEARCH_QUERY_MODE="compact"),
        search_query_mode_sweep=True,
        search_service=QueryModeSweepSearchService(best_mode="compact"),
        problem_agent=problem_agent,
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.best_query_mode_by_score == "compact"
    assert result.primary_query_mode_score == result.query_mode_scores["compact"]
    assert result.query_mode_scores["compact"] > result.query_mode_scores["expanded"]
    assert result.query_mode_hit_at_k["compact"] == 1
    assert result.query_mode_mrr_at_k["compact"] == 1
    assert result.query_mode_source_span_coverage["compact"] == 1
    assert problem_agent.generate_call_count == 1

    payload = json.loads((output_dir / REPORT_JSON_NAME).read_text(encoding="utf-8"))
    assert payload["cases"][0]["best_query_mode_by_score"] == "compact"
    assert "query_mode_scores" in payload["cases"][0]
    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Search Query Mode Sweep" in summary


def test_search_query_mode_sweep_records_expanded_as_best_and_not_best_section(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(
        cases_path,
        _base_case(
            expected_search_terms=["expanded_marker"],
            expected_chunk_ids=["expanded_chunk"],
            expected_source_spans=["expanded_marker"],
            min_expected_search_term_coverage=0.0,
        ),
    )
    problem_agent = CountingProblemAgent()

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(PROBLEM_AGENT_SEARCH_QUERY_MODE="compact"),
        search_query_mode_sweep=True,
        search_service=QueryModeSweepSearchService(best_mode="expanded"),
        problem_agent=problem_agent,
        artifact_publisher=FakePublisher(),
    )

    result = report.cases[0]
    assert result.best_query_mode_by_score == "expanded"
    assert result.primary_query_mode_score == result.query_mode_scores["compact"]
    assert result.query_mode_scores["expanded"] > result.query_mode_scores["compact"]
    assert problem_agent.generate_call_count == 1

    summary = (output_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Configured Query Mode Not Best" in summary
    assert "expanded" in summary


def test_runner_respects_fail_on_threshold_false(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case(min_returned_chunks=99))

    report = run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=_settings(),
        fail_on_threshold=False,
        search_service=FakeSearchService(),
        problem_agent=FakeProblemAgent(),
        artifact_publisher=FakePublisher(),
    )

    assert report.failed_count == 1
    assert report.cases[0].threshold_passed is False
    assert any("returned_chunk_count" in failure for failure in report.cases[0].threshold_failures)


def test_runner_raises_when_fail_on_threshold_true(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    output_dir = tmp_path / "reports"
    _write_cases(cases_path, _base_case(min_returned_chunks=99))

    with pytest.raises(AssertionError, match="thresholds failed"):
        run_live_problem_generation_eval(
            cases_path=cases_path,
            output_dir=output_dir,
            settings=_settings(),
            fail_on_threshold=True,
            search_service=FakeSearchService(),
            problem_agent=FakeProblemAgent(),
            artifact_publisher=FakePublisher(),
        )


@pytest.mark.llm
@pytest.mark.rag
def test_live_problem_generation_benchmark_from_env():
    preflight = live_problem_generation_preflight_from_env()
    if not preflight.can_run:
        pytest.skip(live_eval_preflight_skip_message(preflight))

    report = run_live_problem_generation_eval_from_env()

    assert report.case_count > 0
