from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.content.curriculum_seed import build_curriculum_bundle
from app.content.library_seed import build_library_bundle
from app.content.maxmin_seed import build_maxmin_bundle
from sympy import diff
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)
from sympy.abc import x


TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
ROOT = Path(__file__).resolve().parents[1]
SEED_BUNDLE_PATH = ROOT / "content" / "seed_suneung_math_p0_v1.json"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_CONTENT_ROOT = PROJECT_ROOT / "apps" / "api" / "data" / "content"
DEFAULT_BUNDLE_ID = "suneung-math-curriculum-v1"


class ContentRepository(Protocol):
    def load_default_bundle(self) -> dict: ...
    def load_bundle(self, bundle_id: str) -> dict | None: ...
    def list_catalog(self) -> list[dict]: ...
    def import_bundle(self, bundle: dict) -> None: ...
    def delete_bundle(self, bundle_id: str) -> bool: ...
    def save_review_report(self, report: dict) -> None: ...
    def list_review_reports(self) -> list[dict]: ...
    def get_review_report(self, review_job_id: str) -> dict | None: ...


def _sample_points(expression: str, x_min: float, x_max: float, samples: int = 51) -> list[list[float]]:
    expr = parse_expr(expression, transformations=TRANSFORMATIONS)
    points: list[list[float]] = []
    for index in range(samples):
        ratio = index / (samples - 1)
        x_value = x_min + (x_max - x_min) * ratio
        y_value = float(expr.subs(x, x_value))
        points.append([round(x_value, 4), round(y_value, 4)])
    return points


def _hydrate_graph_object(obj: dict) -> dict:
    spec = obj.get("graphSpec", {})
    function = str(spec["function"])
    x_min = float(spec.get("xMin", -1))
    x_max = float(spec.get("xMax", 4))
    y_min = float(spec.get("yMin", -4))
    y_max = float(spec.get("yMax", 6))
    curves = [
        {
            "color": "#f7e6a7",
            "points": _sample_points(function, x_min, x_max),
        }
    ]
    marks: list[dict] = []
    tangent_at = spec.get("tangentAt")
    if tangent_at is not None:
        tangent_x = float(tangent_at)
        expr = parse_expr(function, transformations=TRANSFORMATIONS)
        slope = diff(expr, x).subs(x, tangent_x)
        point_y = expr.subs(x, tangent_x)
        tangent_expression = slope * (x - tangent_x) + point_y
        curves.append(
            {
                "color": "#f3a43b",
                "points": _sample_points(str(tangent_expression), x_min, x_max),
            }
        )
        marks.append(
            {
                "x": tangent_x,
                "y": float(point_y),
                "label": str(spec.get("markLabel") or f"({tangent_x}, {point_y})"),
            }
        )

    hydrated = {
        "id": obj["id"],
        "type": "graph",
        "x": obj.get("x"),
        "y": obj.get("y"),
        "w": obj.get("w"),
        "h": obj.get("h"),
        "graph": {
            "xMin": x_min,
            "xMax": x_max,
            "yMin": y_min,
            "yMax": y_max,
            "curves": curves,
            "marks": marks,
        },
    }
    if "delayMs" in obj:
        hydrated["delayMs"] = obj["delayMs"]
    return hydrated


def hydrate_bundle(bundle: dict) -> dict:
    next_bundle = json.loads(json.dumps(bundle))
    for lesson_pack in next_bundle.get("lessonPacks", []):
        lesson_pack["scenes"] = [
            {
                **scene,
                "objects": [
                    _hydrate_graph_object(obj)
                    if obj.get("type") == "graph" and "graphSpec" in obj
                    else obj
                    for obj in scene.get("objects", [])
                ],
            }
            for scene in lesson_pack.get("scenes", [])
        ]
    next_bundle["microScenes"] = {
        key: {
            **scene,
            "objects": [
                _hydrate_graph_object(obj)
                if obj.get("type") == "graph" and "graphSpec" in obj
                else obj
                for obj in scene.get("objects", [])
            ],
        }
        for key, scene in next_bundle.get("microScenes", {}).items()
    }
    return next_bundle


