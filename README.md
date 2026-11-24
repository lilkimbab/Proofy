# Proofy

**해설지 봐도 모르겠던 그 한 줄, 칠판에서 다시.**

고3 수능 수학 AI 코치. 진단 12문제로 시작합니다.

| 이런 순간 | Proofy |
|---|---|
| 오늘 뭐 하지? | 진단과 설문으로 수능 날까지의 일간·주간 계획. 첫 화면엔 지금 할 공부 하나만. |
| 해설지 봐도 모르겠던 그 한 줄 | 칠판 강의 중에 그 줄을 콕 눌러 질문. 칠판이 그 자리에서 다시 풀어 줌. |
| 답은 맞았는데 풀이가 불안함 | 단계마다 SymPy로 채점. 식 모양이 달라도 같으면 정답, 틀리면 부호인지 계산인지 개념인지까지. |
| 같은 데서 또 틀림 | 틀린 문제는 오답노트로, 며칠 뒤 계획에 다시. |

```
미분계수의 정의 활용

lim (x→2) {f(x) − 3} / (x − 2) = 5   ⇒  f(2) = 3, f′(2) = 5
g(x) = x²f(x) 로 두면 g(2) = 12
lim (x→2) {x²f(x) − 12} / (x − 2) = g′(2)        ← 콕
= 2·2·f(2) + 2²·f′(2) = 32

Q. 왜 갑자기 g′(2)가 돼요?
A. 분자가 g(x) − g(2) 꼴이라서요. 미분계수 정의 그대로예요.
```

공통수학부터 대수, 미적분Ⅰ·Ⅱ, 확률과 통계, 기하까지 7과목 22단원 (2022 개정 교육과정, 2028학년도 수능 기준).

---

## 고난도 문제는 이렇게 만듭니다

목표는 수능 22번 수준. LLM이 낸 문제를 그대로 학생 앞에 두지 않습니다.

```mermaid
flowchart LR
    A[출제<br/>Gemini Flash] --> B{SymPy 검산}
    B -- 정답·조건 틀림 --> A
    B -- 통과 --> C{반례 찾기}
    C -- 답이 둘 이상 --> A
    C -- 없음 --> D[강한 모델이<br/>답 모르고 풀기]
    D --> E{약한 모델이<br/>풀어 버림?}
    E -- 예 --> F[더 어렵게<br/>다시 출제]
    F --> B
    E -- 아니요 --> G[사람 검토]
    G -- 승인 --> H[앱 문제 형식으로<br/>내보내기]
```

| 단계 | 하는 일 |
|---|---|
| 출제 | 한 번에 한 문제. 단원별 출제 틀(미적분Ⅰ 미분 7개, 적분 4개)을 돌아가며 지정. 함수를 직접 주지 않고 조건 (가)(나) 뒤에 숨김. 정답은 1~999 자연수. |
| SymPy 검산 | 모델이 조건마다 확인 식을 같이 써 오면, 허용된 함수만 쓰는 격리된 프로세스에서 실행해 조건과 정답을 확인. 틀리면 이유를 붙여 고쳐 오게 함. |
| 반례 찾기 | 다른 모델이 출제자가 놓친 경우를 찾음. 반례가 나오면 SymPy가 원래 조건에 넣어 보고, 답이 둘이면 돌려보냄. |
| 강한 모델 풀이 | `gpt-oss-120b`가 답을 모른 채 풀어서 정답을 맞히는지. 다르면 다른 모델에게 한 번 더. |
| 약한 모델 풀이 | `gpt-oss-20b`가 풀어 버리면 22번감이 아님. 같은 틀로 더 어렵게 다시 출제(최대 2번). |
| 사람 검토 | 풀이, 케이스, 검산 결과, 풀이 모델 기록을 보고 승인. 승인한 문제만 앱 문제 형식으로 나감. |

### 왜 사람이 마지막에 보나

첫 실행에서 Gemini가 낸 문제입니다.

> 최고차항의 계수가 1인 삼차함수 f(x)와 실수 k에 대하여 g(x) = (x − 1)|f(x) − k| 라 하자.
> (가) 함수 g(x)는 실수 전체의 집합에서 미분가능하다.
> (나) 함수 g(x)의 극댓값은 0이고, 극솟값은 −16이다.
> (다) f(0) = 2
>
> f(4)의 값을 구하시오.

출제자 답은 158입니다(f(x) − k = (x − 1)(x + 3)²). 그런데 f(x) − k = (x − t)³, t = 1 − 8·3^(1/4)/3 도 세 조건을 모두 만족하고, 이때 f(4) ≈ 262.03입니다. 풀이가 삼중근을 x = 1일 때만 따졌습니다.

