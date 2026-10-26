# STEP — Spec-Driven Development

**현재 STEP: 4. Review (Human).** 2026-10-22 실행 로그·핵심 주석 R1~R4 구현/검증 완료, 사용자 검토 대기. 결과는 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)에 있다. 2026-10-26 문서 통합은 특정 파일 정리 요청이며 단계 전환이 아니다.

## 단계와 산출물

| 순서 | 주체 | 수행 내용 | 문서 수정 범위 |
| --- | --- | --- | --- |
| 1. Design | Human+AI | 요구·설계를 논의/합의 | 작성/수정을 요청한 PRD·ARCHITECTURE·UI_GUIDE 등만 |
| 2. Plan | AI+Human | spec/현황을 읽고 범위·순서·선행 테스트·완료 조건 계획 | IMPLEMENTATION_PLAN만 |
| 3. Implement | AI | PLAN에 따라 테스트 먼저 작성→실패 확인→구현→관련 검사 통과 | 코드/테스트, STATUS, PLAN 진행 상태, 영향받은 spec/ADR |
| 4. Review | Human | 사용자가 구현 검토·REVIEW 작성 | AI는 대신 작성/완료 처리하지 않음 |
| 5. Reflect | AI, into plan | 사용자 REVIEW를 후속 유효 계획에 반영 | IMPLEMENTATION_PLAN만 |

초기 Design 이후 Plan→Implement→Review→Reflect를 반복한다. 단계는 사용자의 명시적 지시 범위에서 수행하며 다음 단계로 자동 진행하지 않는다. 단순 질의는 답변만, 특정 파일 변경은 그 범위만 수행한다. 단계명 언급만으로 수행 지시라고 판단하지 않는다.

Plan/Reflect는 관련 문서를 읽되 PLAN 외 문서를 수정하지 않는다. 필요한 spec 변경을 다음 Implement 항목으로 남긴다. PLAN에는 현재 유효한 다음 작업만 두며 완료 이력은 STATUS로 옮긴다. 다음 승인 작업이 없으면 그 사실만 표시한다.

Implement 시작/검증 완료 후 인계 때 이 문서와 AGENTS의 현재 단계 표시를 함께 갱신한다. 완료 시 Human Review 대기로 두며 Review/Reflect를 대신 수행하지 않는다. Plan/Reflect 또는 설명 요청을 이유로 단계 표시까지 자동 변경하지 않는다. 사용자가 단계 상태 갱신을 별도로 명시하면 그 지시 범위에서 반영한다.

## 유지할 문서

docs에는 PRD, UI_GUIDE, ARCHITECTURE, ADR, IMPLEMENTATION_PLAN, IMPLEMENTATION_STATUS, REVIEW, STEP의8개만 유지한다. 기술 설계는 ARCHITECTURE, 실제 결과/제약은 STATUS, 결정 이유는 ADR이다. 역할별 별도 설계/보고/시나리오 문서를 추가하지 않는다. README는 진입 링크, AGENTS와 저장소 SKILL은 작업 지침만 담당한다.
