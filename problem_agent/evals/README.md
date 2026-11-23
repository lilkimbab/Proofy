# 문제 생성 + 피드백 Eval Fixtures

이 디렉터리는 문제 생성과 피드백 품질을 반복 검증하기 위한 고정 평가 데이터다.

원칙:

- 기본 테스트는 OpenAI API key 없이 실행되어야 한다.
- fixture는 모델 호출 결과를 직접 평가하는 대신, 현재 품질 기준이 어떤 출력을 통과/거부해야 하는지 정의한다.
- live LLM 평가는 별도 `pytest -m llm` 경로로만 실행한다.

구성:

- `problem_generation/`: 객관식, 주관식, 심층 주관식, 자료 기반성 평가
- `problem_generation/high_rigor_realistic_materials.jsonl`: 실제 과목 자료처럼 만든 9개 고난도 문제 생성 평가 세트
- `feedback/`: 주관식 채점 결과와 피드백 말투 평가
- `safety/`: RAG prompt injection 방어 평가

고난도 문제 생성 eval은 단순 JSON 형식만 보지 않는다.

- 근거 chunk 2개 이상 사용 여부
- 여러 개념을 함께 쓰는지
- 계산/수식형 문제의 LaTeX 사용 여부
- 주관식 rubric 항목 수와 채점 근거
- 객관식 오답 선택지의 진단 정보
- 자료 밖 조건, 원문 복제, AI 같은 문체 여부

실행:

```bash
.venv/bin/python -m pytest tests/test_eval_runner.py -q
```
