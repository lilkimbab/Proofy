# Project Goal

이 프로젝트의 목표는 Study Agent의 **문제 생성 + 피드백 파트**를 단순 퀴즈 생성기가 아니라, 자료 기반 평가와 오답 개선을 담당하는 상업 서비스용 백엔드로 완성하는 것이다.

상업화 관점에서 이 파트의 가치는 “문제를 많이 만들어주는 것”이 아니라, 사용자가 올린 자료 안에서 실제 시험·과제에 가까운 문제를 만들고, 답안 근거와 오답 개선 행동까지 안정적으로 제공하는 데 있다.

## 핵심 목표

- 사용자가 올린 자료에서 검색된 chunk만 근거로 문제를 만든다.
- 모든 문제는 `source_chunk_ids`를 가져야 한다.
- 제출 전에는 정답, 해설, rubric을 숨긴다.
- 객관식은 LLM이 아니라 코드로 결정적으로 채점한다.
- 주관식은 rubric 기준으로 채점하고, 감점 이유와 다음 행동을 설명한다.
- 고난도 요청은 단순 개념 문제가 아니라 응용, 분석, 계산, 비교, 오류 탐지형 문제로 처리한다.
- 피드백은 차갑지 않게, 존댓말 기반의 친근한 학습 코치 말투로 제공한다.
- 오답 유형, 약점 개념, 복습 추천을 남겨 이후 문제 생성과 User Model 업데이트에 활용한다.
- 비용이 큰 LLM 호출은 필요한 경우에만 쓰고, 기본 테스트는 API key 없이 통과해야 한다.

## 상업화 품질 기준

- 문제는 교수나 선생님이 낸 것처럼 평가 의도, 근거, 정답 기준이 분명해야 한다.
- 고난도 문제는 단순 암기나 정의 확인이 아니라 적용, 분석, 비교, 계산, 오류 탐지, 근거 해석 중 하나 이상을 요구해야 한다.
- 사용자가 여러 개념을 섞은 문제를 원하면 생성 결과도 실제로 여러 개념을 연결해야 하며, 단일 개념 문제로 축소되면 품질 gate에서 걸러야 한다.
- 학습 콘텐츠 형식은 자료의 `tags`, `metadata`, `concepts`, `content`를 보고 추천하되, UI 구현은 다른 파트에 맡기고 우리 API는 제공 가능 기능과 추천 근거만 반환한다.
- 사용자는 AI 사용법을 몰라도 되게 하고, 자유 프롬프트보다 제한된 요청 필드와 추천 API를 우선한다.
- 업로드 자료를 다른 사용자 문제 생성이나 모델 학습에 재사용하지 않고, 원문 장문 복제와 저작권 위험을 품질 gate와 정책 문서로 관리한다.
- 월정액 손익을 위해 일반 문제, 고난도 문제, LLM 예산 한도를 분리해서 제어한다.
- prompt injection, system prompt leakage, vector/RAG 오염, unbounded consumption 같은 LLM 서비스 위험을 입력 검증, 출력 schema, 권한 제한, 사용량 제한으로 줄인다.

## 연구 기반 설계 원칙

- Evidence-Centered Design 관점처럼 문제는 “무엇을 평가할지”, “어떤 답안 행동을 증거로 볼지”, “어떤 채점 기준으로 판단할지”가 함께 설계되어야 한다.
- UDL 관점처럼 일반 사용자가 접근하기 쉬운 표현, 명확한 rubric, 다양한 문제 형식을 제공하되, 평가 목표를 흐리지 않는다.
- NIST AI RMF 관점처럼 AI 기능은 신뢰성, 안전성, 책임성, 측정 가능성을 운영 기준으로 가져야 한다.
- OWASP LLM Top 10 관점처럼 자료 chunk와 사용자 입력은 명령이 아니라 데이터로 취급하고, LLM 출력은 항상 후처리 검증을 통과해야 한다.
- OpenAI Structured Outputs 관점처럼 모델 출력은 자유 텍스트가 아니라 schema를 통과한 구조화 결과로 저장한다.

참고:

- ETS Evidence-Centered Design: https://www.ets.org/research/policy_research_reports/publications/report/2003/hsgs.html
- CAST UDL Assessment Tips: https://www.cast.org/resources/tips-articles/udl-tips-assessment/
- NIST Generative AI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- OWASP LLM01 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs

## 현재 우선순위

1. 문항 모델별 품질 기준을 분리하고, 고난도/복합 개념 요청이 실제 문항에 반영되는지 검증한다.
2. 고난도 문제 생성 eval set을 자료 형태별로 계속 확장한다.
3. 주관식 답안 시뮬레이션과 rubric별 confidence를 강화한다.
4. 오답 후 복습 문제, 힌트, 학습 콘텐츠 추천이 하나의 개선 루프로 이어지게 한다.
5. RAG/Search 파트와 통합할 때도 우리 코드는 `SearchService` 계약만 바라보게 유지한다.
6. 상업 서비스 운영을 위해 비용 한도, 남용 방지, 저작권 안전성, 문서 정리를 계속 유지한다.

## 역할 경계

우리 파트가 직접 하는 일:

- 문제 생성
- 정답과 해설 생성
- rubric 생성
- 문제 품질 검증
- 답안 제출과 채점
- 피드백 생성
- 오답 진단과 복습 추천

우리 파트가 직접 하지 않는 일:

- PDF 파싱
- OCR/이미지 인식
- Vector DB 내부 구현
- Search/RAG 검색 알고리즘
- 사용자 계정/개인정보 DB
- 전체 학습 로드맵 생성

## 작업 원칙

- 기능을 넓히기보다 평가 루프를 깊게 만든다.
- 문서나 코드 변경 전에는 `problem-feedback-roadmap.md`와 관련 테스트를 먼저 확인한다.
- 새 기능은 가능하면 eval fixture나 unit test로 검증한다.
- 외부 API, OpenAI key, 실제 RAG 서버가 없어도 기본 테스트는 통과해야 한다.
- 큰 변경 뒤에는 아래 명령을 실행한다.

```bash
.venv/bin/python -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/problem_agent_pycache .venv/bin/python -m compileall app tests
```

## 권장 `/goal`

Codex TUI에서 slash command가 지원되면 아래처럼 짧게 설정한다.

```text
/goal Study Agent 문제 생성·피드백 파트를 자료 기반 평가 엔진으로 완성한다. 외부 RAG 통합 전까지 문항 모델별 품질 기준, 고난도 eval, rubric 채점, 오답 진단, 복습 루프, 비용 통제를 강화하고 모든 변경은 테스트로 검증한다.
```
