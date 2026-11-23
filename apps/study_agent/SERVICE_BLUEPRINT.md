# AI 과외 선생님 서비스 설계도

## 1. 서비스 개요

AI 과외 선생님은 사용자가 업로드한 학습 자료를 기반으로 개인 맞춤형 학습을 제공하는 문서 기반 AI 학습 플랫폼입니다.

핵심 흐름은 다음과 같습니다.

```text
로그인
→ 자료 업로드
→ 텍스트 추출
→ 섹션 분리
→ chunk 생성
→ embedding 생성
→ 학습 문서 화면 제공
→ 드래그 질문/메모
→ RAG 답변
→ 문제 생성
→ 풀이 피드백
→ 학습 기록/분석
```

## 2. 핵심 사용자 경험

### 2.1 로그인

사용자는 Supabase Auth 기반 이메일/비밀번호 로그인을 통해 개인 학습 공간에 접근합니다.

- 회원가입
- 로그인
- 로그아웃
- 세션 유지
- 사용자별 문서/질문/메모/풀이 기록 분리

### 2.2 자료 업로드

사용자는 PDF, TXT, MD 등 학습 자료를 업로드합니다.

현재 MVP:

- TXT/MD 즉시 분석
- PDF 텍스트 추출
- DOCX/PPTX/OCR은 확장 대상

업로드된 자료는 다음 단계를 거칩니다.

```text
파일 저장
→ 텍스트 추출
→ 섹션 분리
→ 섹션별 요약/핵심어 생성
→ chunk 분리
→ embedding 생성
→ DB 저장
```

### 2.3 문서 기반 학습

학습 화면은 업로드된 자료를 섹션 단위로 보여줍니다.

기능:

- 섹션 탭 이동
- 섹션별 설명 확인
- 핵심 요약 확인
- 학습 진행률 저장
- 문서 위 질문/메모 표시

### 2.4 드래그 질문/메모

사용자가 문서의 특정 문장을 드래그하면 질문 또는 메모를 남길 수 있습니다.

질문 흐름:

```text
문장 드래그
→ 질문 선택
→ 질문 입력
→ 선택 텍스트 + 문서 chunk 기반 RAG 검색
→ AI 답변 생성
→ 본문에 질문 표시
→ 이어 질문 가능
```

메모 흐름:

```text
문장 드래그
→ 메모 선택
→ 메모 입력
→ 본문에 메모 표시
→ 다시 열어서 수정 가능
```

### 2.5 문제 생성 및 피드백

문서 chunk와 핵심어를 기반으로 문제를 생성합니다.

현재 MVP:

- 단답형 문제 생성
- 힌트 제공
- 정답 제출
- 풀이 피드백
- 취약 개념 저장

확장 대상:

- 객관식
- OX
- 서술형
- 난이도 자동 조절
- 오답 기반 유사 문제 생성

## 3. 화면 구조

```text
/login
  - 로그인
  - 회원가입
  - 게스트 둘러보기

/
  - 홈 대시보드

/documents
  - 내 문서 목록

/upload
  - 자료 업로드

/learn
  - 문서 학습 화면
  - 섹션 탭
  - 드래그 질문/메모
  - 질문/메모 기록 패널

/questions
  - 질문 기록

/quiz
  - 문제 생성
  - 답안 제출

/roadmap
  - 학습 로드맵

/analytics
  - 학습 분석

/settings
  - 사용자 설정
```

## 4. 시스템 아키텍처

```text
Frontend: Next.js App Router
  |
  |-- Supabase Auth session
  |-- Authorization Bearer token
  |
Backend: Next.js API Routes
  |
  |-- Auth 검증
  |-- 문서 처리
  |-- 질문/메모 처리
  |-- 문제/피드백 처리
  |
Storage: Supabase Storage / local fallback
  |
Database: Supabase Postgres
  |
AI Layer
  |-- Ollama local model
  |-- OpenAI optional
  |-- local fallback
```

## 5. 주요 API

### Auth

```text
GET /api/auth/config
GET /api/auth/session
```

### Documents

```text
GET /api/documents
POST /api/documents
GET /api/documents/[id]
PATCH /api/documents/[id]
GET /api/sections?documentId=
```

### RAG Q&A

```text
POST /api/ask
GET /api/questions
```

### Annotations

```text
GET /api/annotations?documentId=&sectionId=
POST /api/annotations
PATCH /api/annotations
```

### Quiz

```text
POST /api/quizzes
POST /api/attempts
```

### Learning

```text
GET /api/roadmap
GET /api/analytics
```

