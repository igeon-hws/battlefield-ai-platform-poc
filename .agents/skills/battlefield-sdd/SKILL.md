---
name: battlefield-sdd
description: Follow the repository SDD workflow for battlefield-ai-platform-poc design, planning, implementation, and reflection, while keeping its eight canonical documents consolidated. Use for project work; ordinary questions only require an answer.
---

# Battlefield SDD

저장소 루트의 AGENTS.md와 docs/STEP.md를 먼저 읽는다. 아래 경로는 모두 저장소 루트 기준이다. 이 skill은 단계별 행동을 안내하며 새로운 단계나 외부 작업의 권한을 부여하지 않는다.

## 요청과 읽기 범위

1. 현재 STEP/수행 주체와 사용자 요청을 확인한다. 단계 수행 지시인지, 설명/논의인지, 특정 파일 변경인지 구분한다. 단계명을 언급했다는 이유만으로 전환하지 않는다.
2. 요구는 docs/PRD.md, 기술은 docs/ARCHITECTURE.md, 화면은 docs/UI_GUIDE.md, 결정 이유는 docs/ADR.md를 필요한 범위에서 읽는다. 현재 구현과 docs/IMPLEMENTATION_STATUS.md도 대조한다.
3. 읽을 문서와 수정할 문서를 구분한다. 단순 질의는 답변만 한다. 특정 파일 요청은 그 범위만 변경하고 단계 전환으로 확대하지 않는다.

## 단계별 수행

- **Design:** 사용자와 요구/설계를 논의한다. spec 작성·수정을 요청한 경우에만 해당 문서에 반영한다. 구현을 시작하지 않는다.
- **Plan:** spec·실제 코드를 읽고 범위/제외 범위·순서/의존성·먼저 실패시킬 테스트·검증 방법·완료 조건을 docs/IMPLEMENTATION_PLAN.md에만 쓴다. 필요한 spec 변경도 후속 Implement 항목으로 둔다.
- **Implement:** PLAN을 읽고 테스트 먼저 작성→관련 실패 확인→구현→관련 검사 통과까지 완료한다. 변경에 맞는 계약/단위/실제 MCP·Neo4j/UI 검증을 선택한다. 비용이 드는 live 검증은 기존 사용자 권한 범위에서만 수행한다. 실패/미검증을 숨기지 않는다. 실제 결과·환경·한계는 docs/IMPLEMENTATION_STATUS.md, 변경 이유는 ADR, 영향받은 기술/요구/화면은 기존 문서에 정합화한다. PLAN은 실제 진행 상태를 갱신한다. 시작/인계 단계 표시는 STEP과 AGENTS를 함께 맞춘다.
- **Review:** 사용자 소유다. AI는 docs/REVIEW.md를 대신 작성하거나 Review를 완료하지 않는다. 검토 중 질문에는 답하고 별도 수정 지시만 그 범위에서 수행한다.
- **Reflect:** 사용자 REVIEW와 실제 구현을 읽고 피드백의 해결 지점·검증·완료 조건을 다음 PLAN에만 반영한다. REVIEW 원문·코드·다른 spec을 변경하지 않는다.

명시된 단계의 산출물까지 완료하되 다음 단계로 자동 진행하지 않는다. 구현 후에는 Human Review 대기로 인계하며 Reflect는 사용자 지시 후 수행한다. Plan/Reflect에서는 PLAN 외 파일·단계 상태를 자동 변경하지 않는다.

## 문서 유지와 완료 확인

- docs의 유지 파일은 ADR.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, IMPLEMENTATION_STATUS.md, PRD.md, REVIEW.md, STEP.md, UI_GUIDE.md뿐이다. 별도 Agent/Ontology/데모/보고 문서나 문서 archive를 만들지 않는다.
- PLAN은 다음 유효 작업만 유지한다. 완료 이력을 누적하지 않는다. 실제 결과와 주요 이력은 STATUS로 정리하되 다른 단계의 요청에서 임의로 STATUS를 바꾸지 않는다. 승인된 다음 일이 없으면 PLAN에 그 사실을 표시한다.
- 기술 상세는 ARCHITECTURE, 시나리오/평가 요구는 PRD, 시각/상호작용은 UI_GUIDE, 선택 이유는 ADR에 한 번만 쓴다. 중복 복사 대신 링크한다.
- 결과 보고에는 변경 이유·실제 검사·미완료/제약을 구분한다. 과거 통과 기록을 새 검증으로 쓰지 않는다. 문서만 바꾸면 링크/참조·현재/과거 구분을 확인하고 불필요한 제품 회귀를 새로 돌리지 않는다.
