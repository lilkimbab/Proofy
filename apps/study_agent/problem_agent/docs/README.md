# 문제 생성 + 피드백 문서 안내

문서는 아래 기준으로 본다. 개발 기준 문서와 참고 문서를 분리해서, 팀원이 읽을 때 무엇을 먼저 봐야 하는지 헷갈리지 않게 한다.

## 1. 먼저 볼 기준 문서

- [../README.md](../README.md): 실행 방법, 환경 변수, API 테스트
- 팀원 통합용 짧은 안내는 루트 [../README.md](../README.md)의 "팀원이 빠르게 통합할 때 보는 기준"에 통합한다.
- [../problem-feedback-roadmap.md](../problem-feedback-roadmap.md): 현재 구현 단계와 다음 작업 기준
- [problem-feedback-integration-contracts.md](problem-feedback-integration-contracts.md): 팀 연동 계약
- [problem-feedback-shared-server-integration.md](problem-feedback-shared-server-integration.md): document/tutor/rag 파트와 같은 서버로 합칠 때의 기준

## 2. 품질 기준 문서

- [problem-feedback-quality-application-plan.md](problem-feedback-quality-application-plan.md): 문제 품질, 고난도 출제, 비용 기준
- [problem-feedback-advanced-research-roadmap.md](problem-feedback-advanced-research-roadmap.md): 다음 제품 고도화 연구와 구현 후보
- [problem-feedback-human-tone-strategy.md](problem-feedback-human-tone-strategy.md): 피드백 문체 기준

## 3. 기획과 참고 문서

- [problem-feedback-system-flow.md](problem-feedback-system-flow.md): 전체 서비스 흐름
- [product-ui-brief.md](product-ui-brief.md): UI 제작용 목적과 화면 요약
- [problem-feedback-pricing-cost-model.md](problem-feedback-pricing-cost-model.md): 가격, 모델 비용, 월정액 운영 가정
- [notebooklm-competitive-analysis.md](notebooklm-competitive-analysis.md): NotebookLM 경쟁 분석 참고 자료
- [problem-feedback-concepts.md](problem-feedback-concepts.md): 구현 전 핵심 개념 요약
- [problem-feedback-development-plan.md](problem-feedback-development-plan.md): 개발 계획 요약
- [../team-architecture-and-roles.md](../team-architecture-and-roles.md): 팀 역할 경계

## 유지 원칙

- 새 아이디어는 먼저 로드맵의 Phase 중 어디에 들어가는지 정한다.
- 팀 연동 필드는 `integration-contracts`에만 적는다.
- 제품 품질과 비용 판단은 `quality-application-plan`에만 적는다.
- 문체 관련 내용은 `human-tone-strategy`에만 적는다.
- 경쟁 분석과 가격 가정은 참고용이다. 출시 전에는 최신 가격과 기능을 다시 확인한다.
- 단순 연구 메모를 새 파일로 늘리지 않고, 위 문서 중 하나에 통합한다.
