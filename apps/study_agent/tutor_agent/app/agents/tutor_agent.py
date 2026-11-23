from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.modules.guard_harness import enforce_tutor_output, guard_question
from app.modules.personalization import (
    apply_local_personalization,
    build_personalization_instructions,
    build_user_model,
)
from app.modules.rag import chunks_to_sources, compose_local_answer, retrieve_relevant_chunks
from app.modules.rag_client import fetch_chunks
from app.schemas.common import AgentContext, AgentRequest, AgentResponse, AgentTrace, GuardResult
from app.services.llm_client import create_tutor_answer, get_ai_provider


class TutorAgent(BaseAgent):
    name = "tutor"
    version = "1.0.0"

    async def normalize_input(self, request: AgentRequest, trace: AgentTrace) -> AgentRequest:
        payload = dict(request.payload or {})
        payload["question"] = str(payload.get("question") or "").strip()

        # document_id만 있고 chunks가 없으면 RAG에서 자동으로 가져온다
        if request.document_id and not payload.get("chunks") and not payload.get("document"):
            rag_chunks = await fetch_chunks(
                document_id=request.document_id,
                question=payload["question"],
                top_k=6,
            )
            if rag_chunks:
                payload["chunks"] = rag_chunks

        return request.model_copy(
            update={
                "agent_type": "tutor",
                "request_type": request.request_type or "tutor.answer",
                "selected_text": str(request.selected_text or "").strip(),
                "section_id": str(request.section_id or "").strip() or None,
                "payload": payload,
            }
        )

    async def check_preconditions(self, request: AgentRequest, trace: AgentTrace) -> GuardResult:
        return guard_question(
            question=str(request.payload.get("question") or ""),
            document=get_document_payload(request),
            selected_text=request.selected_text or "",
        )

    async def build_context(self, request: AgentRequest, trace: AgentTrace) -> AgentContext:
        payload = request.payload or {}
        document = get_document_payload(request)
        user_model = build_user_model(
            requested_level=request.options.level,
            attempts=list(payload.get("attempts") or []),
            questions=list(payload.get("questions") or []),
            preferences=dict(payload.get("preferences") or {}),
        )
        chunks = retrieve_relevant_chunks(
            document=document,
            question=str(payload.get("question") or ""),
            selected_text=request.selected_text or "",
            section_id=request.section_id,
            limit=6 if request.options.mode == "deep" else 5,
        )
        return AgentContext(
            user_model=user_model,
            document=document,
            retrieved_chunks=chunks,
            sources=chunks_to_sources(chunks),
            history={
                "attempts": list(payload.get("attempts") or []),
                "questions": list(payload.get("questions") or []),
            },
        )

    async def create_plan(self, request: AgentRequest, context: AgentContext, trace: AgentTrace) -> dict[str, Any]:
        provider = get_ai_provider()
        return {
            "provider": provider,
            "use_local_fallback": provider == "local",
            "personalization_instructions": build_personalization_instructions(context.user_model),
            "include_sources": request.options.include_sources,
        }

    async def generate(
        self,
        request: AgentRequest,
        context: AgentContext,
        plan: dict[str, Any],
        trace: AgentTrace,
    ) -> dict[str, Any]:
        question = str(request.payload.get("question") or "")
        if not plan["use_local_fallback"]:
            answer = await create_tutor_answer(
                question=question,
                selected_text=request.selected_text or "",
                chunks=context.retrieved_chunks,
                document_title=str(context.document.get("title") or ""),
                personalization_instructions=plan["personalization_instructions"],
            )
            if answer:
                return {"answer": answer}

        local_answer = compose_local_answer(question, context.retrieved_chunks)
        return {
            "answer": apply_local_personalization(local_answer, context.user_model),
            "local_fallback": True,
        }

    async def postprocess(
        self,
        draft: dict[str, Any],
        request: AgentRequest,
        context: AgentContext,
        plan: dict[str, Any],
        trace: AgentTrace,
    ) -> AgentResponse:
        answer = enforce_tutor_output(draft.get("answer"))
        provider = plan["provider"]
        mode = "local-tutor-agent-rag" if draft.get("local_fallback") else f"{provider}-tutor-agent-rag"
        return AgentResponse(
            ok=True,
            agent_type=self.name,
            mode=mode,
            answer=answer,
            data={
                "user_model": context.user_model,
                "chunk_count": len(context.retrieved_chunks),
            },
            sources=context.sources if plan["include_sources"] else [],
            guard=GuardResult(allowed=True, reason="allowed"),
            trace=trace,
        )


def get_document_payload(request: AgentRequest) -> dict[str, Any]:
    payload = request.payload or {}
    document = dict(payload.get("document") or {})
    if payload.get("chunks"):
        document["chunks"] = payload["chunks"]
    if request.document_id and not document.get("id"):
        document["id"] = request.document_id
    return document

