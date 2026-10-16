# 저장소 작업 지침

프로젝트: Agentic Battlefield Intelligence Platform — 전장의 분석형 AI 플랫폼 PoC

## 현재 단계와 설계 기준

- **현재 STEP: 4. Review (Human), R6–R7 구현 완료·사용자 검토 대기** — docs/STEP.md의 `Now` 기준.
- CRITICAL: 작업 시작 시 docs/STEP.md를 먼저 읽고 현재 단계와 수행 주체를 확인한다. 단계 상태의 기준은 docs/STEP.md이며, 이 문서의 현재 STEP 표시와 다르면 docs/STEP.md를 따른다.
- 요구사항은 docs/PRD.md, 화면은 docs/UI_GUIDE.md, 서비스 경계는 docs/ARCHITECTURE.md를 따른다.
- Agent 실행은 docs/AGENT_DESIGN.md가 기준이다. 주요 변경의 이유는 docs/ADR.md에 남긴다.


## 아키텍처 규칙

- CRITICAL: Mock C4I는 자체 UI·Python 서버·시뮬레이터·저장소를 포함해 플랫폼·MCP·LLM·Node 없이 단독 제공·실행 가능해야 한다. UI 빌드는 배포 전에 수행한다.
- CRITICAL: 현재 Agent는 Python 단일 동적 분석 Agent다. OpenAI native tool calling과 하나의 loop를 사용한다. 별도 Orchestrator·전문 Agent·위임·계획 워크플로를 구현하지 않는다.
- CRITICAL: Agent의 C4I 조회는 실제 MCP Python Client→MCP Python Server→공개 C4I API를 통한다. 원천 DB·내부 모듈·직접 REST로 우회하지 않는다.


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

