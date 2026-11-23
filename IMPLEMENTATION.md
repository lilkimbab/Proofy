# AI Study Agent 구현 목차

## 현재 구현됨

1. Next.js App Router 프로젝트 전환
   - `app/layout.jsx`
   - `app/page.jsx`
   - `app/globals.css`

2. 디자인 UI 구현
   - 홈 대시보드
   - 내 문서 목록
   - 자료 업로드
   - 문서 학습 화면
   - AI 질문하기
   - 질문 기록
   - 학습 로드맵
   - 문제 풀이
   - 피드백
   - 학습 분석
   - 설정

3. MVP 1차 백엔드 뼈대
   - `POST /api/documents`: 파일 업로드, 저장, TXT/MD/PDF 텍스트 추출, 섹션 분리
   - `GET /api/documents`: 문서 목록 조회
   - `GET /api/sections`: 문서의 섹션별 설명 조회
   - `POST /api/ask`: 관련 chunk 검색 후 답변 생성
   - `GET /api/questions`: 질문 기록 조회

4. 긴 자료 처리 구조
   - 전체 자료를 한 번에 AI 컨텍스트에 넣지 않음
   - 자료를 섹션 단위로 분리
   - 섹션별 요약, 핵심 포인트, 키워드, 학습 프롬프트 생성
   - 섹션 아래 chunk를 만들고 embedding을 저장
   - 질문 시 관련 chunk만 검색
   - 섹션별 설명을 하나씩 제공하거나 전체 설명 묶음으로 표시

5. AI API 키 입력 공간
   - `.env.example`에 OpenAI/Supabase 환경변수 공간 추가
   - `OPENAI_API_KEY`가 비어 있으면 로컬 해시 embedding + 로컬 답변 사용
   - `OPENAI_API_KEY`를 넣으면 OpenAI embedding/chat 호출 구조로 전환

6. Vector DB 전환 설계
   - `SUPABASE_SCHEMA.sql` 추가
   - `documents`, `document_sections`, `document_chunks`, `questions`
   - pgvector 검색 함수 `match_document_chunks`

7. Supabase DB 연결 코드
   - `@supabase/supabase-js` 설치
   - `lib/supabaseAdmin.js` 추가
   - `lib/store.js`를 Supabase 우선, JSON fallback 구조로 변경
   - 환경변수가 있으면 Supabase DB 사용
   - 환경변수가 없으면 기존 `data/study-agent.json` 사용

8. AI API 없이 동작하는 문제/피드백 Agent
   - `lib/quizEngine.js` 추가
   - `POST /api/quizzes`: 문서 chunk 기반 로컬 문제 생성
   - `POST /api/attempts`: 답안 제출, 로컬 채점, 피드백 저장
   - 문제 풀이 UI를 실제 API에 연결

9. AI API 없이 동작하는 로드맵/분석 Agent
   - `lib/studyPlanner.js` 추가
   - `GET /api/roadmap`: 문서/질문/오답 기반 로컬 로드맵 생성
   - `GET /api/analytics`: 문서/질문/풀이 기반 학습 분석
   - 학습 로드맵 UI와 학습 분석 UI를 실제 API에 연결

10. Ollama/OpenAI Provider 구조
   - `AI_PROVIDER=local|ollama|openai|auto`
   - OpenAI API 키 없이 local 모드로 동작
   - Ollama 설정 시 로컬 오픈소스 모델 사용 가능
   - OpenAI API 키는 맨 마지막에 연결

11. 실서비스 기반 작업 1~7
   - Supabase DB 연결 준비 완료
   - `lib/auth.js`: Supabase bearer token 기반 사용자 식별, 미설정 시 guest fallback
   - 사용자별 문서/질문/문제/풀이 기록 분리
   - `lib/fileStorage.js`: Supabase Storage 연결, 미설정 시 local uploads fallback
   - URL 라우팅 추가: `/documents`, `/upload`, `/questions`, `/roadmap`, `/quiz`, `/analytics`, `/settings`
   - PDF 추출 메타데이터 추가: pageCount, extractionMethod, ocrRequired
   - 로드맵/분석 UI를 실제 API 데이터와 연결

## 남은 MVP 1차 구현

1. PDF 추출 고도화
   - 현재: `pdf-parse` 기반 텍스트 추출
   - 보완: 페이지 번호와 섹션 출처 저장
   - 스캔 PDF: OCR 연결 필요

2. DOCX/PPTX 텍스트 추출기 연결
   - DOCX 후보: `mammoth`
   - PPTX 후보: 전용 파서 또는 변환 파이프라인

3. Supabase 프로젝트 실제 연결
   - Supabase에서 `SUPABASE_SCHEMA.sql` 실행
   - `.env.local`에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` 입력
   - 실제 DB 저장/조회 확인

4. 실제 embedding/vector DB 연결
   - 후보: PostgreSQL + pgvector
   - 현재는 로컬 해시 embedding 기반 chunk 검색
   - 이후 OpenAI embedding을 `document_chunks.embedding`에 저장
   - `match_document_chunks` 함수로 pgvector 검색

5. Supabase Auth UI 마감
   - 현재 서버 API는 bearer token 기반 사용자 분리를 지원
   - 남은 작업: 로그인/회원가입 화면에서 Supabase session을 발급받고 API 요청에 token 첨부

6. 영구 DB 전환
   - 현재 Supabase 환경변수 없으면 `data/study-agent.json` 파일 저장
   - Supabase 환경변수 입력 후 DB 저장 확인 필요

7. AI 모델 연결
   - 맨 마지막 단계에서 진행
   - 선택지: OpenAI 또는 Ollama
   - 자료 기반 답변 생성
   - 섹션별 설명 고도화
   - 문제 생성 고도화
   - 출처 기반 답변 제한

## 추천 다음 순서

1. `npm install` 후 Next 앱 실행 확인
2. TXT/MD 업로드로 섹션 분리 흐름 테스트
3. PDF 파서 연결
4. 문제 생성/피드백 기능 구현
5. 로드맵/복습 Agent 구현
6. 로그인/사용자 분리
7. PostgreSQL + pgvector 연결
8. OpenAI API 연결
