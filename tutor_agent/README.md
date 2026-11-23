# Tutor Agent

FastAPI 기반 AI 과외 선생님 에이전트입니다.

이 패키지는 `tutor-agent` 브랜치의 `agent-server/` 프로토타입을 `problem_agent/`와 비슷한 독립 FastAPI 구조로 정리한 버전입니다. 원본 브랜치는 변경하지 않고, 통합 결과만 `main`에 반영하기 위한 패키지입니다.

## 기능

- 자료 기반 질문 답변
- 선택 텍스트 우선 설명
- 간단한 안전 가드
- 사용자 수준 기반 개인화
- 로컬 fallback 답변
- Ollama/OpenAI chat provider 확장

## 실행

```bash
cd tutor_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8101
```

## API

```text
GET /health
POST /agents/run
POST /agents/tutor
```

## 요청 예시

```bash
curl -sS -X POST http://127.0.0.1:8101/agents/tutor \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "guest",
    "document_id": "doc-1",
    "selected_text": "미분계수는 순간변화율입니다.",
    "payload": {
      "question": "이 부분을 쉽게 설명해줘",
      "document": {
        "title": "미분의 개념",
        "sections": [
          {
            "id": "s1",
            "title": "미분의 정의",
            "content": "미분계수는 순간변화율이며 접선의 기울기와 연결됩니다."
          }
        ]
      }
    }
  }'
```

