from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import time

import httpx

from app.config import Settings, get_settings
from app.models import Feedback, Problem
from app.schemas.integration_contracts import (
    GeneratedArtifactIndexPayload,
    GeneratedArtifactType,
    GeneratedArtifactVisibility,
    UserConceptUpdatePayload,
)
from app.schemas.learning_contents import LearningContentBase, LearningContentType
from app.schemas.problems import AssessmentSessionReportResponse


class GeneratedArtifactPublishError(RuntimeError):
    """Raised when the generated artifact index API rejects a publish request."""


@dataclass(frozen=True)
class ArtifactPublishBatchResult:
    attempted: int
    succeeded: int
    failed: int
    elapsed_ms: float
    errors: list[str] = field(default_factory=list)


INDEX_SUMMARY_LIST_LIMIT = 20
INDEX_CONTENT_CHAR_LIMIT = 4000
INDEX_TRUNCATION_MARKER = "\n... [truncated for index]"


class GeneratedArtifactPublisher:
    """Publishes generated problems and feedback to the shared vector index API.

    The publisher is intentionally outbound-only. Vector DB storage and embedding
    remain owned by the RAG/Search part, while this module sends enough private
    metadata for later retrieval.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def publish_problem(self, problem: Problem) -> bool:
        if not self._problem_publish_enabled():
            return False
        payload = self.build_problem_payload(problem)
        return self._publish_payload(payload)

    def publish_problems(self, problems: list[Problem]) -> ArtifactPublishBatchResult:
        started = time.perf_counter()
        if not problems or not self._problem_publish_enabled():
            return ArtifactPublishBatchResult(
                attempted=0,
                succeeded=0,
                failed=0,
                elapsed_ms=self._elapsed_ms(started),
            )
        if len(problems) == 1:
            return self._publish_problems_sequential(problems=problems, started=started)

        payloads: list[GeneratedArtifactIndexPayload] = []
        errors: list[str] = []
        for problem in problems:
            try:
                payloads.append(self.build_problem_payload(problem))
            except Exception as exc:
                if self.settings.generated_artifact_publish_fail_fast:
                    raise
                errors.append(str(exc))

        if not payloads:
            return ArtifactPublishBatchResult(
                attempted=len(problems),
                succeeded=0,
                failed=len(problems),
                elapsed_ms=self._elapsed_ms(started),
                errors=errors,
            )

        with httpx.Client(timeout=self.settings.generated_artifact_timeout_seconds) as client:
            if self.settings.generated_artifact_publish_fail_fast:
                result = self._publish_payloads_sequential_with_client(
                    client=client,
                    payloads=payloads,
                    started=started,
                    attempted=len(problems),
                )
            else:
                result = self._publish_payloads_concurrently_with_client(
                    client=client,
                    payloads=payloads,
                    started=started,
                    attempted=len(problems),
                )
        if errors:
            return ArtifactPublishBatchResult(
                attempted=result.attempted,
                succeeded=result.succeeded,
                failed=result.failed + len(errors),
                elapsed_ms=result.elapsed_ms,
                errors=[*errors, *result.errors],
            )
        return result

    def publish_problem_to_rag_add(self, problem: Problem) -> bool:
        return self.publish_payload_to_rag_add(self.build_problem_payload(problem))

    def publish_feedback(self, feedback: Feedback, *, problem: Problem | None = None) -> bool:
        if not self._enabled():
            return False
        payload = self.build_feedback_payload(feedback, problem=problem)
        return self._publish_payload(payload)

    def publish_feedback_to_rag_add(self, feedback: Feedback, *, problem: Problem | None = None) -> bool:
        return self.publish_payload_to_rag_add(self.build_feedback_payload(feedback, problem=problem))

    def publish_assessment_report(self, report: AssessmentSessionReportResponse, *, user_id: str) -> bool:
        if not self._enabled():
            return False
        payload = self.build_assessment_report_payload(report, user_id=user_id)
        return self._publish_payload(payload)

    def publish_learning_content(self, content: LearningContentBase) -> bool:
        if not self._enabled():
            return False
        payload = self.build_learning_content_payload(content)
        return self._publish_payload(payload)

    def publish_user_concept_update(self, update: UserConceptUpdatePayload, *, problem: Problem) -> bool:
        if not self._enabled():
            return False
        payload = self.build_user_concept_update_payload(update, problem=problem)
        return self._publish_payload(payload)

    def publish_payload_to_rag_add(self, payload: GeneratedArtifactIndexPayload) -> bool:
        rag_add_url = self._rag_add_url_for_payload(payload)
        if not rag_add_url:
            return False
        return self._post_rag_add(payload, rag_add_url=rag_add_url)

    def _publish_payload(self, payload: GeneratedArtifactIndexPayload) -> bool:
        if self.settings.generated_artifact_publish_enabled and self.settings.generated_artifact_index_url:
            return self._post(payload)
        rag_add_url = self._rag_add_url_for_payload(payload)
        if rag_add_url:
            return self._post_rag_add(payload, rag_add_url=rag_add_url)
        return False

    def _publish_payload_with_client(
        self,
        client: httpx.Client,
        payload: GeneratedArtifactIndexPayload,
    ) -> bool:
        if self.settings.generated_artifact_publish_enabled and self.settings.generated_artifact_index_url:
            return self._post_with_client(client, payload)
        rag_add_url = self._rag_add_url_for_payload(payload)
        if rag_add_url:
            return self._post_rag_add_with_client(client, payload, rag_add_url=rag_add_url)
        return False

    def _publish_problems_sequential(
        self,
        *,
        problems: list[Problem],
        started: float,
    ) -> ArtifactPublishBatchResult:
        succeeded = 0
        failed = 0
        errors: list[str] = []
        for problem in problems:
            try:
                if self.publish_problem(problem):
                    succeeded += 1
                else:
                    if self.settings.generated_artifact_publish_fail_fast:
                        raise GeneratedArtifactPublishError("Generated artifact publish returned false")
                    failed += 1
            except Exception as exc:
                if self.settings.generated_artifact_publish_fail_fast:
                    raise
                failed += 1
                errors.append(str(exc))
        return ArtifactPublishBatchResult(
            attempted=len(problems),
            succeeded=succeeded,
            failed=failed,
            elapsed_ms=self._elapsed_ms(started),
            errors=errors,
        )

    def _publish_problems_concurrently(
        self,
        *,
        problems: list[Problem],
        started: float,
    ) -> ArtifactPublishBatchResult:
        max_workers = min(len(problems), self.settings.generated_artifact_publish_concurrency)
        succeeded = 0
        failed = 0
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._publish_problem_capture_error, problem) for problem in problems]
            for future in as_completed(futures):
                ok, error = future.result()
                if ok:
                    succeeded += 1
                else:
                    failed += 1
                    if error:
                        errors.append(error)
        return ArtifactPublishBatchResult(
            attempted=len(problems),
            succeeded=succeeded,
            failed=failed,
            elapsed_ms=self._elapsed_ms(started),
            errors=errors,
        )

    def _publish_payloads_sequential_with_client(
        self,
        *,
        client: httpx.Client,
        payloads: list[GeneratedArtifactIndexPayload],
        started: float,
        attempted: int,
    ) -> ArtifactPublishBatchResult:
        succeeded = 0
        failed = 0
        errors: list[str] = []
        for payload in payloads:
            try:
                if self._publish_payload_with_client(client, payload):
                    succeeded += 1
                else:
                    raise GeneratedArtifactPublishError("Generated artifact publish returned false")
            except Exception as exc:
                if self.settings.generated_artifact_publish_fail_fast:
                    raise
                failed += 1
                errors.append(str(exc))
        return ArtifactPublishBatchResult(
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            elapsed_ms=self._elapsed_ms(started),
            errors=errors,
        )

    def _publish_payloads_concurrently_with_client(
        self,
        *,
        client: httpx.Client,
        payloads: list[GeneratedArtifactIndexPayload],
        started: float,
        attempted: int,
    ) -> ArtifactPublishBatchResult:
        max_workers = min(len(payloads), self.settings.generated_artifact_publish_concurrency)
        succeeded = 0
        failed = 0
        errors: list[str] = []
        # httpx.Client can be shared for concurrent requests, which lets this
        # batch path reuse one connection pool instead of opening one per item.
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._publish_payload_capture_error_with_client, client, payload)
                for payload in payloads
            ]
            for future in as_completed(futures):
                ok, error = future.result()
                if ok:
                    succeeded += 1
                else:
                    failed += 1
                    if error:
                        errors.append(error)
        return ArtifactPublishBatchResult(
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            elapsed_ms=self._elapsed_ms(started),
            errors=errors,
        )

    def _publish_problem_capture_error(self, problem: Problem) -> tuple[bool, str | None]:
        try:
            return self.publish_problem(problem), None
        except Exception as exc:
            return False, str(exc)

    def _publish_payload_capture_error_with_client(
        self,
        client: httpx.Client,
        payload: GeneratedArtifactIndexPayload,
    ) -> tuple[bool, str | None]:
        try:
            ok = self._publish_payload_with_client(client, payload)
            return ok, None if ok else "Generated artifact publish returned false"
        except Exception as exc:
            return False, str(exc)

    def build_problem_payload(self, problem: Problem) -> GeneratedArtifactIndexPayload:
        choices_text = self._choices_text(problem)
        content = "\n".join(
            part
            for part in [
                f"문제: {problem.question}",
                choices_text,
                "정답과 해설은 제출 전 검색 결과에 노출하지 않습니다.",
            ]
            if part
        )
        return GeneratedArtifactIndexPayload(
            artifact_id=problem.id,
            artifact_type=GeneratedArtifactType.problem,
            user_id=problem.user_id,
            document_id=problem.document_id,
            content=self._bounded_content(content),
            metadata={
                "schema_version": "problem_artifact.v1",
                "producer": "problem_agent",
                "problem_id": problem.id,
                "question": problem.question,
                "problem_type": problem.type,
                "difficulty": problem.difficulty,
                "bloom_level": problem.bloom_level,
                "concepts": problem.concepts or [],
                "source_chunk_ids": problem.source_chunk_ids or [],
                "source_refs": problem.source_refs or [],
                "quality_status": problem.quality_status,
                "item_model_id": problem.item_model_id,
                "answer_hidden_until_submission": True,
            },
            source_chunk_ids=problem.source_chunk_ids or [],
            visibility=GeneratedArtifactVisibility.hidden_until_submission,
            created_at=problem.created_at,
        )

    def build_feedback_payload(
        self,
        feedback: Feedback,
        *,
        problem: Problem | None = None,
    ) -> GeneratedArtifactIndexPayload:
        feedback_problem = problem or feedback.problem
        document_id = feedback_problem.document_id if feedback_problem else ""
        if not document_id:
            raise ValueError("feedback artifact requires a problem document_id")
        content = "\n".join(
            part
            for part in [
                f"피드백 요약: {feedback.summary}",
                f"피드백: {feedback.feedback}",
                self._recommended_review_text(feedback.recommended_review),
            ]
            if part
        )
        weak_concepts = self._limited_texts(feedback.weak_concepts)
        recommended_review = self._limited_texts(feedback.recommended_review)
        return GeneratedArtifactIndexPayload(
            artifact_id=feedback.id,
            artifact_type=GeneratedArtifactType.feedback,
            user_id=feedback.user_id,
            document_id=document_id,
            content=self._bounded_content(content),
            metadata={
                "schema_version": "feedback_artifact.v1",
                "producer": "problem_agent",
                "feedback_id": feedback.id,
                "problem_id": feedback.problem_id,
                "submission_id": feedback.submission_id,
                "summary": feedback.summary,
                "is_correct": feedback.is_correct,
                "score": feedback.score,
                "max_score": feedback.max_score,
                "mistake_type": feedback.mistake_type,
                "learning_state": feedback.learning_state,
                "weak_concepts": weak_concepts,
                "recommended_review": recommended_review,
                "source_chunk_ids": feedback.source_chunk_ids or [],
            },
            source_chunk_ids=feedback.source_chunk_ids or [],
            visibility=GeneratedArtifactVisibility.private,
            created_at=feedback.created_at,
        )

    def build_assessment_report_payload(
        self,
        report: AssessmentSessionReportResponse,
        *,
        user_id: str,
    ) -> GeneratedArtifactIndexPayload:
        score_text = (
            f"{report.total_score:g}/{report.max_score:g}"
            if report.max_score
            else "not_scored"
        )
        content = "\n".join(
            part
            for part in [
                f"평가 세트 리포트: {report.session_id}",
                f"점수: {score_text}",
                f"완료율: {report.completion_ratio:.0%}",
                self._concept_list_text("잘한 개념", report.strong_concepts),
                self._concept_list_text("약점 개념", report.weak_concepts),
                self._recommended_review_text(report.recommended_review),
                f"다음 행동: {report.next_step}",
            ]
            if part
        )
        strong_concepts = self._limited_texts(report.strong_concepts)
        weak_concepts = self._limited_texts(report.weak_concepts)
        recommended_review = self._limited_texts(report.recommended_review)
        return GeneratedArtifactIndexPayload(
            artifact_id=f"assessment_report:{report.session_id}",
            artifact_type=GeneratedArtifactType.assessment_report,
            user_id=user_id,
            document_id=report.document_id,
            content=self._bounded_content(content),
            metadata={
                "schema_version": "assessment_report_artifact.v1",
                "producer": "problem_agent",
                "session_id": report.session_id,
                "retry_of_session_id": report.retry_of_session_id,
                "status": report.status.value,
                "problem_count": report.problem_count,
                "submitted_count": report.submitted_count,
                "correct_count": report.correct_count,
                "total_score": report.total_score,
                "max_score": report.max_score,
                "score_ratio": report.score_ratio,
                "completion_ratio": report.completion_ratio,
                "total_elapsed_time_sec": report.total_elapsed_time_sec,
                "time_limit_seconds": report.time_limit_seconds,
                "time_over_limit": report.time_over_limit,
                "strong_concepts": strong_concepts,
                "weak_concepts": weak_concepts,
                "recommended_review": recommended_review,
                "next_step": report.next_step,
                "concept_score_deltas": self._limited_mapping(report.concept_score_deltas),
                "previous_score_ratio": report.previous_score_ratio,
                "score_delta": report.score_delta,
                "concept_summary": self._assessment_concept_summary(report),
            },
            source_chunk_ids=[],
            visibility=GeneratedArtifactVisibility.private,
            created_at=report.submitted_at or report.created_at,
        )

    def build_learning_content_payload(self, content: LearningContentBase) -> GeneratedArtifactIndexPayload:
        if not content.id:
            raise ValueError("learning content artifact requires content id")
        if not content.user_id:
            raise ValueError("learning content artifact requires user_id")
        return GeneratedArtifactIndexPayload(
            artifact_id=content.id,
            artifact_type=GeneratedArtifactType.learning_content,
            user_id=content.user_id,
            document_id=content.document_id,
            content=self._bounded_content(self._learning_content_index_text(content)),
            metadata={
                "schema_version": "learning_content_artifact.v1",
                "producer": "problem_agent",
                "content_id": content.id,
                "content_type": content.content_type.value,
                "interaction_mode": (content.interaction_mode.value if content.interaction_mode else None),
                "concepts": content.concepts,
                "difficulty": content.difficulty.value,
                "bloom_level": content.bloom_level.value,
                "quality_status": content.quality_status.value,
                "quality_score": content.quality_report.score,
                "source_chunk_ids": content.source_chunk_ids,
                "source_revision_ids": content.source_revision_ids,
                "content_version": content.content_version,
                "private_payload_available": self._learning_content_has_hidden_payload(content),
            },
            source_chunk_ids=content.source_chunk_ids,
            visibility=GeneratedArtifactVisibility.private,
            created_at=content.created_at,
        )

    def build_user_concept_update_payload(
        self,
        update: UserConceptUpdatePayload,
        *,
        problem: Problem,
    ) -> GeneratedArtifactIndexPayload:
        concepts = self._limited_texts(update.weak_concepts or update.concepts)
        concepts_text = ", ".join(concepts)
        score_text = f"{update.score:g}/{update.max_score:g}"
        content = "\n".join(
            part
            for part in [
                f"학습 신호: {concepts_text}",
                f"점수: {score_text}",
                f"학습 상태: {update.learning_state.value}",
                self._recommended_review_text(update.recommended_review),
            ]
            if part
        )
        return GeneratedArtifactIndexPayload(
            artifact_id=f"learning_signal:{update.feedback_id}",
            artifact_type=GeneratedArtifactType.learning_signal,
            user_id=update.user_id,
            document_id=problem.document_id,
            content=self._bounded_content(content),
            metadata={
                "schema_version": "learning_signal_artifact.v1",
                "producer": "problem_agent",
                "problem_id": update.problem_id,
                "submission_id": update.submission_id,
                "feedback_id": update.feedback_id,
                "concepts": self._limited_texts(update.concepts),
                "is_correct": update.is_correct,
                "score": update.score,
                "max_score": update.max_score,
                "mistake_type": update.mistake_type.value if update.mistake_type else None,
                "learning_state": update.learning_state.value,
                "weak_concepts": self._limited_texts(update.weak_concepts),
                "recommended_review": self._limited_texts(update.recommended_review),
                "mastery_updates": [
                    item.model_dump(mode="json")
                    for item in update.mastery_updates[:INDEX_SUMMARY_LIST_LIMIT]
                ],
                "source_chunk_ids": problem.source_chunk_ids or [],
            },
            source_chunk_ids=problem.source_chunk_ids or [],
            visibility=GeneratedArtifactVisibility.private,
        )

    def _post(self, payload: GeneratedArtifactIndexPayload) -> bool:
        try:
            kwargs = {
                "json": payload.model_dump(mode="json"),
                "timeout": self.settings.generated_artifact_timeout_seconds,
            }
            headers = self._headers()
            if headers:
                kwargs["headers"] = headers
            response = httpx.post(
                self.settings.generated_artifact_index_url,
                **kwargs,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            if self.settings.generated_artifact_publish_fail_fast:
                raise GeneratedArtifactPublishError(f"Generated artifact publish failed: {exc}") from exc
            return False
        return True

    def _post_with_client(self, client: httpx.Client, payload: GeneratedArtifactIndexPayload) -> bool:
        try:
            kwargs = {
                "json": payload.model_dump(mode="json"),
            }
            headers = self._headers()
            if headers:
                kwargs["headers"] = headers
            response = client.post(
                self.settings.generated_artifact_index_url,
                **kwargs,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            if self.settings.generated_artifact_publish_fail_fast:
                raise GeneratedArtifactPublishError(f"Generated artifact publish failed: {exc}") from exc
            return False
        return True

    def _post_rag_add(self, payload: GeneratedArtifactIndexPayload, *, rag_add_url: str | None = None) -> bool:
        title = self._rag_add_title(payload)
        file_name = self._rag_add_file_name(payload)
        body = self._rag_add_text(payload, title=title)
        url = rag_add_url or self.settings.generated_artifact_add_url
        try:
            kwargs = {
                "files": {"file": (file_name, body.encode("utf-8"), "text/plain")},
                "data": {"title": title},
                "timeout": self.settings.generated_artifact_timeout_seconds,
            }
            headers = self._headers()
            if headers:
                kwargs["headers"] = headers
            response = httpx.post(
                url,
                **kwargs,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            if self.settings.generated_artifact_publish_fail_fast:
                raise GeneratedArtifactPublishError(f"Generated artifact /add publish failed: {exc}") from exc
            return False
        return True

    def _post_rag_add_with_client(
        self,
        client: httpx.Client,
        payload: GeneratedArtifactIndexPayload,
        *,
        rag_add_url: str | None = None,
    ) -> bool:
        title = self._rag_add_title(payload)
        file_name = self._rag_add_file_name(payload)
        body = self._rag_add_text(payload, title=title)
        url = rag_add_url or self.settings.generated_artifact_add_url
        try:
            kwargs = {
                "files": {"file": (file_name, body.encode("utf-8"), "text/plain")},
                "data": {"title": title},
            }
            headers = self._headers()
            if headers:
                kwargs["headers"] = headers
            response = client.post(
                url,
                **kwargs,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            if self.settings.generated_artifact_publish_fail_fast:
                raise GeneratedArtifactPublishError(f"Generated artifact /add publish failed: {exc}") from exc
            return False
        return True

    def _enabled(self) -> bool:
        return bool(
            self.settings.generated_artifact_publish_enabled
            and (self.settings.generated_artifact_index_url or self.settings.generated_artifact_add_url)
        )

    def _problem_publish_enabled(self) -> bool:
        return bool(self._enabled() or self._derived_problem_rag_add_url())

    def _rag_add_url_for_payload(self, payload: GeneratedArtifactIndexPayload) -> str | None:
        explicit_url = str(self.settings.generated_artifact_add_url or "").strip()
        if explicit_url:
            return explicit_url
        artifact_type = getattr(payload.artifact_type, "value", payload.artifact_type)
        if artifact_type == GeneratedArtifactType.problem.value:
            return self._derived_problem_rag_add_url()
        return None

    def _derived_problem_rag_add_url(self) -> str | None:
        if not self.settings.generated_problem_rag_upload_enabled:
            return None
        base_url = str(self.settings.rag_agent_url or "").strip().rstrip("/")
        if not base_url:
            return None
        path = str(self.settings.generated_problem_rag_add_path or "/add").strip() or "/add"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base_url}{path}"

    def _elapsed_ms(self, started: float) -> float:
        return max(0.0, (time.perf_counter() - started) * 1000)

    def _headers(self) -> dict[str, str]:
        api_key = str(self.settings.generated_artifact_api_key or "").strip()
        header_name = str(self.settings.generated_artifact_api_key_header or "").strip()
        if not api_key or not header_name:
            return {}
        return {header_name: api_key}

    def _rag_add_title(self, payload: GeneratedArtifactIndexPayload) -> str:
        prefix = str(self.settings.generated_artifact_add_title_prefix or "").strip() or "generated_artifact"
        title_parts = [
            prefix,
            payload.document_id.strip(),
            payload.artifact_type.value,
        ]
        return "__".join(part for part in title_parts if part).strip() or "generated_artifact"

    def _rag_add_file_name(self, payload: GeneratedArtifactIndexPayload) -> str:
        raw = f"{payload.artifact_type.value}_{payload.artifact_id}.txt"
        safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in raw)
        return safe[:128] or "generated_artifact.txt"

    def _rag_add_text(self, payload: GeneratedArtifactIndexPayload, *, title: str) -> str:
        metadata = {
            **payload.metadata,
            "artifact_id": payload.artifact_id,
            "artifact_type": payload.artifact_type.value,
            "user_id": payload.user_id,
            "document_id": payload.document_id,
            "visibility": payload.visibility.value,
            "source_chunk_ids": payload.source_chunk_ids,
        }
        lines = [
            "# Study Agent Generated Artifact",
            f"title: {title}",
            f"artifact_id: {payload.artifact_id}",
            f"artifact_type: {payload.artifact_type.value}",
            f"user_id: {payload.user_id}",
            f"document_id: {payload.document_id}",
            f"visibility: {payload.visibility.value}",
            "",
            "## Content",
            payload.content,
            "",
            "## Metadata",
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        ]
        return self._bounded_content("\n".join(lines), limit=INDEX_CONTENT_CHAR_LIMIT)

    def _choices_text(self, problem: Problem) -> str:
        choices = problem.choices or []
        if not choices:
            return ""
        lines = ["보기:"]
        for choice in choices:
            choice_id = str(choice.get("id") or "").strip()
            choice_text = str(choice.get("text") or "").strip()
            if choice_id and choice_text:
                lines.append(f"- {choice_id}. {choice_text}")
        return "\n".join(lines)

    def _recommended_review_text(self, recommended_review: list[str] | None) -> str:
        reviews = self._limited_texts(recommended_review)
        if not reviews:
            return ""
        return "복습 추천: " + ", ".join(reviews)

    def _concept_list_text(self, label: str, concepts: list[str]) -> str:
        values = self._limited_texts(concepts)
        if not values:
            return ""
        return f"{label}: " + ", ".join(values)

    def _limited_texts(self, values: list[str] | None, limit: int = INDEX_SUMMARY_LIST_LIMIT) -> list[str]:
        return [str(item).strip() for item in (values or []) if str(item).strip()][:limit]

    def _limited_mapping(self, values: dict[str, float], limit: int = INDEX_SUMMARY_LIST_LIMIT) -> dict[str, float]:
        return dict(list(values.items())[:limit])

    def _bounded_content(self, content: str, limit: int = INDEX_CONTENT_CHAR_LIMIT) -> str:
        text = str(content).strip()
        if len(text) <= limit:
            return text
        body_limit = max(0, limit - len(INDEX_TRUNCATION_MARKER))
        return text[:body_limit].rstrip() + INDEX_TRUNCATION_MARKER

    def _assessment_concept_summary(self, report: AssessmentSessionReportResponse) -> list[dict]:
        return [
            {
                "concept": item.concept,
                "status": item.status,
                "score_ratio": item.score_ratio,
                "submitted_count": item.submitted_count,
                "problem_count": item.problem_count,
            }
            for item in report.concept_results[:INDEX_SUMMARY_LIST_LIMIT]
        ]

    def _learning_content_index_text(self, content: LearningContentBase) -> str:
        payload = content.payload
        content_type = content.content_type
        lines = [f"학습 콘텐츠: {content_type.value}", f"개념: {', '.join(content.concepts)}"]
        if content_type == LearningContentType.flashcard:
            lines.extend([f"앞면: {payload.get('front', '')}", f"뒷면: {payload.get('back', '')}"])
        elif content_type == LearningContentType.concept_summary_card:
            lines.extend(
                [
                    f"제목: {payload.get('title', '')}",
                    f"요약: {payload.get('summary', '')}",
                    "핵심: " + ", ".join(payload.get("key_points") or []),
                ]
            )
        elif content_type == LearningContentType.worked_example:
            steps = payload.get("steps") or []
            step_text = " / ".join(str(step.get("text", "")) for step in steps if isinstance(step, dict))
            lines.extend(
                [
                    f"예제: {payload.get('problem', '')}",
                    f"풀이 흐름: {step_text}",
                    f"최종 답: {payload.get('final_answer', '')}",
                ]
            )
        elif content_type == LearningContentType.cloze:
            lines.append(f"빈칸: {payload.get('prompt', '')}")
        elif content_type == LearningContentType.true_false:
            lines.append(f"OX 문장: {payload.get('statement', '')}")
        elif content_type == LearningContentType.ordering:
            items = payload.get("items") or []
            item_text = " / ".join(str(item.get("text", "")) for item in items if isinstance(item, dict))
            lines.extend([f"순서 문제: {payload.get('prompt', '')}", f"항목: {item_text}"])
        elif content_type == LearningContentType.matching:
            pairs = payload.get("pairs") or []
            left_items = [str(pair.get("left", "")) for pair in pairs if isinstance(pair, dict)]
            right_items = [str(pair.get("right", "")) for pair in pairs if isinstance(pair, dict)]
            lines.extend(
                [
                    f"매칭 문제: {payload.get('prompt', '')}",
                    "왼쪽 항목: " + ", ".join(left_items),
                    "오른쪽 항목: " + ", ".join(right_items),
                ]
            )
        elif content_type == LearningContentType.mistake_drill:
            lines.extend(
                [
                    "오답 맞춤 연습",
                    "대상 개념: " + ", ".join(payload.get("target_concepts") or content.concepts),
                    f"오답 유형: {payload.get('target_mistake_type', '')}",
                ]
            )
        elif content_type == LearningContentType.mini_exam:
            lines.extend([f"미니 시험: {payload.get('title', '')}", f"문항 수: {len(payload.get('items') or [])}"])
        return "\n".join(line for line in lines if line and not line.endswith(": "))

    def _learning_content_has_hidden_payload(self, content: LearningContentBase) -> bool:
        return content.content_type in {
            LearningContentType.cloze,
            LearningContentType.true_false,
            LearningContentType.ordering,
            LearningContentType.matching,
        }
