from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_learning_content_service, get_user_id
from app.llm import LLMServiceError
from app.schemas.learning_contents import (
    GenerateLearningContentRequest,
    GenerateLearningContentResponse,
    GenerateMiniExamRequest,
    GenerateMistakeDrillRequest,
    LearningContentRecommendationResponse,
    LearningContentBase,
    LearningContentInteractionMode,
    LearningContentResponse,
    LearningContentType,
    RecommendLearningContentRequest,
)
from app.services.learning_content_service import LearningContentService
from app.services.search_service import SearchAgentError

router = APIRouter(prefix="/api", tags=["learning-contents"])


def to_learning_content_response(
    content: LearningContentBase,
    *,
    include_private: bool = False,
) -> LearningContentResponse:
    private_available = _has_private_learning_content_payload(content)
    return LearningContentResponse(
        id=content.id,
        user_id=content.user_id,
        document_id=content.document_id,
        content_type=content.content_type,
        interaction_mode=content.interaction_mode or LearningContentInteractionMode.study_only,
        concepts=content.concepts,
        source_chunk_ids=content.source_chunk_ids,
        source_revision_ids=content.source_revision_ids,
        content_version=content.content_version,
        difficulty=content.difficulty,
        bloom_level=content.bloom_level,
        quality_status=content.quality_status,
        quality_report=content.quality_report,
        material_readiness=content.material_readiness,
        payload=content.payload if include_private else _public_learning_content_payload(content),
        private_payload_available=private_available,
        display_copy=content.display_copy,
        created_at=content.created_at,
    )


def _has_private_learning_content_payload(content: LearningContentBase) -> bool:
    return content.content_type in {
        LearningContentType.cloze,
        LearningContentType.true_false,
        LearningContentType.ordering,
        LearningContentType.matching,
    }


def _public_learning_content_payload(content: LearningContentBase) -> dict:
    payload = content.payload
    if content.content_type == LearningContentType.cloze:
        return {"prompt": payload["prompt"]}
    if content.content_type == LearningContentType.true_false:
        return {"statement": payload["statement"]}
    if content.content_type == LearningContentType.ordering:
        return {
            "prompt": payload["prompt"],
            "items": payload["items"],
        }
    if content.content_type == LearningContentType.matching:
        pairs = payload.get("pairs") or []
        return {
            "prompt": payload["prompt"],
            "left_items": [{"id": f"L{index + 1}", "text": pair["left"]} for index, pair in enumerate(pairs)],
            "right_items": [{"id": f"R{index + 1}", "text": pair["right"]} for index, pair in enumerate(pairs)],
        }
    return payload


@router.post("/learning-contents/generate", response_model=GenerateLearningContentResponse)
def generate_learning_contents(
    request: GenerateLearningContentRequest,
    user_id: str = Depends(get_user_id),
    service: LearningContentService = Depends(get_learning_content_service),
) -> GenerateLearningContentResponse:
    try:
        result = service.generate_contents(user_id=user_id, request=request)
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GenerateLearningContentResponse(
        contents=[to_learning_content_response(content, include_private=False) for content in result.contents],
        learning_task_strategy=result.learning_task_strategy,
        material_readiness=result.material_readiness,
    )


@router.post("/learning-contents/recommendations", response_model=LearningContentRecommendationResponse)
def recommend_learning_content_types(
    request: RecommendLearningContentRequest,
    _user_id: str = Depends(get_user_id),
    service: LearningContentService = Depends(get_learning_content_service),
) -> LearningContentRecommendationResponse:
    try:
        result = service.recommend_content_types(request=request)
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LearningContentRecommendationResponse(
        problem_options=result.problem_options,
        content_options=result.content_options,
        selectable_content_types=result.selectable_content_types,
        available_content_types=result.available_content_types,
        recommended_content_types=result.recommended_content_types,
        not_recommended_content_types=result.not_recommended_content_types,
        reason=result.reason,
        learning_task_strategy=result.learning_task_strategy,
        material_readiness=result.material_readiness,
    )


@router.post("/learning-contents/mini-exams/generate", response_model=GenerateLearningContentResponse)
def generate_mini_exam(
    request: GenerateMiniExamRequest,
    user_id: str = Depends(get_user_id),
    service: LearningContentService = Depends(get_learning_content_service),
) -> GenerateLearningContentResponse:
    try:
        result = service.generate_mini_exam(user_id=user_id, request=request)
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GenerateLearningContentResponse(
        contents=[to_learning_content_response(content, include_private=False) for content in result.contents]
    )


@router.get("/learning-contents/{content_id}", response_model=LearningContentResponse)
def get_learning_content(
    content_id: str,
    user_id: str = Depends(get_user_id),
    service: LearningContentService = Depends(get_learning_content_service),
) -> LearningContentBase:
    content = service.get_content(content_id)
    if content is None or content.user_id != user_id:
        raise HTTPException(status_code=404, detail="Learning content not found")
    return to_learning_content_response(content, include_private=False)


@router.post("/learning-contents/mistake-drills/generate", response_model=GenerateLearningContentResponse)
def generate_mistake_drills(
    request: GenerateMistakeDrillRequest,
    user_id: str = Depends(get_user_id),
    service: LearningContentService = Depends(get_learning_content_service),
) -> GenerateLearningContentResponse:
    try:
        result = service.generate_mistake_drills(user_id=user_id, request=request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SearchAgentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GenerateLearningContentResponse(
        contents=[to_learning_content_response(content, include_private=False) for content in result.contents]
    )
