# AI 과외 선생님 서비스 전환 체크리스트

현재 MVP는 업로드, 섹션 분리, Ollama 기반 RAG 답변, 문제 생성, 피드백, 문서 위 질문/메모 기록까지 동작합니다.
실제 서비스로 전환하려면 아래 순서로 마무리하세요.

## 1. Supabase 마이그레이션

Supabase SQL Editor에서 아래 파일을 순서대로 실행합니다.

1. `SUPABASE_SCHEMA.sql`
2. `SUPABASE_MIGRATION_INTERACTIVE_QUESTIONS.sql`
3. `SUPABASE_MIGRATION_ANNOTATIONS.sql`
4. `SUPABASE_MIGRATION_EMBEDDING_JSON.sql`

`annotations` 테이블이 없으면 개발 중에는 로컬 JSON fallback으로 저장되지만, 실제 서비스에서는 반드시 Supabase에 저장해야 합니다.

## 2. Ollama 로컬 AI

MacBook RAM 16GB 기준 권장 구성:

```bash
ollama pull embeddinggemma
ollama pull gemma3:4b
ollama serve
```

`.env.local` 예시:

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
OLLAMA_CHAT_MODEL=gemma3:4b
```

## 3. 실제 서비스 전 핵심 보강

- Supabase Auth를 UI에 연결해 사용자별 문서/질문/메모/풀이 기록을 완전히 분리합니다.
- Supabase RLS 정책을 켜고 `user_id = auth.uid()` 기반 정책을 적용합니다.
- DOCX/PPTX/OCR 추출기를 추가합니다.
- 업로드 파일 용량 제한, 파일 형식 검증, 악성 파일 차단을 추가합니다.
- 긴 문서 처리 작업을 API 요청 안에서 끝내지 말고 background job/queue로 분리합니다.
- Ollama는 로컬 개발용으로 두고, 배포 서비스에서는 OpenAI API 또는 별도 GPU 서버를 연결합니다.

## 4. 배포 전 검증

```bash
npm run build
curl -sS http://127.0.0.1:4173/api/documents
curl -sS http://127.0.0.1:4173/api/roadmap
curl -sS http://127.0.0.1:4173/api/analytics
```

문서 업로드 후 확인할 것:

- 문서 상세 화면에서 섹션 탭이 전환되는지
- 드래그 후 질문/메모 저장이 되는지
- 본문에 질문/메모 표시가 남는지
- 질문 기록에서 이어 질문이 되는지
- 문제 생성, 정답 제출, 피드백이 저장되는지
- 진행률이 문서 상세 API에 반영되는지
