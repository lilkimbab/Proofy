from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request

from app.core.config import settings


SYSTEM_PROMPT = """당신은 한국 수능 수학 콘텐츠 디자이너입니다.
출력은 반드시 JSON이어야 하며, 이미 운영 중인 콘텐츠 저장소에 바로 넣을 수 있어야 합니다.
문항은 수능/N수생 관점에서 개념, 실수 포인트, 풀이 흐름, 오개념 교정 포인트가 명확해야 합니다.
강의 scene은 칠판 강의형 구조로 작성하고, 각 scene에는 narration과 objects를 포함하세요.
문제는 functionSpec.expression, functionSpec.pointX를 포함하여 SymPy로 검산 가능한 형태여야 합니다.
가능한 모든 문제에는 gradingSpec을 넣고, gradingSpec.steps / gradingSpec.final 에 mode, expected, hint 를 포함하세요.
"""


@dataclass
class ContentGenerationRequest:
    bundle_id: str
    title: str
    unit_title: str
    concepts: list[str]
    target_exam: str
    lesson_count: int
    problem_count: int
    focus: str


class StrongLLMContentGenerator:
    def __init__(self) -> None:
        self.provider = settings.content_generation_provider
        self.api_url = settings.content_generation_api_url
        self.api_key = settings.content_generation_api_key
        self.model = settings.content_generation_model
        self.gemini_api_key = settings.gemini_api_key
        self.gemini_model = settings.gemini_model

    def build_prompt(self, spec: ContentGenerationRequest) -> dict[str, Any]:
        instruction = (
            "다음 조건을 만족하는 수능 수학 콘텐츠 묶음 JSON을 생성하세요.\n"
            f"- bundleId: {spec.bundle_id}\n"
            f"- title: {spec.title}\n"
            f"- unitTitle: {spec.unit_title}\n"
            f"- targetExam: {spec.target_exam}\n"
            f"- concepts: {', '.join(spec.concepts)}\n"
            f"- lessonCount: {spec.lesson_count}\n"
            f"- problemCount: {spec.problem_count}\n"
            f"- focus: {spec.focus}\n"
            "- 스키마는 기존 seed_suneung_math_p0_v1.json과 호환되어야 합니다.\n"
            "- lessonPacks, microScenes, problemSets, diagnosticQuestions를 포함하세요.\n"
            "- 각 문제는 functionSpec.expression, functionSpec.pointX를 포함하세요.\n"
            "- 자동채점 가능한 문제는 evaluationType='structured-generic' 또는 기존 자동채점 타입을 사용하세요.\n"
            "- 자동채점 가능한 문제는 gradingSpec.steps 와 gradingSpec.final 을 반드시 포함하세요.\n"
            "- 각 lesson scene은 title, narration, objects를 포함하세요.\n"
            "- output은 설명 없이 JSON만 반환하세요."
        )
        if self.provider == "gemini":
            return {
                "model": self.gemini_model,
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": instruction}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "responseMimeType": "application/json",
                },
            }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction},
            ],
            "response_format": {"type": "json_object"},
        }

    def generate_or_prepare_job(self, spec: ContentGenerationRequest) -> dict[str, Any]:
        payload = self.build_prompt(spec)
        if self.provider == "gemini":
            return self._generate_gemini(payload)
        if not self.api_url or not self.api_key:
            return {
                "mode": "job-only",
                "message": "실제 API 키가 없어 generation job payload만 반환합니다.",
                "request": payload,
            }

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with request.urlopen(http_request) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return {"mode": "remote", "raw": raw, "request": payload}

    def _generate_gemini(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.gemini_api_key:
            return {
                "mode": "job-only",
                "message": "Gemini API 키가 없어 generation job payload만 반환합니다.",
                "request": payload,
            }
        body = json.dumps(
            {
                "systemInstruction": payload["systemInstruction"],
                "contents": payload["contents"],
                "generationConfig": payload["generationConfig"],
            }
        ).encode("utf-8")
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{payload['model']}:generateContent"
        )
        http_request = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.gemini_api_key,
            },
            method="POST",
        )
        with request.urlopen(http_request) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return {"mode": "remote", "raw": raw, "request": payload}