이 문제는 SymPy 검산을 통과했고, 다른 풀이 모델도 158을 냈습니다. 22번 수준에서 문제가 망가지는 곳은 대개 정답 계산이 아니라 빠뜨린 경우 하나입니다. 이 문제는 지금 반례 찾기 단계의 테스트로 남아 있습니다.

---

## 지금 어디까지 왔나

| 영역 | 상태 |
|---|---|
| 고난도 문제 | 무료 Gemini Flash로 맞는 4점 문제(20~21번급)까지 확인. 22번 수준과 "답이 하나인지" 자동 확정은 아직이라 사람 검토가 마지막 관문. 승인한 문제를 앱 문제 은행에 넣는 연결은 다음 작업. |
| 문제 은행 | 22단원 924문항. 대부분 숫자만 바꾸는 템플릿이라 2~3점 수준이고, 위 파이프라인 문제로 바꿔 가는 중. |
| 강의 | 단원별 칠판 장면 1,002개. 지금 푸는 문제의 해설 중심으로 다시 쓰는 중. |
| 계정 | 데모용 인증. 공개 배포 전에 토큰 인증과 관리자 기능 잠금이 필요. |

---

## 바로 실행

```bash
./scripts/bootstrap.sh    # 가상환경, 패키지, .env 생성
./scripts/start-all.sh    # API와 화면을 함께 띄움
```

- 화면: http://localhost:3000
- API 문서: http://localhost:8000/docs
- 끄기: `./scripts/stop-all.sh`

LLM 키가 없어도 실행됩니다. 강의 중 질문에는 내장 답변이 나가고, 문제 출제만 키가 필요합니다.

### LLM 설정

키는 루트 `.env`에만 넣습니다(`.env.example` 참고).

| 쓰는 곳 | 모델 |
|---|---|
| 강의 중 질문, 계획 전략 | Gemini(`APP_GEMINI_MODEL`). 실패하면 Groq `openai/gpt-oss-120b`가 대신 답하고 5분 동안 Gemini를 건너뜀 |
| 문제 출제 | Gemini Flash. `--model`로 바꾸거나 예비 모델을 줄 수 있음 |
| 반례 찾기, 풀이 | Groq `openai/gpt-oss-120b`(강한 모델), `openai/gpt-oss-20b`(약한 모델) |

### 문제 출제

`apps/api`에서 실행합니다. 스크립트가 루트 `.env`를 직접 읽습니다. 한 문제에 5~15분 걸립니다.

```bash
.venv/bin/python -m scripts.generate_problems generate --unit calc1-diff --count 3
.venv/bin/python -m scripts.generate_problems list                # 상태, 난이도 판정, 검토 상태
.venv/bin/python -m scripts.generate_problems show <id>           # 문제, 풀이, 케이스, 검산, 풀이 모델 기록
.venv/bin/python -m scripts.generate_problems review <id> --approve   # 또는 --reject --note "이유"
.venv/bin/python -m scripts.generate_problems export              # 승인한 문제를 앱 문제 형식으로
.venv/bin/python -m scripts.generate_problems solve --file p.txt --answer 13   # 기출 등으로 난이도 신호 맞춰 보기
```

출제한 문제는 `apps/api/data/generated/problems/<단원>/`에, 내보낸 문제는 `apps/api/data/generated/approved/`에 쌓입니다.

---

## 개발

| 경로 | 내용 |
|---|---|
| `apps/web` | Next.js 15, React 18, TypeScript. 화면 전체와 `MathText` 수식 표시 |
| `apps/api` | FastAPI. 계획, 강의 세션, 채점, 오답노트, 문제 출제 |
| `apps/api/app/services/problem_factory.py` | 고난도 문제 출제 파이프라인 |
| `apps/api/app/domain/problem_verifier.py` | LLM이 쓴 조건 검사식을 격리해서 SymPy로 실행 |
| `apps/api/app/domain/evaluator.py` | 학생 풀이 단계별 SymPy 채점 |
| `apps/api/app/content` | 커리큘럼·강의·문제 생성기, 출제 틀 |
| `apps/study_agent` | 자료 업로드, RAG, 로드맵, 문제 생성, 튜터 에이전트. 아직 Proofy와 연결 전 |

테스트 (71개, 3분쯤):

```bash
PYTHONPATH=apps/api apps/api/.venv/bin/python -m unittest \
  apps/api/tests/test_evaluator.py apps/api/tests/test_content_selection.py \
  apps/api/tests/test_p1_service.py apps/api/tests/test_curriculum_review.py \
  apps/api/tests/test_lecture_copy.py apps/api/tests/test_problem_verifier.py \
  apps/api/tests/test_problem_factory.py
```

화면 타입 검사와 빌드:

```bash
cd apps/web && node_modules/.bin/tsc --noEmit -p . && npm run build
```

PostgreSQL까지 함께 띄우려면 `docker compose up --build`. 기본은 메모리 저장소(`APP_STORAGE_BACKEND=memory`)입니다.
