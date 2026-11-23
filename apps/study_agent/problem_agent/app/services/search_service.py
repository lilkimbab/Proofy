from __future__ import annotations

import hashlib
import json

import httpx

from app.config import Settings, get_settings
from app.schemas.integration_contracts import ChunkBatchRequest, RetrievedChunk, SearchChunksRequest


class SearchAgentError(RuntimeError):
    """Raised when the external Search Agent is unavailable or invalid."""


_RAG_CHUNK_CACHE: dict[str, RetrievedChunk] = {}


class SearchService:
    """Client for the team-owned Search Agent.

    The actual vector search lives outside this module. This service only
    defines the contract expected by Problem/Feedback services.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._demo_chunks = [
            RetrievedChunk(
                chunk_id="demo_chunk_001",
                document_id="demo_doc",
                content=(
                    "뉴턴의 제2법칙은 F = ma로 표현된다. 같은 힘이 작용할 때 질량이 클수록 "
                    "가속도는 작아지고, 가속도는 힘에 비례하며 질량에 반비례한다."
                ),
                page=1,
                section_title="뉴턴의 운동 법칙",
                concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
                tags=["science", "formula", "concept_relation"],
                metadata={"subject_domain": "science", "content_forms": ["formula", "concept_relation"]},
            )
        ]

    def search_chunks(
        self,
        *,
        document_id: str,
        concepts: list[str],
        difficulty: str,
        query: str,
        top_k: int = 6,
        include_images: bool = False,
    ) -> list[RetrievedChunk]:
        if self.settings.demo_search_enabled:
            return self._demo_chunks_for_request(document_id=document_id, concepts=concepts)[:top_k]
        if self.settings.rag_agent_url:
            return self._search_rag_agent(
                document_id=document_id,
                concepts=concepts,
                query=query,
                top_k=top_k,
                include_images=include_images,
            )
        if not self.settings.search_agent_url:
            raise SearchAgentError("SEARCH_AGENT_URL or RAG_AGENT_URL is not configured")

        request = SearchChunksRequest(
            document_id=document_id,
            concepts=concepts,
            difficulty=difficulty,
            query=query,
            top_k=top_k,
        )
        try:
            response = self._post_json(
                f"{self.settings.search_agent_url.rstrip('/')}/search",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            chunks = [RetrievedChunk.model_validate(item) for item in response.json()]
            return self._dedupe_and_validate_search_chunks(
                document_id=document_id,
                chunks=chunks,
                source_label="Search Agent /search",
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchAgentError(f"Search Agent /search failed: {exc}") from exc

    def get_chunks_by_ids(self, *, document_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        if self.settings.demo_search_enabled:
            demo_chunks = self._demo_chunks_for_request(document_id=document_id, concepts=[])
            return [chunk for chunk in demo_chunks if chunk.chunk_id in chunk_ids]
        if self.settings.rag_agent_url:
            if self.settings.rag_agent_chunks_path:
                return self._get_rag_chunks_by_ids(document_id=document_id, chunk_ids=chunk_ids)
            if self.settings.rag_agent_fetch_path:
                return self._fetch_rag_chunks_by_ids(document_id=document_id, chunk_ids=chunk_ids)
            return self._get_cached_rag_chunks(document_id=document_id, chunk_ids=chunk_ids)
        if not self.settings.search_agent_url:
            raise SearchAgentError("SEARCH_AGENT_URL or RAG_AGENT_URL is not configured")

        request = ChunkBatchRequest(document_id=document_id, chunk_ids=chunk_ids)
        try:
            response = self._post_json(
                f"{self.settings.search_agent_url.rstrip('/')}/chunks/batch",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            chunks = [RetrievedChunk.model_validate(item) for item in response.json()]
            return self._validate_and_order_chunk_batch(
                document_id=document_id,
                chunk_ids=chunk_ids,
                chunks=chunks,
                source_label="Search Agent /chunks/batch",
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchAgentError(f"Search Agent /chunks/batch failed: {exc}") from exc

    def _demo_chunks_for_request(self, *, document_id: str, concepts: list[str]) -> list[RetrievedChunk]:
        requested_concepts = concepts or self._demo_chunks[0].concepts
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=document_id,
                content=chunk.content,
                page=chunk.page,
                section_title=chunk.section_title,
                concepts=requested_concepts,
                tags=chunk.tags,
                metadata=chunk.metadata,
            )
            for chunk in self._demo_chunks
        ]

    def _search_rag_agent(
        self,
        *,
        document_id: str,
        concepts: list[str],
        query: str,
        top_k: int,
        include_images: bool,
    ) -> list[RetrievedChunk]:
        request = {
            "query": query,
            "title": document_id,
            "top_k": top_k,
            "filter": None,
        }
        try:
            response = self._post_json(
                self._rag_url(self.settings.rag_agent_search_path),
                json=request,
                include_images=include_images,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SearchAgentError(f"RAG Agent /search failed: {exc}") from exc

        results = self._extract_rag_results(payload)
        chunks: list[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()
        for result in results:
            chunk = self._rag_result_to_chunk(
                document_id=document_id,
                concepts=concepts,
                result=result,
                include_images=include_images,
            )
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            chunks.append(chunk)
            if len(chunks) >= top_k:
                break
        if not chunks:
            raise SearchAgentError("RAG Agent /search returned no usable chunks")
        for chunk in chunks:
            _RAG_CHUNK_CACHE[chunk.chunk_id] = chunk
        return chunks

    def _extract_rag_results(self, payload: object) -> list[dict]:
        if isinstance(payload, list):
            results = payload
        elif isinstance(payload, dict):
            results = None
            for key in ["results", "documents", "chunks", "items", "data", "matches", "contexts", "nodes"]:
                value = payload.get(key)
                if isinstance(value, list):
                    results = value
                    break
            if results is None:
                raise SearchAgentError("RAG Agent /search response must include a result list")
        else:
            raise SearchAgentError("RAG Agent /search response must be a JSON object or list")

        if not results:
            raise SearchAgentError("RAG Agent /search returned no results")
        invalid_indexes = [index for index, item in enumerate(results) if not isinstance(item, dict)]
        if invalid_indexes:
            raise SearchAgentError(f"RAG Agent /search returned non-object results: {invalid_indexes}")
        return results

    def _get_rag_chunks_by_ids(self, *, document_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        request = {
            "document_id": document_id,
            "title": document_id,
            "chunk_ids": chunk_ids,
        }
        try:
            response = self._post_json(
                self._rag_url(self.settings.rag_agent_chunks_path or ""),
                json=request,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SearchAgentError(f"RAG Agent chunk batch failed: {exc}") from exc

        chunks = [
            self._rag_result_to_chunk(document_id=document_id, concepts=[], result=result)
            for result in self._extract_rag_results(payload)
        ]
        ordered_chunks = self._validate_and_order_chunk_batch(
            document_id=document_id,
            chunk_ids=chunk_ids,
            chunks=chunks,
            source_label="RAG Agent chunk batch",
        )
        for chunk in ordered_chunks:
            _RAG_CHUNK_CACHE[chunk.chunk_id] = chunk
        return ordered_chunks

    def _fetch_rag_chunks_by_ids(self, *, document_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        request = {
            "title": document_id,
            "filter": {
                "id": chunk_ids if len(chunk_ids) > 1 else chunk_ids[0],
            },
            "limit": len(chunk_ids),
        }
        try:
            response = self._post_json(
                self._rag_url(self.settings.rag_agent_fetch_path or ""),
                json=request,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SearchAgentError(f"RAG Agent /fetch failed: {exc}") from exc

        chunks = [
            self._rag_result_to_chunk(document_id=document_id, concepts=[], result=result)
            for result in self._extract_rag_results(payload)
        ]
        ordered_chunks = self._validate_and_order_chunk_batch(
            document_id=document_id,
            chunk_ids=chunk_ids,
            chunks=chunks,
            source_label="RAG Agent /fetch",
        )
        for chunk in ordered_chunks:
            _RAG_CHUNK_CACHE[chunk.chunk_id] = chunk
        return ordered_chunks

    def _get_cached_rag_chunks(self, *, document_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        missing_chunk_ids: list[str] = []
        wrong_document_ids: list[str] = []
        for chunk_id in chunk_ids:
            chunk = _RAG_CHUNK_CACHE.get(chunk_id)
            if chunk is None:
                missing_chunk_ids.append(chunk_id)
                continue
            if chunk.document_id != document_id:
                wrong_document_ids.append(chunk_id)
                continue
            chunks.append(chunk)
        if missing_chunk_ids:
            missing = ", ".join(missing_chunk_ids)
            raise SearchAgentError(
                "RAG Agent adapter cannot resolve uncached chunk ids. "
                f"Missing chunk ids: {missing}"
            )
        if wrong_document_ids:
            wrong = ", ".join(wrong_document_ids)
            raise SearchAgentError(f"RAG Agent adapter returned chunks from a different document: {wrong}")
        return chunks

    def _validate_and_order_chunk_batch(
        self,
        *,
        document_id: str,
        chunk_ids: list[str],
        chunks: list[RetrievedChunk],
        source_label: str,
    ) -> list[RetrievedChunk]:
        returned_chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(returned_chunk_ids)) != len(returned_chunk_ids):
            raise SearchAgentError(f"{source_label} returned duplicate chunks")

        unexpected_ids = [chunk_id for chunk_id in returned_chunk_ids if chunk_id not in chunk_ids]
        if unexpected_ids:
            raise SearchAgentError(f"{source_label} returned unexpected chunks: {', '.join(unexpected_ids)}")

        returned_ids = set(returned_chunk_ids)
        missing_ids = [chunk_id for chunk_id in chunk_ids if chunk_id not in returned_ids]
        if missing_ids:
            raise SearchAgentError(f"{source_label} did not return chunks: {', '.join(missing_ids)}")

        wrong_document_ids = [
            chunk.chunk_id
            for chunk in chunks
            if chunk.chunk_id in chunk_ids and chunk.document_id != document_id
        ]
        if wrong_document_ids:
            wrong = ", ".join(wrong_document_ids)
            raise SearchAgentError(f"{source_label} returned chunks from a different document: {wrong}")

        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        return [chunk_by_id[chunk_id] for chunk_id in chunk_ids]

    def _dedupe_and_validate_search_chunks(
        self,
        *,
        document_id: str,
        chunks: list[RetrievedChunk],
        source_label: str,
    ) -> list[RetrievedChunk]:
        wrong_document_ids = [chunk.chunk_id for chunk in chunks if chunk.document_id != document_id]
        if wrong_document_ids:
            wrong = ", ".join(wrong_document_ids)
            raise SearchAgentError(f"{source_label} returned chunks from a different document: {wrong}")

        deduped_chunks: list[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            deduped_chunks.append(chunk)
        return deduped_chunks

    def _rag_result_to_chunk(
        self,
        *,
        document_id: str,
        concepts: list[str],
        result: dict,
        include_images: bool = False,
    ) -> RetrievedChunk:
        metadata = dict(result.get("metadata") if isinstance(result.get("metadata"), dict) else {})
        result_document_id = self._first_text(
            result,
            ["document_id", "doc_id", "title"],
            metadata=metadata,
            metadata_keys=["document_id", "doc_id", "title"],
        )
        if result_document_id and result_document_id != document_id:
            raise SearchAgentError(
                f"RAG Agent returned a chunk from a different document: {result_document_id}"
            )

        content = self._first_text(
            result,
            ["parent_text", "text", "content", "page_content", "document", "body"],
            metadata=metadata,
            metadata_keys=["parent_text", "text", "content", "page_content"],
        )
        if not content:
            raise SearchAgentError("RAG Agent result is missing text/content")
        child_text = self._first_text(
            result,
            ["text", "content", "page_content", "document", "body"],
            metadata=metadata,
            metadata_keys=["text", "content", "page_content"],
        )
        if child_text and child_text != content and "rag_child_text" not in metadata:
            metadata["rag_child_text"] = child_text

        source = self._first_text(
            result,
            ["source", "section_title", "section", "file_name", "filename"],
            metadata=metadata,
            metadata_keys=["source", "section_title", "section", "file_name", "filename"],
        )
        page = self._page_value(result, metadata=metadata)
        chunk_id = self._first_text(
            result,
            ["chunk_id", "id", "node_id"],
            metadata=metadata,
            metadata_keys=["chunk_id", "id", "node_id"],
        ) or self._make_rag_chunk_id(
            document_id=document_id,
            source=source or "",
            page=page,
            content=content,
        )
        chunk_concepts = self._concepts_value(result, metadata=metadata) or concepts
        self._copy_rag_result_metadata(
            result=result,
            metadata=metadata,
            source=source,
            page=page,
            include_images=include_images,
        )
        return RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            content=content,
            page=page,
            section_title=source or None,
            concepts=chunk_concepts,
            tags=self._tags_value(result, metadata=metadata),
            metadata=metadata,
        )

    def _copy_rag_result_metadata(
        self,
        *,
        result: dict,
        metadata: dict,
        source: str,
        page: int | None,
        include_images: bool,
    ) -> None:
        for key in ["score", "distance", "file_name", "filename"]:
            value = result.get(key)
            if value is not None and key not in metadata:
                metadata[key] = value
        if source and "source" not in metadata:
            metadata["source"] = source
        if page is not None and "page" not in metadata:
            metadata["page"] = page

        image_payload = result.get("image")
        if image_payload:
            metadata["image_available"] = True
            if include_images or (
                not self.settings.rag_agent_text_only
                and self.settings.rag_agent_preserve_image_payloads
            ):
                metadata["image"] = image_payload
            else:
                metadata["image_omitted"] = "text_only"
        elif "image" in result:
            metadata["image_available"] = False

    def _first_text(
        self,
        result: dict,
        keys: list[str],
        *,
        metadata: dict,
        metadata_keys: list[str],
    ) -> str:
        for key in keys:
            text = self._text_value(result.get(key), nested_keys=keys)
            if text:
                return text
        for key in metadata_keys:
            text = self._text_value(metadata.get(key), nested_keys=metadata_keys)
            if text:
                return text
        return ""

    def _text_value(self, value: object, *, nested_keys: list[str]) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, int | float):
            return str(value).strip()
        if isinstance(value, dict):
            fallback_keys = ["parent_text", "text", "content", "page_content", "body", "document", "source", "title"]
            for key in [*nested_keys, *fallback_keys]:
                if key not in value:
                    continue
                text = self._text_value(value.get(key), nested_keys=fallback_keys)
                if text:
                    return text
        return ""

    def _page_value(self, result: dict, *, metadata: dict) -> int | None:
        for source in [result, metadata]:
            for key in ["page", "page_number", "page_num"]:
                value = source.get(key)
                if value is None or value == "":
                    continue
                try:
                    return int(value)
                except (TypeError, ValueError):
                    raise SearchAgentError(f"RAG Agent result has invalid page value: {value}") from None
        return None

    def _concepts_value(self, result: dict, *, metadata: dict) -> list[str]:
        for source in [result, metadata]:
            value = source.get("concepts")
            if isinstance(value, list):
                concepts = [str(item).strip() for item in value if str(item).strip()]
                if concepts:
                    return list(dict.fromkeys(concepts))
            if isinstance(value, str) and value.strip():
                return [value.strip()]
        return []

    def _tags_value(self, result: dict, *, metadata: dict) -> list[str]:
        tags: list[str] = []
        for source in [result, metadata]:
            for key in [
                "tags",
                "tag",
                "content_tags",
                "learning_tags",
                "content_forms",
                "content_form",
                "subject_domain",
                "subject",
            ]:
                value = source.get(key)
                if isinstance(value, list):
                    tags.extend(str(item).strip() for item in value if str(item).strip())
                elif isinstance(value, str) and value.strip():
                    tags.extend(part.strip() for part in value.replace(";", ",").split(",") if part.strip())
        return list(dict.fromkeys(tags))

    def _make_rag_chunk_id(self, *, document_id: str, source: str, page: int | None, content: str) -> str:
        raw = json.dumps(
            {
                "document_id": document_id,
                "source": source,
                "page": page,
                "content": content,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"rag_{digest}"

    def _rag_url(self, path: str) -> str:
        base_url = (self.settings.rag_agent_url or "").rstrip("/")
        normalized_path = f"/{path.strip('/')}" if path else ""
        return f"{base_url}{normalized_path}"

    def _post_json(self, url: str, *, json: dict, include_images: bool = False) -> httpx.Response:
        kwargs = {"json": json, "timeout": self.settings.search_agent_timeout_seconds}
        headers = self._headers(include_images=include_images)
        if headers:
            kwargs["headers"] = headers
        return httpx.post(url, **kwargs)

    def _headers(self, *, include_images: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        api_key = str(self.settings.search_agent_api_key or "").strip()
        header_name = str(self.settings.search_agent_api_key_header or "").strip()
        if api_key and header_name:
            headers[header_name] = api_key
        if self.settings.rag_agent_url and self.settings.rag_agent_text_only and not include_images:
            headers["X-RAG-Text-Only"] = "true"
        if self.settings.rag_agent_url and self.settings.rag_agent_skip_ngrok_warning:
            headers["ngrok-skip-browser-warning"] = "true"
        return headers
