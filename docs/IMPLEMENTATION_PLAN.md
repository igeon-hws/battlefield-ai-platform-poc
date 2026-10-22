# 구현 계획 — Agent 실행 로그와 핵심 로직 주석

상태: **R1~R4 구현·검증 완료 · Human Review 대기** (2026-10-22).
입력은 [REVIEW](./REVIEW.md)의 “에이전트 실행 기록 로그 파일(알아보기 쉽게)”, “코드 중요한 부분 주석”이다. 단계 상태는 [STEP](./STEP.md)을 따른다.

완료한 구현 순서·계약·실제 결과는 [구현 보고서](./IMPLEMENTATION_REPORT.md)의 R1~R4 절, 사용법은 [README](../README.md), 실행 설계는 [AGENT_DESIGN](./AGENT_DESIGN.md), 결정은 [ADR-024](./ADR.md)에 반영했다. 완료 체크리스트와 과거 C0~C7 계획은 이 문서에 누적하지 않는다.

## 현재 인계

| Review 항목 | 구현 결과 |
| --- | --- |
| 읽기 쉬운 실행 파일 로그 | 실행별 UTF-8 파일, 질문/모드/기준·discovery·모델/도구·근거·최종 상태·오류 기록. 마스킹/생략·취소/복구·I/O 실패 격리 포함 |
| 핵심 로직 주석 | Agent loop, OFF/ON·snapshot/evidence/페이지 경계, Fabric/Graph·비교 격리, UI 자체 ID와 문서 참조의 차이를 설명 |

검증은 일반 136개, 실제 MCP/Neo4j 통합 1개와 최종 관련 37개를 수행했다(서로 겹치는 회귀를 합산하지 않음). Ruff/format/mypy/diff check를 통과했다. 프론트는 주석만 변경했고 실제 GPT 호출을 추가하지 않았다.

## 사용자 Review 확인 지점

- 플랫폼을 재시작한 뒤 `var/logs/agent/<runId>.log`에서 실행 흐름을 이해할 수 있는지 확인한다.
- 예시 `var/logs/agent/sample-fixture-8ed0fa2ea488.log`는 합성 fixture provider로 만든 가독성 예시다. 실제 GPT 결과로 간주하지 않는다.
- 긴 결과는 8,000자에서 생략하며 전체 근거는 DB/UI trace가 기준이다. 자동 로그 삭제는 없고 I/O 실패는 stderr 경고로 확인한다.
- 핵심 주석이 코드의 판단 이유를 설명하는지 검토한다.

새 구현 작업은 아직 계획하지 않는다. 사용자 Review 뒤 명시적 Reflect 지시를 받으면 이 PLAN을 다음 유효 작업으로 갱신한다. AI가 사용자 REVIEW를 작성하거나 완료 처리하지 않는다.