## 6. 데이터베이스 구조

### documents

문서 기본 정보입니다.

```text
id
user_id
title
subject
goal
deadline
file_url
storage_path
status
progress
overview
created_at
updated_at
```

### document_sections

문서를 학습 단위로 나눈 섹션입니다.

```text
id
document_id
order_index
title
content
summary
explanation
keywords
```

### document_chunks

RAG 검색에 사용하는 작은 텍스트 단위입니다.

```text
id
document_id
section_id
chunk_index
content
token_estimate
embedding_provider
embedding
embedding_json
```

### questions

전체 질문 기록입니다.

```text
id
user_id
document_id
section_id
selected_text
anchor
question
answer
sources
mode
created_at
```

### annotations

문서 위에 남는 질문/메모 기록입니다.

```text
id
user_id
document_id
section_id
type
selected_text
anchor
note
thread
created_at
updated_at
```

### generated_quizzes

생성된 문제입니다.

```text
id
user_id
document_id
section_id
chunk_id
type
difficulty
question
options
answer
explanation
hint
source
```

### quiz_attempts

사용자 풀이 기록입니다.

```text
id
user_id
quiz_id
document_id
user_answer
is_correct
feedback
weak_concepts
created_at
```

## 7. AI 처리 구조

### 7.1 긴 자료 처리

긴 자료를 한 번에 AI에 넣지 않습니다.

```text
전체 문서
→ 섹션 분리
→ 섹션별 설명 생성
→ chunk 분리
→ chunk embedding
→ 질문 시 관련 chunk만 검색
→ 선택 텍스트 + 관련 chunk로 답변 생성
```

이 방식은 컨텍스트 초과와 토큰 낭비를 줄입니다.

### 7.2 RAG 답변

```text
사용자 질문
→ 질문 embedding 생성
→ 문서 chunk와 유사도 비교
→ 관련 chunk top-k 선택
→ 선택 텍스트와 함께 AI prompt 구성
→ 답변 생성
→ sources 저장
```

### 7.3 Ollama 구성

MacBook RAM 16GB 기준 권장:

```text
Embedding: embeddinggemma
Chat: gemma3:4b
```

`.env.local`:

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma
OLLAMA_CHAT_MODEL=gemma3:4b
```

### 7.4 OpenAI 확장

운영 서비스에서는 OpenAI API 또는 별도 GPU 서버를 연결할 수 있습니다.

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
```

## 8. 현재 구현 상태

구현 완료:

- Next.js 프로젝트
- Supabase DB 연결
- Supabase Storage 연결
- Supabase Auth 로그인/회원가입
- 문서 업로드
- 텍스트 추출
- 섹션 분리
- chunk 생성
- Ollama embedding/chat 연결
- RAG 질문 답변
- 문서 위 드래그 질문/메모
- 질문/메모 본문 표시
- 이어 질문
- 문제 생성
- 풀이 피드백
- 학습 로드맵
- 학습 분석
- 진행률 저장

부분 구현:

- PDF 텍스트 추출
- 로컬 fallback 저장소
- OpenAI 연결 구조

미구현/확장 대상:

- DOCX/PPTX 본문 추출
- OCR
- Supabase RLS 정책
- 소셜 로그인
- 비밀번호 재설정 UI
- background job queue
- 배포 환경 AI 서버
- 결제/요금제
- 관리자 페이지

## 9. 실제 서비스 전환 순서

1. Supabase 마이그레이션 전체 실행
2. Supabase Auth Email provider 설정
3. RLS 정책 적용
4. DOCX/PPTX/OCR 추출기 추가
5. 업로드 용량 제한 및 파일 검증 추가
6. 긴 문서 분석을 background job으로 분리
7. 배포 환경 AI provider 결정
8. 에러 로깅/모니터링 추가
9. Vercel 또는 서버 배포
10. 사용자 테스트

## 10. 핵심 차별점

기존 AI 챗봇과의 차이:

```text
채팅 중심
→ 문서 기반 학습

일반 지식 답변
→ 내 자료 기반 답변

일회성 질문
→ 문서 위 질문/메모 기록

단순 정답 제공
→ 문제 생성 + 풀이 피드백 + 약점 분석

수동 학습
→ 로드맵 기반 학습 관리
```

최종 한 문장:

```text
사용자가 업로드한 학습 자료를 기반으로 AI가 개인화된 과외 선생님처럼 학습을 지도하고, 문서 위에서 직접 질문하며 기록을 남기며 공부할 수 있는 인터랙티브 학습 플랫폼
```
