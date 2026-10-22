# 저장소 작업 지침

프로젝트: Agentic Battlefield Intelligence Platform — 전장의 분석형 AI 플랫폼 PoC

## 현재 단계와 설계 기준

- **현재 STEP: 4. Review (Human).** 2026-10-22 실행 로그·핵심 주석 R1~R4 구현·검증 완료, 사용자 검토 대기다. docs/STEP.md가 단계 기준이며 Review/Reflect는 대신 수행하지 않는다.
- CRITICAL: 작업 시작 시 docs/STEP.md를 먼저 읽고 현재 단계와 수행 주체를 확인한다. 단계 상태의 기준은 docs/STEP.md이며 이 문서와 다르면 STEP.md를 따른다.
- 요구사항은 docs/PRD.md, 화면은 docs/UI_GUIDE.md, 서비스 경계는 docs/ARCHITECTURE.md를 따른다.
- Agent 실행은 docs/AGENT_DESIGN.md가 기준이다. 구현에 따른 주요 변경의 이유는 Implement에서 docs/ADR.md에 남긴다.
- 고도화 경계는 docs/SEMANTIC_ARCHITECTURE.md, 의미·매핑은 docs/ONTOLOGY_DESIGN.md, 비교·평가는 docs/SEMANTIC_DEMO.md를 따른다. 기존 단일 C4I 구현 기록과 목표 설계를 구분한다.


## 아키텍처 규칙

- CRITICAL: Mock ATCIS와 Mock KNCCS는 각각 자체 UI·Python 서버·시뮬레이터·DB·공개 API를 가지며 상대 체계·플랫폼·MCP·Neo4j·LLM·Node 없이 단독 실행 가능해야 한다. 합성 데이터와 가상 스키마만 사용한다. UI 빌드는 배포 전에 수행한다. 프론트엔드 외 실행 로직은 Python이다.
- CRITICAL: 현재 Agent는 Python 단일 동적 분석 Agent다. OpenAI native tool calling과 하나의 loop를 사용한다. 별도 Orchestrator·전문 Agent·위임·계획 워크플로를 구현하지 않는다.
- CRITICAL: Agent의 C4I 조회는 실제 MCP Python Client→MCP Python Server→공개 C4I API를 통한다. 원천 DB·내부 모듈·직접 REST로 우회하지 않는다.
- CRITICAL: Graph는 검증된 의미·관계·동일성 및 근거를 소유하고, 실시간 위치·상태는 원천 체계가 소유한다. 관계·동일성을 LLM 추측으로 Graph에 생성하지 않는다. OFF는 원천 native 도구와 일반 계산만 사용하며 Semantic 해석·관계 해소·동일성 판정 helper의 간접 호출도 금지한다. ON은 Semantic 근거의 해석을 추가 사용한다. ON/OFF 비교는 동일한 질문·원천 snapshot 집합을 사용한다. 정책이 다른 과거 대화/대기 run을 새 정책에 자동 재사용하지 않는다.
- 기본 native 데모는 c2-domain-demo-v3와 독립 fixture/gold를 따른다. 동일 객체의 상태·배속 데이터를 의도적으로 상충시키지 않는다. S8/v2와 과거 v1 충돌 시연·평가는 호환/역사 기록으로 보존하며 v3 기대값과 혼용하지 않는다.


## 개발 프로세스

- CRITICAL: 먼저 사용자 요청이 **단계 수행 지시**, **단순 질의·논의**, **특정 파일 변경 지시** 중 무엇인지 구분한다. 단계명 언급만으로 수행 지시라고 간주하지 않는다.
  - 단계를 명시적으로 수행하라고 하면 해당 단계의 작업과 산출물까지 완료한다. 직전 단계가 끝났다는 이유로 다음 단계까지 진행하지 않는다.
  - 설명·의견·가능 여부·시나리오 아이디어 등 단순 질의에는 답변만 한다. 관련 파일을 읽거나 조사할 수 있지만 코드·문서·단계 상태를 자동 변경하지 않는다.
  - 특정 파일의 작성/수정을 요청하면 그 범위만 변경한다. 이를 프로젝트 전체의 단계 전환이나 다른 spec 동기화 지시로 확대하지 않는다.
- CRITICAL: docs/STEP.md의 역할을 따른다. 초기 Design 후에는 Plan → Implement → Review → Reflect 루프를 반복한다.

| 단계 | 수행 내용 | 문서 수정 범위 |
| --- | --- | --- |
| Design (Human+AI) | 요구사항·설계를 함께 논의하고 합의한다. | 논의만 요청하면 답변만 한다. spec 작성/수정을 명시적으로 요청한 경우 해당 문서에 반영한다. |
| Plan (AI+Human) | 관련 spec과 현재 구현을 읽고 구현 범위·순서·테스트·완료 조건을 계획한다. | **docs/IMPLEMENTATION_PLAN.md만 수정한다.** PRD·아키텍처·Agent/UI/Ontology 설계·ADR·README 등 다른 문서에 계획을 분산 기록하지 않는다. |
| Implement (AI) | PLAN에 따라 테스트를 먼저 작성하고 구현해 통과시킨다. | 코드·테스트와 실제 결과를 docs/IMPLEMENTATION_REPORT.md에 기록한다. 구현에 영향받은 spec·ADR·실행 안내 등을 필요한 범위에서 정합화하고 PLAN의 실제 진행 상태를 갱신한다. |
| Review (Human) | 사용자가 구현을 검토하고 docs/REVIEW.md에 결과를 남긴다. | AI가 REVIEW.md를 대신 작성하거나 Review를 완료 처리하지 않는다. 검토 중 질의에는 답변하며 수정은 별도 지시 범위를 따른다. |
| Reflect (AI, into plan) | 사용자 Review를 읽고 피드백·후속 작업을 다음 계획에 반영한다. | **docs/IMPLEMENTATION_PLAN.md만 수정한다.** REVIEW 원문·다른 spec·코드는 변경하지 않는다. |

- CRITICAL: **읽을 문서와 수정할 문서를 구분한다.** Plan/Reflect에서도 관련 spec을 읽어야 하지만, 읽거나 새로운 설계 필요성을 발견했다는 이유로 해당 spec을 수정하지 않는다. 필요한 spec 변경은 PLAN의 후속 Implement 항목에 남긴다.
- CRITICAL: **PLAN은 현재 유효한 구현 계획만 유지한다.** Plan/Reflect에서 PLAN을 수정할 때 과거 계획·완료 내역을 계속 누적하지 않고 다음 구현의 기준으로 정리한다.