def extract_generated_text(result: dict[str, Any]) -> str | None:
    raw = result.get("raw", {})
    candidates = raw.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        text_blocks = [
            item.get("text", "")
            for item in parts
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        joined = "\n".join(block.strip() for block in text_blocks if block.strip())
        if joined:
            return joined
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
    return None


def parse_generated_bundle(result: dict[str, Any]) -> dict[str, Any] | None:
    text = extract_generated_text(result)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def normalize_generated_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if "bundleId" in bundle and bundle.get("problemSets") and isinstance(
        bundle["problemSets"][0].get("problems", None) if bundle["problemSets"] else None,
        list,
    ):
        return bundle

    lesson_packs_source = bundle.get("lessonPacks", [])
    scene_source = bundle.get("microScenes", [])
    problems_source = {
        str(item.get("questionId") or item.get("id")): item
        for item in bundle.get("diagnosticQuestions", [])
    }
    grouped_scenes: dict[str, list[dict[str, Any]]] = {}
    for scene in scene_source:
        lesson_id = str(scene.get("lessonId") or "lesson-1")
        grouped_scenes.setdefault(lesson_id, []).append(scene)

    normalized_lesson_packs: list[dict[str, Any]] = []
    concept_lookup: list[dict[str, Any]] = []
    normalized_problem_sets: list[dict[str, Any]] = []

    default_concepts = bundle.get("concepts", [])
    if default_concepts and isinstance(default_concepts[0], str):
        concept_names = default_concepts
    else:
        concept_names = [item.get("id") for item in default_concepts if isinstance(item, dict)]

    for index, lesson_pack in enumerate(lesson_packs_source, start=1):
        lesson_pack_id = str(
            lesson_pack.get("id") or lesson_pack.get("lessonPackId") or f"{bundle['bundleId']}-lp{index}"
        )
        problem_set_ids = lesson_pack.get("problemSetIds", [])
        problem_set_id = str(problem_set_ids[0]) if problem_set_ids else f"{bundle['bundleId']}-ps{index}"
        concept_ids = [
            value if isinstance(value, str) else value.get("id")
            for value in lesson_pack.get("conceptIds")
            or lesson_pack.get("concepts")
            or concept_names
        ]
        concept_ids = [str(item) for item in concept_ids if item]
        for concept_index, concept_id in enumerate(concept_ids):
            concept_lookup.append(
                {
                    "id": concept_id,
                    "title": concept_id.replace("-", " ").title(),
                    "lessonPackId": lesson_pack_id,
                    "problemSetId": problem_set_id,
                    "baselineScore": max(48, 70 - concept_index * 3),
                    "baselineTrend": "+0",
                    "baselineRisk": "중간",
                }
            )
        lesson_ids = lesson_pack.get("lessonIds", [])
        scenes: list[dict[str, Any]] = []
        for lesson_id in lesson_ids or [f"{bundle['bundleId']}-lesson{index}"]:
            for scene_idx, scene in enumerate(grouped_scenes.get(str(lesson_id), []), start=1):
                scenes.append(
                    {
                        "id": str(scene.get("sceneId") or f"{lesson_id}-scene{scene_idx}"),
                        "title": str(scene.get("title") or f"장면 {scene_idx}"),
                        "narration": str(scene.get("narration") or ""),
                        "objects": [
                            _normalize_scene_object(object_payload, object_index)
                            for object_index, object_payload in enumerate(scene.get("objects", []), start=1)
                        ],
                    }
                )
        normalized_lesson_packs.append(
            {
                "id": lesson_pack_id,
                "title": str(lesson_pack.get("title") or lesson_pack_id),
                "unitTitle": str(lesson_pack.get("unitTitle") or bundle.get("unitTitle") or lesson_pack_id),
                "teacherName": "하늘 선생님",
                "conceptIds": concept_ids,
                "questionStarters": [
                    "핵심 개념을 다시 설명해줘",
                    "수능에서 어떤 함정이 나와?",
                    "오개념 포인트를 짚어줘",
                ],
                "scenes": scenes,
            }
        )

        source_problem_set = next(
            (
                item
                for item in bundle.get("problemSets", [])
                if str(item.get("problemSetId") or item.get("id")) == problem_set_id
            ),
            {},
        )
        normalized_problem_sets.append(
            {
                "id": problem_set_id,
                "title": str(source_problem_set.get("title") or f"{lesson_pack_id} 문제 묶음"),
                "lessonPackId": lesson_pack_id,
                "conceptIds": concept_ids,
                "problems": [
                    _normalize_problem(problems_source[problem_id], problem_index)
                    for problem_index, problem_id in enumerate(
                        source_problem_set.get("problemIds", []),
                        start=1,
                    )
                    if problem_id in problems_source
                ],
            }
        )

    if not concept_lookup:
        concept_lookup = [
            {
                "id": "generated-concept",
                "title": "Generated Concept",
                "lessonPackId": normalized_lesson_packs[0]["id"] if normalized_lesson_packs else "generated-lesson",
                "problemSetId": normalized_problem_sets[0]["id"] if normalized_problem_sets else "generated-set",
                "baselineScore": 60,
                "baselineTrend": "+0",
                "baselineRisk": "중간",
            }
        ]

    return {
        "bundleId": str(bundle.get("bundleId") or "generated-bundle"),
        "title": str(bundle.get("title") or "Generated Bundle"),
        "version": "generated",
        "domain": "suneung-math",
        "concepts": concept_lookup,
        "diagnosticQuestions": [
            _normalize_diagnostic(question, index, concept_lookup[0]["id"])
            for index, question in enumerate(bundle.get("diagnosticQuestions", []), start=1)
        ],
        "microScenes": {
            "slope": _default_micro_scene("generated-slope", "기울기 설명", "핵심 기울기 포인트를 다시 정리합니다."),
            "point": _default_micro_scene("generated-point", "접점 설명", "핵심 좌표 복구 포인트를 다시 정리합니다."),
            "recap": _default_micro_scene("generated-recap", "풀이 흐름 요약", "핵심 풀이 흐름을 한 번 더 요약합니다."),
        },
        "lessonPacks": normalized_lesson_packs,
        "problemSets": normalized_problem_sets,
    }


def _normalize_scene_object(payload: dict[str, Any], order: int) -> dict[str, Any]:
    position_map = {
        "top-left": (8, 12),
        "top-center": (28, 10),
        "mid-left": (8, 32),
        "mid-right": (52, 34),
        "bottom-left": (8, 56),
        "bottom-right": (52, 58),
        "bottom-center": (24, 64),
    }
    position = payload.get("position")
    x_value, y_value = position_map.get(position, (8, 16 + order * 10))
    offset_y = int(payload.get("offsetY", 0))
    object_type = str(payload.get("type") or "note")
    content = payload.get("content")
    if object_type == "graph":
        equation = str(content or "x**2")
        if equation.startswith("y ="):
            equation = equation.replace("y =", "", 1).strip()
        return {
            "id": f"generated-graph-{order}",
            "type": "graph",
            "x": 56,
            "y": 16,
            "w": 36,
            "h": 58,
            "graphSpec": {
                "function": equation,
                "xMin": -4,
                "xMax": 4,
                "yMin": -8,
                "yMax": 8,
                "tangentAt": 0,
                "markLabel": "focus",
            },
        }
    if object_type == "table":
        table_rows = payload.get("content", [])
        flattened = " / ".join(" | ".join(str(cell) for cell in row) for row in table_rows)
        return {
            "id": f"generated-table-{order}",
            "type": "note",
            "x": x_value,
            "y": y_value + offset_y / 8,
            "w": 40,
            "content": f"{payload.get('title', '표')}: {flattened}",
        }
    mapped_type = {
        "text": "note",
        "equation": "equation",
    }.get(object_type, "note")
    return {
        "id": f"generated-object-{order}",
        "type": mapped_type,
        "x": x_value,
        "y": y_value + offset_y / 8,
        "w": 40,
        "content": str(content),
    }


def _normalize_problem(question: dict[str, Any], order: int) -> dict[str, Any]:
    function_spec = question.get("functionSpec", {})
    point_value = function_spec.get("pointX", 0)
    if isinstance(point_value, list):
        point_value = point_value[0] if point_value else 0
    expression = str(function_spec.get("expression", "x**2"))
    statement = str(question.get("questionText") or question.get("statement") or "")
    is_maxmin_points = "극대점" in statement and "극소점" in statement
    grading_spec = question.get("gradingSpec")
    has_structured_grading = isinstance(grading_spec, dict) and isinstance(
        grading_spec.get("final"), dict
    )
    evaluation_type = (
        str(
            question.get("evaluationType")
            or question.get("evaluation_type")
            or "structured-generic"
        )
        if has_structured_grading
        else "maxmin-points" if is_maxmin_points else "reflection-open"
    )
    return {
        "id": str(question.get("questionId") or question.get("id") or f"generated-problem-{order}"),
        "title": str(question.get("title") or f"Generated Problem {order}"),
        "statement": statement,
        "coachHint": "도함수, 핵심 조건, 결론 순서로 정리하세요.",
        "expectedOutline": [
            "핵심 조건 정리",
            "도함수 또는 기준식 정리",
            "판정 포인트 확인",
            "결론 마무리",
        ],
        "functionSpec": {
            "expression": expression,
            "pointX": int(point_value) if isinstance(point_value, (int, float)) else 0,
        },
        "evaluationType": evaluation_type,
        "stepGuide": [
            {"label": "Step 1. 도함수", "placeholder": "예: f'(x) = ..."},
            {"label": "Step 2. 극값 후보", "placeholder": "예: f'(x)=0 → x=..."},
            {"label": "Step 3. 판정", "placeholder": "예: x=...는 극대, x=...는 극소"},
        ]
        if is_maxmin_points
        else [
            {"label": "Step 1. 핵심 식", "placeholder": "예: 필요한 식이나 조건을 정리"},
            {"label": "Step 2. 접근 과정", "placeholder": "예: 어떤 기준으로 판정했는지 적기"},
            {"label": "Step 3. 근거", "placeholder": "예: 부호 변화/계산 결과를 근거로 적기"},
        ],
        "finalPrompt": "예: 극대점 (a, f(a)), 극소점 (b, f(b))" if is_maxmin_points else "예: 최종 결론을 한 줄로 정리",
        "gradingSpec": grading_spec if has_structured_grading else None,
    }


def _normalize_diagnostic(question: dict[str, Any], order: int, concept_id: str) -> dict[str, Any]:
    options = question.get("options", [])
    normalized_options = [
        option.get("text", option) if isinstance(option, dict) else str(option)
        for option in options
    ]
    answer = question.get("answer", 0)
    if isinstance(answer, int) and answer > 0 and options and all(
        isinstance(option, dict) and "id" in option for option in options
    ):
        answer_index = next(
            (
                idx
                for idx, option in enumerate(options)
                if isinstance(option, dict) and int(option.get("id", -1)) == answer
            ),
            0,
        )
    else:
        answer_index = int(answer) if isinstance(answer, int) else 0
    return {
        "id": str(question.get("questionId") or f"generated-diag-{order}"),
        "prompt": str(question.get("questionText") or question.get("title") or ""),
        "options": normalized_options or ["없음"],
        "answer": answer_index,
        "concept": concept_id,
    }


def _default_micro_scene(scene_id: str, title: str, narration: str) -> dict[str, Any]:
    return {
        "id": scene_id,
        "title": title,
        "narration": narration,
        "resumeLabel": "이어서 같이 볼게요",
        "objects": [
            {
                "id": f"{scene_id}-note",
                "type": "callout",
                "x": 8,
                "y": 18,
                "w": 42,
                "content": narration,
            }
        ],
    }