def _catalog_curriculum(curriculum: dict) -> dict:
    if not curriculum:
        return {}
    return {
        "courses": [
            {
                "courseId": course.get("courseId"),
                "courseTitle": course.get("courseTitle"),
                "domains": [
                    {
                        "unitId": domain.get("unitId"),
                        "domainTitle": domain.get("domainTitle"),
                        "contentElements": domain.get("contentElements", []),
                        "drillLessonPackId": domain.get("drillLessonPackId"),
                        "drillProblemSetId": domain.get("drillProblemSetId"),
                        "drillProblemCount": domain.get("drillProblemCount", 0),
                    }
                    for domain in course.get("domains", [])
                ],
            }
            for course in curriculum.get("courses", [])
        ],
        "drillLibraries": curriculum.get("drillLibraries", []),
        "killerTracks": curriculum.get("killerTracks", []),
    }


def load_seed_bundle() -> dict:
    return hydrate_bundle(json.loads(SEED_BUNDLE_PATH.read_text(encoding="utf-8")))


def _seed_builder_bundles() -> list[dict]:
    return [
        load_seed_bundle(),
        hydrate_bundle(build_library_bundle()),
        hydrate_bundle(build_maxmin_bundle()),
        hydrate_bundle(build_curriculum_bundle()),
    ]


def _ensure_data_content_root() -> None:
    DATA_CONTENT_ROOT.mkdir(parents=True, exist_ok=True)


def _bundle_file_path(bundle_id: str) -> Path:
    return DATA_CONTENT_ROOT / f"{bundle_id}.json"


def persist_bundle_file(bundle: dict) -> Path:
    _ensure_data_content_root()
    path = _bundle_file_path(str(bundle["bundleId"]))
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete_bundle_file(bundle_id: str) -> bool:
    path = _bundle_file_path(bundle_id)
    if path.exists():
        path.unlink()
        return True
    return False


