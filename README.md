# Proofy

입시생을 위한 AI 수능 코치. Proofy는 진단과 계획, AI 칠판 강의, 풀이 평가 등을 바탕으로 여러분을 만점의 길로 인도합니다.

## What It Does

- 진단 결과를 바탕으로 수능까지의 일간/주간 학습 계획을 생성합니다.
- AI 칠판 강의를 바탕으로 학생이 알아야 하는 개념과 응용을 마스터합니다.
- 학생 질문을 단순 AI의 정해진 답변이 아닌 AI 칠판을 이용해 사용자와 상호작용하며 답을 합니다.
- SymPy 기반 evaluator로 풀이 단계를 채점하고 오답 원인을 분류합니다.
- 자동 오답노트, 게임 형식 강의 계획으로 수능 날 까지 꾸준하게 유지합니다.
- 콘텐츠를 DB와 JSON 파일로 분리해 강의/문제를 관리합니다.

## Tech Stack

- Frontend: `Next.js`, `React`, `TypeScript`
- Backend: `FastAPI`, `Python`
- Storage: in-memory demo mode, PostgreSQL
- Math checking: `SymPy`
- AI hooks: Gemini-compatible LLM routes
- Local orchestration: Docker Compose, Makefile scripts

## Repository Layout

- `apps/web`: Next.js App Router frontend
- `apps/api`: FastAPI backend
- `apps/api/app/db/schema.sql`: PostgreSQL schema
- `apps/api/app/content`: seed builders and baseline content
- `apps/api/data/content`: app-readable lesson/problem bundles
- `apps/api/tests`: backend regression tests
- `scripts`: local bootstrap/start/stop scripts

## Quick Start

```bash
./scripts/bootstrap.sh
./scripts/start-all.sh
```

- Web: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`

Stop the local services:

```bash
./scripts/stop-all.sh
```

## Manual Development

Run the API:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export APP_STORAGE_BACKEND=memory
export APP_ALLOWED_ORIGINS=http://localhost:3000
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the web app:

```bash
cd apps/web
cp .env.local.example .env.local
npm install
npm run dev
```

Run with Docker:

```bash
docker compose up --build
```

## LLM Configuration

Proofy works without an LLM key by falling back to built-in demo responses. To enable Gemini-backed question answering and content generation:

```bash
export APP_GEMINI_API_KEY=YOUR_KEY
export APP_GEMINI_MODEL=gemini-2.5-flash
export APP_LLM_PROVIDER=gemini
export APP_CONTENT_GENERATION_PROVIDER=gemini
```

## Content Generation

Generate a new content job and normalized bundle:

```bash
export APP_GEMINI_API_KEY=YOUR_KEY
export APP_GEMINI_MODEL=gemini-2.5-flash
export APP_CONTENT_GENERATION_PROVIDER=gemini
PYTHONPATH=apps/api python3 apps/api/scripts/generate_content_job.py \
  --bundle-id suneung-math-maxmin-v1 \
  --title "극대극소 기초 팩" \
  --unit-title "미분 - 극대극소 기초" \
  --concept maxmin-basic \
  --concept sign-analysis \
  --lesson-count 1 \
  --problem-count 4 \
  --out generated_gemini_job.json \
  --bundle-out generated_gemini_bundle.json
```

Generated root-level `generated_gemini*.json` files are ignored by Git.

## Tests

```bash
PYTHONPATH=apps/api python3 -m unittest \
  apps/api/tests/test_evaluator.py \
  apps/api/tests/test_content_selection.py \
  apps/api/tests/test_p1_service.py \
  apps/api/tests/test_curriculum_review.py
```

Frontend build check:

```bash
cd apps/web
npm run build
```
