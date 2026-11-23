# Ollama 사용 방법

AI API 키를 마지막까지 넣지 않고 개발하다가, 로컬 오픈소스 모델을 쓰고 싶을 때 Ollama를 연결할 수 있습니다.

## 1. Ollama 실행

Ollama를 설치한 뒤 로컬 서버가 `http://127.0.0.1:11434`에서 실행되는지 확인합니다.

## 2. 추천 모델

Embedding:

```bash
ollama pull nomic-embed-text
```

Chat:

```bash
ollama pull llama3.1
```

다른 한국어 성능 좋은 모델을 쓰고 싶으면 `OLLAMA_CHAT_MODEL`만 바꾸면 됩니다.

## 3. 환경변수

`.env.local`에 아래처럼 설정합니다.

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_CHAT_MODEL=llama3.1
```

OpenAI API 키는 비워둬도 됩니다.

## 4. 동작 방식

- `AI_PROVIDER=local`: 로컬 해시 embedding + 로컬 규칙 기반 답변
- `AI_PROVIDER=ollama`: Ollama embedding/chat 사용
- `AI_PROVIDER=openai`: OpenAI embedding/chat 사용
- `AI_PROVIDER=auto`: OpenAI 키가 있으면 OpenAI, 없고 Ollama 설정이 있으면 Ollama, 둘 다 없으면 local

Ollama embedding은 `/api/embed`를 사용합니다.
