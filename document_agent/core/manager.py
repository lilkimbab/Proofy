import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from core.llm_client import LLMClient
from core import rag_client, planner, creator, validator, assembler, summarizer, grounding, flashcard_gen, corrector

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
MATERIALS_DIR = os.getenv("MATERIALS_DIR") or os.path.join(_HERE, "..", "generated_materials")

_SECTION_CONCURRENCY = int(os.getenv("SECTION_CONCURRENCY", "3"))


def _has_body(section_text: str) -> bool:
    """H2 heading 이외에 80자 이상의 실제 본문이 있는지 확인."""
    non_heading = [
        l for l in section_text.strip().splitlines()
        if l.strip() and not l.startswith('#')
    ]
    return sum(len(l) for l in non_heading) >= 80


def _make_id(seed: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return hashlib.sha256(f"{seed}{ts}".encode()).hexdigest()[:16]


def _make_doc_id(title: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    short_hash = hashlib.sha256(f"{title}{ts}".encode()).hexdigest()[:8]
    safe = re.sub(r'[^\w]', '_', title, flags=re.UNICODE)
    safe = re.sub(r'_+', '_', safe).strip('_')[:24]
    return f"{safe}_{short_hash}" if safe else short_hash


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StudyManager:
    def __init__(self):
        self._llm = LLMClient()
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        os.makedirs(MATERIALS_DIR, exist_ok=True)

    async def submit_upload(self, file_path: str, title: str) -> tuple[str, str, str]:
        doc_id = _make_doc_id(title)
        task_id = _make_id(doc_id)
        task = {
            "task_id": task_id,
            "doc_id": doc_id,
            "status": "UPLOADING",
            "progress": 0.05,
            "message": "파일 업로드 중...",
            "error": None,
            "created_at": _now_iso(),
            "completed_at": None,
        }
        with self._lock:
            self._tasks[task_id] = task

        doc_dir = os.path.join(MATERIALS_DIR, doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        source_ext = os.path.splitext(file_path)[1] or ".pdf"
        source_path = os.path.join(doc_dir, f"source{source_ext}")
        shutil.copy2(file_path, source_path)

        try:
            add_result = await rag_client.add(file_path, title)
        except Exception as e:
            self._update(task_id, status="FAILED", message="업로드 실패", error=str(e))
            raise RuntimeError(f"업로드 실패: {e}")
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass

        parents = add_result.get("parents", [])
        job_id = add_result.get("job_id", "")

        if not parents:
            self._update(task_id, status="FAILED", message="파싱 결과 없음", error="업로드 응답에 parents가 없습니다")
            raise RuntimeError("업로드 응답에 parents가 없습니다")

        asyncio.ensure_future(self._run_upload_pipeline(task_id, doc_id, parents, title))
        return task_id, doc_id, job_id

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_material(self, doc_id: str) -> dict | None:
        path = os.path.join(MATERIALS_DIR, doc_id, "material.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _update(self, task_id: str, **kwargs):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kwargs)

    async def _enrich_section(
        self,
        section_text: str,
        chunks: list[dict],
        intent: str,
    ) -> tuple[list[str], list[dict]]:
        if "exercise" in intent:
            flashcards = await flashcard_gen.generate_flashcards(self._llm, section_text, intent)
            return [], flashcards
        grounding_issues, flashcards = await asyncio.gather(
            grounding.check_grounding(self._llm, section_text, chunks),
            flashcard_gen.generate_flashcards(self._llm, section_text, intent),
        )
        return grounding_issues, flashcards

    async def _correct_if_needed(
        self,
        section_text: str,
        grounding_issues: list[str],
        chunks: list[dict],
    ) -> tuple[str, list[str]]:
        if not grounding_issues:
            return section_text, grounding_issues
        corrected = await corrector.correct_section(self._llm, section_text, grounding_issues, chunks)
        remaining = await grounding.check_grounding(self._llm, corrected, chunks)
        return corrected, remaining

    @staticmethod
    def _ensure_full_coverage(sections: list[dict], parents: list[dict]) -> list[dict]:
        covered = {pid for s in sections for pid in s.get("target_parent_ids", [])}
        uncovered_ids = [p["parent_id"] for p in parents if p["parent_id"] not in covered]
        if not uncovered_ids:
            return sections
        logger.warning(f"complete 모드: {len(uncovered_ids)}개 parent 누락 → 5개씩 나눠 섹션 추가")
        group_size = 5
        for i in range(0, len(uncovered_ids), group_size):
            group = uncovered_ids[i : i + group_size]
            sections.append({
                "title": f"추가 내용 {i // group_size + 1}",
                "intent": "definition",
                "target_parent_ids": group,
                "focus": "앞선 섹션에서 다루지 못한 내용을 보완합니다",
            })
        return sections

    async def _process_one_section(
        self,
        section: dict,
        parent_map: dict,
        img_dir: str,
    ) -> dict | None:
        target_ids = section.get("target_parent_ids", [])
        chunks = [
            {
                "text": parent_map[pid]["text"],
                "source": parent_map[pid]["file_name"],
                "page": parent_map[pid].get("page_start", 0) + 1,
                "id": pid,
                "image": parent_map[pid].get("image"),
            }
            for pid in target_ids if pid in parent_map
        ]
        if not chunks:
            logger.warning(f"섹션 '{section['title']}'에 해당하는 parents 없음")
            return None

        # 섹션당 page 중복 제거 후 첫 이미지 1개만 사용
        image_map_local: dict = {}
        seen_pages: set = set()
        image_chunks = []
        for c in chunks:
            if c.get("image") and c.get("page") not in seen_pages:
                seen_pages.add(c.get("page"))
                image_chunks.append(c)
        image_chunks = image_chunks[:1]

        for c in image_chunks:
            cid = c["id"]
            entry: dict = {"source": c.get("source", ""), "page": c.get("page", 0), "has_image": False}
            image_map_local[cid] = entry
            raw = c.get("image", "")
            if raw:
                try:
                    data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
                    os.makedirs(img_dir, exist_ok=True)
                    with open(os.path.join(img_dir, f"{cid}.png"), "wb") as f:
                        f.write(base64.b64decode(data))
                    entry["has_image"] = True
                except Exception as e:
                    logger.warning(f"이미지 저장 실패 {cid}: {e}")

        source_entries = [
            {"file": c["source"], "page": c["page"], "chunk_id": c["id"]}
            for c in chunks
        ]

        section_text = await creator.create_section(
            self._llm, section, chunks, image_chunks, complete_mode=True,
        )

        warnings: list[str] = []
        vresult = validator.validate_section(section_text, chunks)
        if vresult["coverage"] < 0.2:
            section_text = await creator.create_section(
                self._llm, section, chunks, image_chunks,
                extra_keywords=vresult["missing_keywords"],
                complete_mode=True,
            )
            if validator.validate_section(section_text, chunks)["coverage"] < 0.2:
                warnings.append(f"'{section['title']}' 섹션의 키워드 커버리지가 낮습니다")
        elif vresult["coverage"] < 0.4:
            warnings.append(f"'{section['title']}' 섹션의 키워드 커버리지가 낮습니다")

        # heading만 남은 경우: 이미지 전용 페이지 등으로 텍스트 추출 실패
        if not _has_body(section_text):
            pages = sorted({c["page"] for c in chunks})
            page_str = ", ".join(f"p.{p}" for p in pages)
            section_text = (
                f"## {section['title']}\n\n"
                f"> ⚠️ 해당 페이지({page_str})의 내용은 대부분 이미지로 구성되어 있어 "
                f"텍스트 추출이 어렵습니다. 원본 PDF의 해당 페이지를 직접 확인해 주세요.\n"
            )
            warnings.append(f"'{section['title']}' 섹션: 이미지 전용 페이지로 텍스트 생성 실패 ({page_str})")
            return {
                "section_text": section_text,
                "section_data": {
                    "title": section["title"],
                    "intent": section.get("intent", "definition"),
                    "content": section_text,
                    "focus": section.get("focus", ""),
                    "source_chunks": [
                        {"chunk_id": c["id"], "text": c["text"], "file": c["source"], "page": c["page"]}
                        for c in chunks
                    ],
                    "grounding_issues": [],
                    "flashcards": [],
                },
                "image_map_entries": image_map_local,
                "source_entries": source_entries,
                "warnings": warnings,
            }

        intent = section.get("intent", "definition")
        grounding_issues, flashcards = await self._enrich_section(section_text, chunks, intent)
        if grounding_issues:
            section_text, grounding_issues = await self._correct_if_needed(
                section_text, grounding_issues, chunks
            )
            flashcards = await flashcard_gen.generate_flashcards(self._llm, section_text, intent)
        if grounding_issues:
            warnings.append(f"'{section['title']}' 섹션에 원본 미확인 내용이 있습니다 ({len(grounding_issues)}건)")

        return {
            "section_text": section_text,
            "section_data": {
                "title": section["title"],
                "intent": intent,
                "content": section_text,  # replace_image_tags applied after full image_map is built
                "focus": section.get("focus", ""),
                "source_chunks": [
                    {"chunk_id": c["id"], "text": c["text"], "file": c["source"], "page": c["page"]}
                    for c in chunks
                ],
                "grounding_issues": grounding_issues,
                "flashcards": flashcards,
            },
            "image_map_entries": image_map_local,
            "source_entries": source_entries,
            "warnings": warnings,
        }

    async def _run_upload_pipeline(
        self, task_id: str, doc_id: str, parents: list[dict], title: str
    ):
        try:
            self._update(task_id, status="SUMMARIZING", progress=0.15, message="섹션 요약 중...")
            summaries = await summarizer.summarize_parents(self._llm, parents)
            planner_input = summarizer.build_planner_input(summaries)

            self._update(task_id, status="SUMMARIZING", progress=0.35, message="Executive Summary 생성 중...")
            exec_summary = await summarizer.generate_executive_summary(self._llm, summaries)

            self._update(task_id, status="PLANNING", progress=0.45, message="전체 커버리지 목차 구성 중...")
            sections = await planner.plan_sections_complete(
                self._llm, planner_input, parents,
                conceptual_flow=exec_summary.get("conceptual_flow", ""),
            )
            sections = self._ensure_full_coverage(sections, parents)

            doc_dir = os.path.join(MATERIALS_DIR, doc_id)
            os.makedirs(doc_dir, exist_ok=True)
            img_dir = os.path.join(doc_dir, "images")
            parent_map = {p["parent_id"]: p for p in parents}

            self._update(task_id, status="GENERATING", progress=0.5, message="자료 생성 중...")
            total = len(sections)
            completed = [0]
            sem = asyncio.Semaphore(_SECTION_CONCURRENCY)

            async def _bounded(section: dict) -> dict | None:
                async with sem:
                    result = await self._process_one_section(section, parent_map, img_dir)
                    completed[0] += 1
                    progress = 0.5 + (completed[0] / total) * 0.4
                    self._update(
                        task_id,
                        progress=round(progress, 3),
                        message=f"생성 중: {completed[0]}/{total} 섹션",
                    )
                    return result

            raw_results = await asyncio.gather(*[_bounded(s) for s in sections])
            results = [r for r in raw_results if r is not None]

            if not results:
                raise RuntimeError("생성된 섹션이 없습니다")

            # Aggregate in original section order (asyncio.gather preserves order)
            sections_md = [r["section_text"] for r in results]
            sections_data = [r["section_data"] for r in results]
            image_map: dict = {}
            sources: list[dict] = []
            warnings: list[str] = []
            seen_ids: set = set()

            for r in results:
                image_map.update(r["image_map_entries"])
                warnings.extend(r["warnings"])
                for src in r["source_entries"]:
                    if src["chunk_id"] not in seen_ids:
                        seen_ids.add(src["chunk_id"])
                        sources.append(src)

            # Resolve [IMAGE: ...] tags now that full image_map is available
            for sd in sections_data:
                sd["content"] = assembler.replace_image_tags(sd["content"], image_map)

            self._update(task_id, status="ASSEMBLING", progress=0.9, message="문서 조립 중...")
            body = assembler.assemble(sections_md, image_map, sources)
            header = (
                f"# {title}\n\n"
                f"> **학습 목표:** 이 자료를 통해 '{title}'에 대한 개념, 예시, 확인 문제를 학습합니다.\n\n"
                f"---\n\n"
            )
            document = header + body

            learning_flow = [
                {"step": i + 1, "title": s["title"], "intent": s["intent"], "focus": s.get("focus", "")}
                for i, s in enumerate(sections_data)
            ]

            material = {
                "doc_id": doc_id,
                "query": title,
                "title": title,
                "mode": "complete",
                "document": document,
                "exec_summary": exec_summary,
                "learning_flow": learning_flow,
                "sections": sections_data,
                "sources": sources,
                "image_map": image_map,
                "warnings": warnings,
                "generated_at": _now_iso(),
            }
            with open(os.path.join(doc_dir, "material.json"), "w", encoding="utf-8") as f:
                json.dump(material, f, ensure_ascii=False, indent=2)

            self._update(task_id, status="DONE", progress=1.0, message="완료", completed_at=_now_iso())
            logger.info(f"[{task_id}] 업로드 파이프라인 완료: doc_id={doc_id}")

        except Exception as e:
            logger.exception(f"[{task_id}] 업로드 파이프라인 오류: {e}")
            self._update(task_id, status="FAILED", message="처리 중 오류가 발생했습니다", error=str(e))
