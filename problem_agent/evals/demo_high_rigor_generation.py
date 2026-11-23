from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.db import Base
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.services.problem_service import ProblemService


class LocalSearchService:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks
        self.last_top_k: int | None = None

    def search_chunks(self, **kwargs):
        self.last_top_k = kwargs.get("top_k")
        document_id = kwargs["document_id"]
        return [chunk.model_copy(update={"document_id": document_id}) for chunk in self.chunks[: self.last_top_k]]

    def get_chunks_by_ids(self, **kwargs):
        chunk_ids = set(kwargs["chunk_ids"])
        return [chunk for chunk in self.chunks if chunk.chunk_id in chunk_ids]


class DemoProblemAgent:
    def generate(self, request, chunks, **kwargs):
        return [demo_high_rigor_problem(request, chunks)]


def main() -> None:
    openai_api_key = os.getenv("OPENAI_API_KEY") or None
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"
    settings = Settings(
        OPENAI_API_KEY=openai_api_key,
        LLM_FALLBACK_ENABLED=openai_api_key is None,
    )
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()

    chunks = math_chunks() if mode != "fallback" else newton_chunks()
    search_service = LocalSearchService(chunks)
    service = ProblemService(
        db=db,
        search_service=search_service,
        problem_agent=_problem_agent_for_mode(mode=mode, settings=settings, openai_api_key=openai_api_key),
        quality_checker=ProblemQualityChecker(),
    )

    request = fallback_request() if mode == "fallback" else high_rigor_request()
    result = service.generate_problem_batch(user_id="demo_user", request=request)
    problem = result.problems[0]

    output = {
        "mode": mode,
        "using_real_llm": openai_api_key is not None,
        "note": _note(mode=mode, openai_api_key=openai_api_key),
        "search_top_k": search_service.last_top_k,
        "high_rigor_profile": result.high_rigor_profile.model_dump(mode="json"),
        "quality_summary": result.quality_summary.model_dump(mode="json"),
        "problem": {
            "id": problem.id,
            "document_id": problem.document_id,
            "type": problem.type,
            "difficulty": problem.difficulty,
            "bloom_level": problem.bloom_level,
            "question": problem.question,
            "concepts": problem.concepts,
            "source_chunk_ids": problem.source_chunk_ids,
            "answer": problem.answer,
            "explanation": problem.explanation,
            "rubric": problem.rubric,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _problem_agent_for_mode(*, mode: str, settings: Settings, openai_api_key: str | None):
    if openai_api_key or mode == "fallback":
        return ProblemAgent(settings=settings)
    return DemoProblemAgent()


def _note(*, mode: str, openai_api_key: str | None) -> str:
    if openai_api_key:
        return "OPENAI_API_KEY를 사용해 실제 LLM 문제 생성을 실행했다. API 비용이 발생할 수 있다."
    if mode == "fallback":
        return "OPENAI_API_KEY 없이 실제 ProblemAgent deterministic fallback 생성 경로를 실행했다."
    return "OPENAI_API_KEY가 없어서 고정 샘플 문제를 출력한다. 고난도 라우팅/품질 요약 확인용이다."


def high_rigor_request() -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="math_demo_doc",
        concepts=["함수의 극한", "연속", "도함수"],
        type="short_answer",
        count=1,
        user_requirements=(
            "시험에 나올 법한 여러 개념이 섞인 고난도 예상 문제를 만들어줘. "
            "해결 과정이 여러 단계로 나뉘고 조건 해석이 필요한 문제였으면 좋겠어."
        ),
    )


def fallback_request() -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="newton_demo_doc",
        concepts=["뉴턴 제2법칙"],
        type="short_answer",
        count=1,
        user_requirements="시험 대비 예상 문제로 실제 수식을 대입해서 푸는 고난도 계산 문제를 만들어줘.",
    )


def math_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="math_chunk_001",
            document_id="math_demo_doc",
            content=(
                "함수의 극한에서는 x가 어떤 값에 가까워질 때 함수값이 가까워지는 값을 본다. "
                "좌극한과 우극한이 같고 그 값이 함수값과 같으면 함수는 그 점에서 연속이다."
            ),
            page=1,
            section_title="함수의 극한과 연속",
            concepts=["함수의 극한", "연속", "좌극한", "우극한"],
        ),
        RetrievedChunk(
            chunk_id="math_chunk_002",
            document_id="math_demo_doc",
            content=(
                "미분계수는 한 점에서의 순간 변화율이며 접선의 기울기와 같다. "
                "도함수의 부호가 양수이면 함수는 증가하고, 음수이면 감소한다."
            ),
            page=2,
            section_title="미분계수와 도함수",
            concepts=["미분계수", "도함수", "증가와 감소"],
        ),
        RetrievedChunk(
            chunk_id="math_chunk_003",
            document_id="math_demo_doc",
            content=(
                "극값을 찾을 때는 도함수가 0이 되는 점과 부호 변화를 확인한다. "
                "연속성과 미분 가능성을 함께 확인해야 구간별 함수의 그래프를 정확히 판단할 수 있다."
            ),
            page=3,
            section_title="극값과 그래프 해석",
            concepts=["극값", "부호 변화", "그래프 해석"],
        ),
    ]


def newton_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="newton_chunk_001",
            document_id="newton_demo_doc",
            content=(
                "뉴턴의 제2법칙은 F = ma이다. 같은 힘이 작용할 때 질량이 클수록 "
                "가속도는 작아지고, 가속도는 힘에 비례하며 질량에 반비례한다."
            ),
            page=1,
            section_title="뉴턴의 운동 법칙",
            concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
        )
    ]


def demo_high_rigor_problem(request: GenerateProblemRequest, chunks: list[RetrievedChunk]) -> dict:
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


if __name__ == "__main__":
    main()