def sync_seed_bundles_to_data(*, overwrite: bool = False) -> list[Path]:
    written: list[Path] = []
    for bundle in _seed_builder_bundles():
        path = _bundle_file_path(str(bundle["bundleId"]))
        if overwrite or not path.exists():
            written.append(persist_bundle_file(bundle))
    for path in sorted(PROJECT_ROOT.glob("generated_*bundle*_normalized.json")):
        try:
            bundle = hydrate_bundle(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        target = _bundle_file_path(str(bundle["bundleId"]))
        if overwrite or not target.exists():
            written.append(persist_bundle_file(bundle))
    return written


def load_seed_bundles() -> list[dict]:
    _ensure_data_content_root()
    for bundle in _seed_builder_bundles():
        persist_bundle_file(bundle)
    bundles: list[dict] = []
    for path in sorted(DATA_CONTENT_ROOT.glob("*.json")):
        try:
            bundles.append(hydrate_bundle(json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    for path in sorted(PROJECT_ROOT.glob("generated_*bundle*_normalized.json")):
        try:
            bundle = hydrate_bundle(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if _bundle_file_path(str(bundle["bundleId"])).exists():
            continue
        bundles.append(bundle)
    return bundles


def load_seed_bundle_map() -> dict[str, dict]:
    return {bundle["bundleId"]: bundle for bundle in load_seed_bundles()}


@dataclass
class MemoryContentRepository:
    bundles: dict[str, dict] = field(default_factory=load_seed_bundle_map)
    review_reports: dict[str, dict] = field(default_factory=dict)

    def load_default_bundle(self) -> dict:
        bundle = self.bundles.get(DEFAULT_BUNDLE_ID) or next(iter(self.bundles.values()))
        return json.loads(json.dumps(bundle))

    def load_bundle(self, bundle_id: str) -> dict | None:
        bundle = self.bundles.get(bundle_id)
        return json.loads(json.dumps(bundle)) if bundle else None

    def list_catalog(self) -> list[dict]:
        return [
            {
                "bundleId": bundle["bundleId"],
                "title": bundle["title"],
                "version": bundle["version"],
                "domain": bundle["domain"],
                "lessonPackCount": len(bundle.get("lessonPacks", [])),
                "problemSetCount": len(bundle.get("problemSets", [])),
                "diagnosticQuestionCount": len(bundle.get("diagnosticQuestions", [])),
                "courseCount": len(bundle.get("curriculum", {}).get("courses", [])),
                "lessonPacks": [
                    {
                        "id": lesson_pack["id"],
                        "title": lesson_pack["title"],
                        "unitTitle": lesson_pack.get("unitTitle", lesson_pack["title"]),
                        "conceptIds": lesson_pack.get("conceptIds", []),
                    }
                    for lesson_pack in bundle.get("lessonPacks", [])
                ],
                "problemSets": [
                    {
                        "id": problem_set["id"],
                        "title": problem_set["title"],
                        "lessonPackId": problem_set.get("lessonPackId"),
                        "problemCount": len(problem_set.get("problems", [])),
                        "evaluationTypes": sorted(
                            {
                                problem.get("evaluationType", "tangent-line")
                                for problem in problem_set.get("problems", [])
                            }
                        ),
                    }
                    for problem_set in bundle.get("problemSets", [])
                ],
                "curriculum": _catalog_curriculum(bundle.get("curriculum", {})),
            }
            for bundle in self.bundles.values()
        ]

    def import_bundle(self, bundle: dict) -> None:
        hydrated = hydrate_bundle(bundle)
        self.bundles[hydrated["bundleId"]] = hydrated
        persist_bundle_file(hydrated)

    def delete_bundle(self, bundle_id: str) -> bool:
        deleted = self.bundles.pop(bundle_id, None) is not None
        file_deleted = delete_bundle_file(bundle_id)
        return deleted or file_deleted

    def save_review_report(self, report: dict) -> None:
        self.review_reports[str(report["reviewJobId"])] = json.loads(json.dumps(report))

    def list_review_reports(self) -> list[dict]:
        return [
            json.loads(json.dumps(report))
            for report in sorted(
                self.review_reports.values(),
                key=lambda item: item.get("createdAt", ""),
                reverse=True,
            )
        ]

    def get_review_report(self, review_job_id: str) -> dict | None:
        report = self.review_reports.get(review_job_id)
        return json.loads(json.dumps(report)) if report else None


class PostgresContentRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._seed_defaults()

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def _seed_defaults(self) -> None:
        sync_seed_bundles_to_data(overwrite=False)
        defaults = load_seed_bundles()
        for bundle in defaults:
            self.import_bundle(bundle)

    def load_default_bundle(self) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM content_bundles
                ORDER BY created_at ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                default = load_seed_bundle()
                self.import_bundle(default)
                return default
            return hydrate_bundle(row[0])

    def load_bundle(self, bundle_id: str) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM content_bundles
                WHERE bundle_id = %s
                """,
                (bundle_id,),
            )
            row = cursor.fetchone()
            return hydrate_bundle(row[0]) if row else None

    def list_catalog(self) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT bundle_id, title, version, domain, lesson_pack_count, problem_set_count, diagnostic_question_count, payload
                FROM content_bundles
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "bundleId": row[0],
                    "title": row[1],
                    "version": row[2],
                    "domain": row[3],
                    "lessonPackCount": row[4],
                    "problemSetCount": row[5],
                    "diagnosticQuestionCount": row[6],
                    "courseCount": len(row[7].get("curriculum", {}).get("courses", [])),
                    "lessonPacks": [
                        {
                            "id": lesson_pack["id"],
                            "title": lesson_pack["title"],
                            "unitTitle": lesson_pack.get("unitTitle", lesson_pack["title"]),
                            "conceptIds": lesson_pack.get("conceptIds", []),
                        }
                        for lesson_pack in row[7].get("lessonPacks", [])
                    ],
                    "problemSets": [
                        {
                            "id": problem_set["id"],
                            "title": problem_set["title"],
                            "lessonPackId": problem_set.get("lessonPackId"),
                            "problemCount": len(problem_set.get("problems", [])),
                            "evaluationTypes": sorted(
                                {
                                    problem.get("evaluationType", "tangent-line")
                                    for problem in problem_set.get("problems", [])
                                }
                            ),
                        }
                        for problem_set in row[7].get("problemSets", [])
                    ],
                    "curriculum": _catalog_curriculum(row[7].get("curriculum", {})),
                }
                for row in rows
            ]

    def import_bundle(self, bundle: dict) -> None:
        raw_bundle = json.loads(json.dumps(bundle))
        bundle_id = raw_bundle["bundleId"]
        persist_bundle_file(raw_bundle)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO content_bundles (
                    bundle_id,
                    title,
                    version,
                    domain,
                    lesson_pack_count,
                    problem_set_count,
                    diagnostic_question_count,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (bundle_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    version = EXCLUDED.version,
                    domain = EXCLUDED.domain,
                    lesson_pack_count = EXCLUDED.lesson_pack_count,
                    problem_set_count = EXCLUDED.problem_set_count,
                    diagnostic_question_count = EXCLUDED.diagnostic_question_count,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """,
                (
                    bundle_id,
                    raw_bundle["title"],
                    raw_bundle["version"],
                    raw_bundle["domain"],
                    len(raw_bundle.get("lessonPacks", [])),
                    len(raw_bundle.get("problemSets", [])),
                    len(raw_bundle.get("diagnosticQuestions", [])),
                    json.dumps(raw_bundle, ensure_ascii=False),
                ),
            )

            for ordering, question in enumerate(raw_bundle.get("diagnosticQuestions", [])):
                cursor.execute(
                    """
                    INSERT INTO content_diagnostic_questions (
                        question_id,
                        bundle_id,
                        ordering,
                        concept_id,
                        prompt,
                        options,
                        answer_index,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                    ON CONFLICT (question_id)
                    DO UPDATE SET
                        bundle_id = EXCLUDED.bundle_id,
                        ordering = EXCLUDED.ordering,
                        concept_id = EXCLUDED.concept_id,
                        prompt = EXCLUDED.prompt,
                        options = EXCLUDED.options,
                        answer_index = EXCLUDED.answer_index,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (
                        question["id"],
                        bundle_id,
                        ordering,
                        question["concept"],
                        question["prompt"],
                        json.dumps(question["options"], ensure_ascii=False),
                        question["answer"],
                        json.dumps(question, ensure_ascii=False),
                    ),
                )

            for lesson_pack in raw_bundle.get("lessonPacks", []):
                cursor.execute(
                    """
                    INSERT INTO content_lesson_packs (
                        lesson_pack_id,
                        bundle_id,
                        title,
                        unit_title,
                        teacher_name,
                        concept_ids,
                        question_starters,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (lesson_pack_id)
                    DO UPDATE SET
                        bundle_id = EXCLUDED.bundle_id,
                        title = EXCLUDED.title,
                        unit_title = EXCLUDED.unit_title,
                        teacher_name = EXCLUDED.teacher_name,
                        concept_ids = EXCLUDED.concept_ids,
                        question_starters = EXCLUDED.question_starters,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (
                        lesson_pack["id"],
                        bundle_id,
                        lesson_pack["title"],
                        lesson_pack["unitTitle"],
                        lesson_pack["teacherName"],
                        json.dumps(lesson_pack.get("conceptIds", []), ensure_ascii=False),
                        json.dumps(lesson_pack.get("questionStarters", []), ensure_ascii=False),
                        json.dumps(lesson_pack, ensure_ascii=False),
                    ),
                )
                for ordering, scene in enumerate(lesson_pack.get("scenes", [])):
                    cursor.execute(
                        """
                        INSERT INTO content_lesson_scenes (
                            scene_id,
                            lesson_pack_id,
                            ordering,
                            title,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (scene_id)
                        DO UPDATE SET
                            lesson_pack_id = EXCLUDED.lesson_pack_id,
                            ordering = EXCLUDED.ordering,
                            title = EXCLUDED.title,
                            payload = EXCLUDED.payload,
                            updated_at = NOW()
                        """,
                        (
                            scene["id"],
                            lesson_pack["id"],
                            ordering,
                            scene["title"],
                            json.dumps(scene, ensure_ascii=False),
                        ),
                    )

            for problem_set in raw_bundle.get("problemSets", []):
                cursor.execute(
                    """
                    INSERT INTO content_problem_sets (
                        problem_set_id,
                        bundle_id,
                        lesson_pack_id,
                        title,
                        concept_ids,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (problem_set_id)
                    DO UPDATE SET
                        bundle_id = EXCLUDED.bundle_id,
                        lesson_pack_id = EXCLUDED.lesson_pack_id,
                        title = EXCLUDED.title,
                        concept_ids = EXCLUDED.concept_ids,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    (
                        problem_set["id"],
                        bundle_id,
                        problem_set["lessonPackId"],
                        problem_set["title"],
                        json.dumps(problem_set.get("conceptIds", []), ensure_ascii=False),
                        json.dumps(problem_set, ensure_ascii=False),
                    ),
                )
                for ordering, problem in enumerate(problem_set.get("problems", [])):
                    cursor.execute(
                        """
                        INSERT INTO content_problems (
                            problem_id,
                            problem_set_id,
                            ordering,
                            title,
                            statement,
                            function_spec,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                        ON CONFLICT (problem_id)
                        DO UPDATE SET
                            problem_set_id = EXCLUDED.problem_set_id,
                            ordering = EXCLUDED.ordering,
                            title = EXCLUDED.title,
                            statement = EXCLUDED.statement,
                            function_spec = EXCLUDED.function_spec,
                            payload = EXCLUDED.payload,
                            updated_at = NOW()
                        """,
                        (
                            problem["id"],
                            problem_set["id"],
                            ordering,
                            problem["title"],
                            problem["statement"],
                            json.dumps(problem.get("functionSpec", {}), ensure_ascii=False),
                            json.dumps(problem, ensure_ascii=False),
                        ),
                    )
            for course in raw_bundle.get("curriculum", {}).get("courses", []):
                for domain in course.get("domains", []):
                    node_id = f"{bundle_id}:{domain['unitId']}"
                    cursor.execute(
                        """
                        INSERT INTO content_curriculum_nodes (
                            node_id,
                            bundle_id,
                            course_id,
                            course_title,
                            unit_title,
                            pdf_pages,
                            content_elements,
                            achievement_codes,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                        ON CONFLICT (node_id)
                        DO UPDATE SET
                            bundle_id = EXCLUDED.bundle_id,
                            course_id = EXCLUDED.course_id,
                            course_title = EXCLUDED.course_title,
                            unit_title = EXCLUDED.unit_title,
                            pdf_pages = EXCLUDED.pdf_pages,
                            content_elements = EXCLUDED.content_elements,
                            achievement_codes = EXCLUDED.achievement_codes,
                            payload = EXCLUDED.payload,
                            updated_at = NOW()
                        """,
                        (
                            node_id,
                            bundle_id,
                            course["courseId"],
                            course["courseTitle"],
                            domain["domainTitle"],
                            domain.get("pdfPages", ""),
                            json.dumps(domain.get("contentElements", []), ensure_ascii=False),
                            json.dumps(domain.get("achievementCodes", []), ensure_ascii=False),
                            json.dumps(domain, ensure_ascii=False),
                        ),
                    )
            connection.commit()

    def delete_bundle(self, bundle_id: str) -> bool:
        delete_bundle_file(bundle_id)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM content_review_items WHERE review_job_id IN (SELECT review_job_id FROM content_review_jobs WHERE bundle_id = %s)", (bundle_id,))
            cursor.execute("DELETE FROM content_review_jobs WHERE bundle_id = %s", (bundle_id,))
            cursor.execute("DELETE FROM content_problems WHERE problem_set_id IN (SELECT problem_set_id FROM content_problem_sets WHERE bundle_id = %s)", (bundle_id,))
            cursor.execute("DELETE FROM content_problem_sets WHERE bundle_id = %s", (bundle_id,))
            cursor.execute("DELETE FROM content_lesson_scenes WHERE lesson_pack_id IN (SELECT lesson_pack_id FROM content_lesson_packs WHERE bundle_id = %s)", (bundle_id,))
            cursor.execute("DELETE FROM content_lesson_packs WHERE bundle_id = %s", (bundle_id,))
            cursor.execute("DELETE FROM content_diagnostic_questions WHERE bundle_id = %s", (bundle_id,))
            cursor.execute("DELETE FROM content_curriculum_nodes WHERE bundle_id = %s", (bundle_id,))
            cursor.execute("DELETE FROM content_bundles WHERE bundle_id = %s", (bundle_id,))
            deleted = cursor.rowcount > 0
            connection.commit()
        return deleted

    def save_review_report(self, report: dict) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO content_review_jobs (
                    review_job_id,
                    source_provider,
                    bundle_id,
                    status,
                    approved_problem_count,
                    rejected_problem_count,
                    raw_bundle,
                    approved_bundle,
                    report
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (review_job_id)
                DO UPDATE SET
                    source_provider = EXCLUDED.source_provider,
                    bundle_id = EXCLUDED.bundle_id,
                    status = EXCLUDED.status,
                    approved_problem_count = EXCLUDED.approved_problem_count,
                    rejected_problem_count = EXCLUDED.rejected_problem_count,
                    raw_bundle = EXCLUDED.raw_bundle,
                    approved_bundle = EXCLUDED.approved_bundle,
                    report = EXCLUDED.report,
                    updated_at = NOW()
                """,
                (
                    report["reviewJobId"],
                    report.get("sourceProvider", "gemini"),
                    report.get("bundleId", ""),
                    report.get("status", "reviewed"),
                    int(report.get("approvedProblemCount", 0)),
                    int(report.get("rejectedProblemCount", 0)),
                    json.dumps(report.get("rawBundle", {}), ensure_ascii=False),
                    json.dumps(report.get("approvedBundle", {}), ensure_ascii=False),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            for item in report.get("items", []):
                cursor.execute(
                    """
                    INSERT INTO content_review_items (
                        item_id,
                        review_job_id,
                        problem_id,
                        problem_set_id,
                        status,
                        reasons,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (item_id)
                    DO UPDATE SET
                        review_job_id = EXCLUDED.review_job_id,
                        problem_id = EXCLUDED.problem_id,
                        problem_set_id = EXCLUDED.problem_set_id,
                        status = EXCLUDED.status,
                        reasons = EXCLUDED.reasons,
                        payload = EXCLUDED.payload
                    """,
                    (
                        item["id"],
                        report["reviewJobId"],
                        item.get("problemId", ""),
                        item.get("problemSetId", ""),
                        item.get("status", "rejected"),
                        json.dumps(item.get("reasons", []), ensure_ascii=False),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
            connection.commit()

    def list_review_reports(self) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report
                FROM content_review_jobs
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
        return [row[0] for row in rows]

    def get_review_report(self, review_job_id: str) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT report
                FROM content_review_jobs
                WHERE review_job_id = %s
                """,
                (review_job_id,),
            )
            row = cursor.fetchone()
        return row[0] if row else None
