.PHONY: bootstrap api web dev stop test build-web

bootstrap:
	./scripts/bootstrap.sh

api:
	./scripts/start-api.sh

web:
	./scripts/start-web.sh

dev:
	./scripts/start-all.sh

stop:
	./scripts/stop-all.sh

test:
	PYTHONPATH=apps/api python3 -m unittest \
		apps/api/tests/test_evaluator.py \
		apps/api/tests/test_content_selection.py \
		apps/api/tests/test_p1_service.py \
		apps/api/tests/test_curriculum_review.py \
		apps/api/tests/test_lecture_copy.py \
		apps/api/tests/test_problem_verifier.py \
		apps/api/tests/test_problem_factory.py \
		apps/api/tests/test_llm_service.py

build-web:
	cd apps/web && npm run build
