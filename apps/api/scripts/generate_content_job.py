from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.content_repository import MemoryContentRepository, PostgresContentRepository
from app.services.content_generation import (
    ContentGenerationRequest,
    StrongLLMContentGenerator,
    normalize_generated_bundle,
    parse_generated_bundle,
)
from app.core.config import settings


def import_bundle(bundle: dict) -> None:
    if settings.storage_backend == "postgres":
        repository = PostgresContentRepository(settings.database_url)
    else:
        repository = MemoryContentRepository()
    repository.import_bundle(bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an offline strong-LLM content generation job.")
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--unit-title", required=True)
    parser.add_argument("--target-exam", default="2028학년도 수능")
    parser.add_argument("--concept", action="append", dest="concepts", required=True)
    parser.add_argument("--lesson-count", type=int, default=1)
    parser.add_argument("--problem-count", type=int, default=6)
    parser.add_argument("--focus", default="개념 루프와 오답 회복이 분명한 수능 대비형")
    parser.add_argument("--out", default="generated_content_job.json")
    parser.add_argument("--bundle-out", default="")
    parser.add_argument("--import-bundle", action="store_true")
    args = parser.parse_args()

    spec = ContentGenerationRequest(
        bundle_id=args.bundle_id,
        title=args.title,
        unit_title=args.unit_title,
        concepts=args.concepts,
        target_exam=args.target_exam,
        lesson_count=args.lesson_count,
        problem_count=args.problem_count,
        focus=args.focus,
    )
    generator = StrongLLMContentGenerator()
    result = generator.generate_or_prepare_job(spec)
    output_path = Path(args.out)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved generation job to {output_path}")

    bundle = parse_generated_bundle(result)
    normalized_bundle = normalize_generated_bundle(bundle) if bundle else None
    if bundle and args.bundle_out:
        bundle_path = Path(args.bundle_out)
        bundle_path.write_text(json.dumps(normalized_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved generated bundle to {bundle_path}")
    if normalized_bundle and args.import_bundle:
        import_bundle(normalized_bundle)
        print(f"imported bundle {normalized_bundle.get('bundleId')}")


if __name__ == "__main__":
    main()
