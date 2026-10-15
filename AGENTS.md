# 저장소 작업 지침

프로젝트: Agentic Battlefield Intelligence Platform — 전장의 분석형 AI 플랫폼 PoC

## 현재 단계와 설계 기준

- 현재 SDD 단계는 Implement이다. (SDD 단계는 STEP.md를 따름)
- 요구사항은 docs/PRD.md, 화면은 docs/UI_GUIDE.md, 서비스 경계는 docs/ARCHITECTURE.md를 따른다.
- Agent 실행은 docs/AGENT_DESIGN.md가 기준이다. 주요 변경의 이유는 docs/ADR.md에 남긴다.


## 아키텍처 규칙

- CRITICAL: Mock C4I는 자체 UI·Python 서버·시뮬레이터·저장소를 포함해 플랫폼·MCP·LLM·Node 없이 단독 제공·실행 가능해야 한다. UI 빌드는 배포 전에 수행한다.
- CRITICAL: 현재 Agent는 Python 단일 동적 분석 Agent다. OpenAI native tool calling과 하나의 loop를 사용한다. 별도 Orchestrator·전문 Agent·위임·계획 워크플로를 구현하지 않는다.
- CRITICAL: Agent의 C4I 조회는 실제 MCP Python Client→MCP Python Server→공개 C4I API를 통한다. 원천 DB·내부 모듈·직접 REST로 우회하지 않는다.


## 개발 프로세스

- CRITICAL: 새 기능 구현 시 반드시 테스트를 먼저 작성하고, 테스트가 통과하는 구현을 작성할 것(TDD).
- docs/STEP.md의 Design → Implement → Review → Reflect 흐름을 따른다.
- 커밋 메시지는 conventional commits 형식을 따른다(feat:, fix:, docs:, refactor:).

