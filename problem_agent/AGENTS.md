# Project Instructions

이 프로젝트에서는 작업을 시작하기 전에 [GOAL.md](GOAL.md)를 먼저 확인한다.

## Working Rule

- `GOAL.md`의 목표, 우선순위, 역할 경계를 현재 작업의 기준으로 삼는다.
- 구현 범위가 애매하면 `GOAL.md`의 "우리 파트가 직접 하는 일"에 포함되는지 먼저 판단한다.
- 자료 파싱, OCR, Vector DB 내부 구현, 로그인 DB, 전체 로드맵 생성은 직접 구현하지 않고 계약 문서나 adapter로만 연결한다.
- 새 기능은 기존 로드맵과 테스트 흐름에 맞게 작게 추가한다.
- 큰 변경 뒤에는 가능하면 `pytest`와 `compileall`을 실행한다.
