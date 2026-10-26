# 저장소 작업 지침

프로젝트: Agentic Battlefield Intelligence Platform — 전장의 분석형 AI 플랫폼 PoC.

## 현재 단계와 작업 순서

- **현재 STEP: 4. Review (Human).** 2026-10-26 Data Fabric Graph 탐색·버전 선택 구현/관련 검증 완료, 사용자 검토 대기. 단계의 기준은 [docs/STEP.md](docs/STEP.md)이며 불일치하면 STEP을 따른다. 검증 한계는 STATUS에 기록한다.
- 작업 시작 시 STEP을 먼저 읽고 요청을 단계 수행 / 단순 질의 / 특정 파일 변경으로 구분한다. 명시한 단계까지만 수행한다. 단순 질의는 답변만, 특정 파일 변경은 해당 범위만 한다.
- SDD 작업에는 [battlefield-sdd SKILL](.agents/skills/battlefield-sdd/SKILL.md)을 읽고 적용한다. 초기 Design 이후 Plan→Implement→Review→Reflect를 따른다.
- Plan/Reflect는 **IMPLEMENTATION_PLAN만** 수정한다. PLAN은 현재 유효한 다음 작업만 유지하며 완료 내역은 STATUS에 둔다. Implement는 테스트 먼저 작성→실패 확인→구현→관련 검사 통과까지 수행한다.
- Review 작성/완료는 사용자 몫이다. 사용자 Review 후 명시적 Reflect 지시에 따라 PLAN에 반영한다. 직전 단계 완료만으로 다음 단계를 수행하지 않는다.

## 문서 지도

docs에는 아래8개만 유지한다. 역할별 설계·보고·시나리오 문서를 새로 만들지 않는다. README는 진입 링크, AGENTS/SKILL은 작업 지침만 담당한다.

| 문서 | 책임 |
| --- | --- |
| [STEP](docs/STEP.md) | 단계·주체·수정 범위 |
| [PRD](docs/PRD.md) | 목표·범위·요구사항·데모/평가 |
| [UI_GUIDE](docs/UI_GUIDE.md) | 화면·시각·상호작용 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 모든 기술 설계·Agent·Ontology·MCP·실행/검증 안내 |
| [ADR](docs/ADR.md) | 주요 기술 결정의 이유·대가 |
| [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) | 현재 유효한 다음 구현 계획 |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | 실제 결과·검증·한계·요약 이력 |
| [REVIEW](docs/REVIEW.md) | 사용자의 검토 원문 |

## 핵심 구현 경계

- Mock ATCIS/KNCCS는 각각 UI·Python 서버·DB·시뮬레이터를 가지며 타 서비스 없이 단독 실행한다. 합성 데이터/가상 schema, 프론트 외 Python, Node는 UI 빌드에만 사용한다.
- 하나의 Python 분석 Agent와 OpenAI native tool loop를 사용한다. 별도 Orchestrator·전문 Agent·위임·계획 워크플로를 구현하지 않는다.
- Agent 원천 조회는 실제 MCP Client→Server→공개 API다. DB/내부 모듈/직접 REST로 우회하지 않는다.
- Graph는 검증된 의미·관계·동일성/근거, 원천은 live 위치/상태를 소유한다. LLM 추측으로 Graph 관계를 생성하지 않는다.
- OFF는 native 도구/원천 문서/일반 계산만 사용하며 Semantic helper 간접 호출도 금지한다. ON/OFF는 같은 질문/snapshot 집합이며 대화/정책을 격리한다. OFF 모델의 올바른 원천 해석은 허용한다.
- 기본은 c2-domain-demo-v3와 독립 fixture/gold다. v1/v2/legacy 기대값을 혼용하거나 동일 자산 상태를 의도적으로 상충시키지 않는다. 코드·문서·실제 측정·미검증 제안을 구분한다.
