from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.agents import (
    FeedbackAgent,
    LearningContentAgent,
    LearningContentQualityChecker,
    ProblemAgent,
    ProblemQualityChecker,
)
from app.db import get_db
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.learning_content_repository import LearningContentRepository
from app.repositories.mistake_remediation_event_repository import MistakeRemediationEventRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.usage_ledger_repository import UsageLedgerRepository
from app.services.feedback_service import FeedbackService
from app.services.assessment_session_readiness_service import AssessmentSessionReadinessService
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.learning_content_service import LearningContentService
from app.services.problem_service import ProblemService
from app.services.search_service import SearchService


_learning_content_repository = LearningContentRepository()


async def get_user_id(x_user_id: str | None = Header(default=None)) -> str:
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is required")
    return user_id


async def get_search_service() -> SearchService:
    return SearchService()


async def get_generated_artifact_publisher() -> GeneratedArtifactPublisher:
    return GeneratedArtifactPublisher()


def build_problem_service(
    db: Session,
    search_service: SearchService,
    artifact_publisher: GeneratedArtifactPublisher | None = None,
) -> ProblemService:
    return ProblemService(
        db=db,
        search_service=search_service,
        problem_agent=ProblemAgent(),
        quality_checker=ProblemQualityChecker(),
        artifact_publisher=artifact_publisher,
    )


def build_feedback_service(
    db: Session,
    search_service: SearchService,
    artifact_publisher: GeneratedArtifactPublisher | None = None,
) -> FeedbackService:
    return FeedbackService(
        db=db,
        feedback_agent=FeedbackAgent(),
        search_service=search_service,
        artifact_publisher=artifact_publisher,
    )


async def get_learning_content_repository() -> LearningContentRepository:
    return _learning_content_repository


def build_learning_content_service(
    db: Session,
    search_service: SearchService,
    repository: LearningContentRepository,
    artifact_publisher: GeneratedArtifactPublisher | None = None,
) -> LearningContentService:
    return LearningContentService(
        search_service=search_service,
        learning_content_agent=LearningContentAgent(),
        quality_checker=LearningContentQualityChecker(),
        repository=repository,
        feedback_repository=FeedbackRepository(db),
        problem_repository=ProblemRepository(db),
        problem_service=build_problem_service(
            db=db,
            search_service=search_service,
            artifact_publisher=artifact_publisher,
        ),
        remediation_repository=MistakeRemediationEventRepository(db),
        artifact_publisher=artifact_publisher,
        usage_ledger_repository=UsageLedgerRepository(db),
    )


async def get_problem_service(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
    artifact_publisher: GeneratedArtifactPublisher = Depends(get_generated_artifact_publisher),
) -> ProblemService:
    return build_problem_service(
        db=db,
        search_service=search_service,
        artifact_publisher=artifact_publisher,
    )


async def get_feedback_service(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
    artifact_publisher: GeneratedArtifactPublisher = Depends(get_generated_artifact_publisher),
) -> FeedbackService:
    return build_feedback_service(
        db=db,
        search_service=search_service,
        artifact_publisher=artifact_publisher,
    )


async def get_assessment_session_readiness_service(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
) -> AssessmentSessionReadinessService:
    return AssessmentSessionReadinessService(db=db, search_service=search_service)


async def get_learning_content_service(
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
    repository: LearningContentRepository = Depends(get_learning_content_repository),
    artifact_publisher: GeneratedArtifactPublisher = Depends(get_generated_artifact_publisher),
) -> LearningContentService:
    return build_learning_content_service(
        db=db,
        search_service=search_service,
        repository=repository,
        artifact_publisher=artifact_publisher,
    )
