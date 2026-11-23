from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MATERIALS_DIR = os.getenv("DOCUMENT_AGENT_MATERIALS_DIR", "../document_agent/generated_materials")
RAG_PROFILE_DIR = os.getenv("RAG_AGENT_USER_PROFILE_DIR", "../rag_agent/user_profiles")


@dataclass
class CollectedData:
    document: dict = field(default_factory=dict)        # title, subject, goal, deadline, progress
    sections: list[dict] = field(default_factory=list)  # order_index, title, intent, focus, flashcards, id
    quiz_attempts: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    concept_cards: list[dict] = field(default_factory=list)   # concept, answer_hint, answer, difficulty, section_title
    section_summaries: list[dict] = field(default_factory=list)  # section_title, focus, intent
    query_history: list[dict] = field(default_factory=list)
    exec_summary: dict = field(default_factory=dict)    # key_topics, learning_objectives, conceptual_flow
    learning_flow: list[dict] = field(default_factory=list)  # step, title, intent, focus


class DataCollector:
    def __init__(self):
        self._supabase = self._init_supabase()

    def _init_supabase(self):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            logger.warning("SUPABASE_URL/SUPABASE_SERVICE_KEY 미설정 — 로컬 파일만 사용")
            return None
        try:
            from supabase import create_client
            return create_client(url, key)
        except Exception as e:
            logger.warning(f"Supabase 초기화 실패: {e}")
            return None

    async def collect(self, user_id: str, doc_id: str) -> CollectedData:
        data = CollectedData()

        if self._supabase:
            # Supabase 동기 I/O를 스레드 풀로 분리해 event loop 블로킹 방지
            results = await asyncio.gather(
                asyncio.to_thread(self._fetch_document, doc_id),
                asyncio.to_thread(self._fetch_sections, doc_id),
                asyncio.to_thread(self._fetch_quiz_attempts, user_id, doc_id),
                asyncio.to_thread(self._fetch_questions, user_id, doc_id),
            )
            data.document, data.sections, data.quiz_attempts, data.questions = results
        else:
            logger.warning("Supabase 없이 로컬 파일만 사용합니다")

        # document_agent material.json — 주 데이터 소스
        material = self._load_material_json(doc_id)
        data.exec_summary = material.get("exec_summary", {})
        data.learning_flow = material.get("learning_flow", [])
        data.concept_cards = self._extract_concept_cards(material)
        data.section_summaries = self._extract_section_summaries(material)

        # Supabase sections가 없으면 material.json으로 대체 (intent/focus/flashcards 포함)
        if not data.sections and material:
            data.sections = self._sections_from_material(material)

        # Supabase document 메타데이터가 없으면 material.json으로 채움
        if not data.document and material:
            data.document = self._document_from_material(material, doc_id)

        data.query_history = self._load_query_history(user_id)
        return data

    # ── Supabase 조회 (동기, to_thread로 실행) ──────────────────────────

    def _fetch_document(self, doc_id: str) -> dict:
        try:
            resp = (
                self._supabase.table("documents")
                .select("id,title,subject,goal,deadline,progress,status")
                .eq("id", doc_id)
                .single()
                .execute()
            )
            return resp.data or {}
        except Exception as e:
            logger.error(f"documents 조회 실패: {e}")
            return {}

    def _fetch_sections(self, doc_id: str) -> list[dict]:
        try:
            resp = (
                self._supabase.table("document_sections")
                .select("id,order_index,title,keywords,summary")
                .eq("document_id", doc_id)
                .order("order_index")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"document_sections 조회 실패: {e}")
            return []

    def _fetch_quiz_attempts(self, user_id: str, doc_id: str) -> list[dict]:
        try:
            resp = (
                self._supabase.table("quiz_attempts")
                .select("id,is_correct,weak_concepts,created_at")
                .eq("user_id", user_id)
                .eq("document_id", doc_id)
                .order("created_at")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"quiz_attempts 조회 실패: {e}")
            return []

    def _fetch_questions(self, user_id: str, doc_id: str) -> list[dict]:
        try:
            resp = (
                self._supabase.table("questions")
                .select("id,question,created_at")
                .eq("user_id", user_id)
                .eq("document_id", doc_id)
                .order("created_at")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"questions 조회 실패: {e}")
            return []

    # ── 로컬 파일 로드 ──────────────────────────────────────────────────

    def _load_material_json(self, doc_id: str) -> dict:
        """document_agent가 생성한 material.json을 읽는다."""
        path = Path(MATERIALS_DIR) / doc_id / "material.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"material.json 로드 실패 ({doc_id}): {e}")
            return {}

    def _extract_concept_cards(self, material: dict) -> list[dict]:
        """sections[].flashcards → concept_cards 형식 변환 (hint용 answer_hint/answer 포함)"""
        cards = []
        for section in material.get("sections", []):
            intent = section.get("intent", "definition")
            difficulty = "높음" if "exercise" in intent else "보통"
            for fc in section.get("flashcards", []):
                q = fc.get("question", "")
                if q:
                    cards.append({
                        "concept": q,
                        "section_title": section.get("title", ""),
                        "answer_hint": fc.get("answer_hint", ""),
                        "answer": fc.get("answer", ""),
                        "difficulty": difficulty,
                    })
        return cards

    def _extract_section_summaries(self, material: dict) -> list[dict]:
        """sections[] → section_summaries 형식 변환"""
        return [
            {
                "section_title": s.get("title", ""),
                "focus": s.get("focus", ""),
                "intent": s.get("intent", "definition"),
                "key_concepts": [],
            }
            for s in material.get("sections", [])
        ]

    def _sections_from_material(self, material: dict) -> list[dict]:
        """Supabase 없을 때 material.json sections로 대체 (intent/focus/flashcards 포함)."""
        return [
            {
                "id": f"local_{i}",
                "order_index": i,
                "title": s.get("title", ""),
                "intent": s.get("intent", "definition"),
                "focus": s.get("focus", ""),
                "flashcards": s.get("flashcards", []),
                "keywords": [],
            }
            for i, s in enumerate(material.get("sections", []))
        ]

    def _document_from_material(self, material: dict, doc_id: str) -> dict:
        """Supabase document 테이블 부재 시 material.json으로 문서 메타데이터를 구성한다."""
        exec_summary = material.get("exec_summary", {})
        objectives = exec_summary.get("learning_objectives", [])
        goal = objectives[0] if objectives else ""
        return {
            "id": doc_id,
            "title": material.get("title", doc_id),
            "subject": "",
            "goal": goal,
            "deadline": None,
            "progress": 0,
            "status": "active",
        }

    def _load_query_history(self, user_id: str) -> list[dict]:
        path = Path(RAG_PROFILE_DIR) / f"{user_id}.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                profile = json.load(f)
            return profile.get("queries", [])
        except Exception as e:
            logger.warning(f"rag 사용자 프로필 로드 실패 ({user_id}): {e}")
            return []
