# 저장소 작업 지침

프로젝트: Agentic Battlefield Intelligence Platform — 전장의 분석형 AI 플랫폼 PoC

## 현재 단계와 설계 기준

- **현재 STEP: 4. Review (Human), S8 구현·검증 완료·사용자 검토 대기** — S8-1~5와 일반 97개·Neo4j 9개·실제 GPT 검증/한계를 구현 보고서에 기록했다. docs/STEP.md의 `Now`가 기준이다. 사용자 Review를 대신하거나 다음 Reflect를 임의로 시작하지 않는다.
- CRITICAL: 작업 시작 시 docs/STEP.md를 먼저 읽고 현재 단계와 수행 주체를 확인한다. 단계 상태의 기준은 docs/STEP.md이며, 이 문서의 현재 STEP 표시와 다르면 docs/STEP.md를 따른다.
- 요구사항은 docs/PRD.md, 화면은 docs/UI_GUIDE.md, 서비스 경계는 docs/ARCHITECTURE.md를 따른다.
- Agent 실행은 docs/AGENT_DESIGN.md가 기준이다. 주요 변경의 이유는 docs/ADR.md에 남긴다.
- 고도화 경계는 docs/SEMANTIC_ARCHITECTURE.md, 의미·매핑은 docs/ONTOLOGY_DESIGN.md, 비교·평가는 docs/SEMANTIC_DEMO.md를 따른다. 기존 단일 C4I 구현 기록과 목표 설계를 구분한다.


## 아키텍처 규칙

- CRITICAL: Mock ATCIS와 Mock KNCCS는 각각 자체 UI·Python 서버·시뮬레이터·DB·공개 API를 가지며 상대 체계·플랫폼·MCP·Neo4j·LLM·Node 없이 단독 실행 가능해야 한다. 합성 데이터와 가상 스키마만 사용한다. UI 빌드는 배포 전에 수행한다. 프론트엔드 외 실행 로직은 Python이다.
- CRITICAL: 현재 Agent는 Python 단일 동적 분석 Agent다. OpenAI native tool calling과 하나의 loop를 사용한다. 별도 Orchestrator·전문 Agent·위임·계획 워크플로를 구현하지 않는다.
- CRITICAL: Agent의 C4I 조회는 실제 MCP Python Client→MCP Python Server→공개 C4I API를 통한다. 원천 DB·내부 모듈·직접 REST로 우회하지 않는다.
- CRITICAL: Graph는 검증된 의미·관계·동일성 및 근거를 소유하고, 실시간 위치·상태는 원천 체계가 소유한다. 관계·동일성을 LLM 추측으로 Graph에 생성하지 않는다. OFF는 원천 native 도구와 일반 계산만 사용하며 Semantic 해석·관계 해소·동일성 판정 helper의 간접 호출도 금지한다. ON은 Semantic 근거의 해석을 추가 사용한다. ON/OFF 비교는 동일한 질문·원천 snapshot 집합을 사용한다. 정책이 다른 과거 대화/대기 run을 새 정책에 자동 재사용하지 않는다.
- 기본 데모의 동일 객체 상태·배속 데이터는 상충하지 않아야 한다. S8의 v2 데이터/기대값을 따르며 과거 v1 충돌 시연과 평가 기록은 역사적 기록으로 보존한다.


## 개발 프로세스

- CRITICAL: 새 기능 구현 시 반드시 테스트를 먼저 작성하고, 테스트가 통과하는 구현을 작성할 것(TDD).
- CRITICAL: docs/STEP.md의 순서와 역할을 따른다. 초기 Design 후에는 Plan → Implement → Review → Reflect 루프를 반복한다.
  1. Design (Human+AI): 요구사항과 설계 명세를 함께 작성한다.
  2. Plan (AI+Human): 구현 계획을 세워 docs/IMPLEMENTATION_PLAN.md에 반영한다.
  3. Implement (AI): 구현 계획에 따라 테스트를 먼저 작성하고, 구현 후 테스트 통과까지 완료하여 docs/IMPLEMENTATION_REPORT.md에 기록한다.
  4. Review (Human): 사용자가 검토하고 docs/REVIEW.md에 결과를 남긴다. AI가 사용자 Review를 대신하거나 임의로 완료 처리하지 않는다.
  5. Reflect (AI, into plan): 완료된 사용자 Review를 바탕으로 docs/IMPLEMENTATION_PLAN.md에 피드백과 후속 계획을 반영한다.
- 단계가 전환되면 docs/STEP.md의 상태와 AGENTS.md의 현재 STEP 표시를 함께 갱신한다. 다음 단계 작업을 임의로 시작하지 않는다.
- 커밋 메시지는 conventional commits 형식을 따른다(feat:, fix:, docs:, refactor:).

