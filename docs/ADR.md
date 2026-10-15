# Architecture Decision Records

- 기준: [아키텍처 초안](./ARCHITECTURE.md)
- 작성일: 2026-10-15
- 상태는 사용자 요구사항에 따른 확정 원칙과 검토 전 설계 제안을 구분한다.

## ADR-001: Mock C4I의 독립 제공

- 상태: 확정 요구사항
- 근거: 사용자 지시 — Mock C4I도 단독으로 제공될 수 있어야 하며 MCP 연동이 분명하게 드러나야 한다.
- 결정: 자체 UI·서버·시뮬레이터·DB·공개 REST/SSE를 가진 독립 배포 단위로 만든다. 분석 플랫폼·MCP·LLM 없이 실행 가능해야 한다.
- 이유: 외부 C4I와 분석 플랫폼의 경계를 실제 실행 환경으로 검증한다.
- 트레이드오프: 단일 앱보다 실행 단위와 설정이 늘어난다.
- 검증: 독립 배포물을 별도 폴더에서 실행하고 두 외부 서비스 없이 이동·상태 변경·API를 확인한다.

## ADR-002: MCP 어댑터 분리와 실제 네트워크 호출

- 상태: 제안
- 결정: MCP Server는 C4I의 공개 읽기 API만 사용하며 Streamable HTTP로 도구를 제공한다. Agent의 C4I 조회는 MCP Client를 통한다.
- 이유: 내부 함수 호출을 MCP 연동으로 오인하지 않게 하고 C4I의 내부 구현과 결합을 피한다.
- 대안: C4I 서버 내부에 MCP를 포함하면 프로세스는 줄지만 독립 경계가 덜 명확하다.
- 트레이드오프: 어댑터 프로세스·인증·네트워크 오류 처리가 추가된다.
- 검증: tools/list와 tools/call을 실제 연결로 수행한다. MCP 종료 시 직접 REST 우회 없이 분석 조회가 실패해야 한다.

## ADR-003: 상황판 동기화와 Agent 조회의 분리

- 상태: 제안
- 결정: 상황판은 C4I REST + SSE를 수집한 projection을 사용하고 Agent는 MCP로 조회한다.
- 이유: 초 단위 이동 표시와 LLM 분석의 실행 주기를 분리한다.
- 트레이드오프: 연결 상태와 데이터 기준 시점을 경로별로 관리해야 한다.
- 검증: MCP 중단 중에도 지도는 갱신되고, UI에는 수집 연결과 MCP 상태가 별도로 표시된다.

## ADR-004: 서버 소유의 장기 실행 작업

- 상태: 제안
- 결정: C4I 시뮬레이터는 C4I 서버에, 수집·영속 큐·Agent 워커는 Platform API에 둔다. React·Vite UI는 정적으로 빌드하고 각 Python FastAPI 서버가 제공한다.
- 이유: 브라우저나 단일 HTTP 요청의 수명에 자동 분석·시뮬레이션이 종속되지 않게 한다.
- 트레이드오프: Python ASGI 장기 실행 서버 운영이 필요하며 서버리스만으로 배포할 수 없다.
- 검증: 브라우저를 닫은 상태에서도 이벤트로 자동 분석이 실행된다. 플랫폼을 종료해도 C4I는 이동한다.

## ADR-005: 불변 snapshot과 실행별 근거 고정

- 상태: 제안
- 결정: C4I는 revision별 snapshot을 보관한다. C4I 정보가 처음 필요할 때 MCP로 기준 snapshot을 확보하고 후속 조회의 시점을 검증한다. 이벤트 실행은 원인 snapshot을 사용하며 일반 직접 답변은 snapshot 없이 완료할 수 있다.
- 이유: 움직이는 객체의 서로 다른 시점을 한 분석에 무의식적으로 섞는 문제를 줄인다.
- 트레이드오프: snapshot 저장 용량과 보관 정책이 필요하다. 결과가 현재 상황과 다른 시점임을 UI에 표시해야 한다.
- 검증: 실행 중 객체가 움직여도 모든 시점 고정 조회가 동일 기준을 유지한다. snapshot이 사라지면 최신 데이터로 대체하지 않고 실패를 표시한다.

## ADR-006: 이전 Multi-Agent 제안 폐기

- 상태: superseded — ADR-010으로 대체
- 근거: 사용자가 이번 PoC를 단일 동적 분석 Agent·native tool calling·간단한 멀티턴/하네스로 변경했다.
- 결정: 이전 Orchestrator·전문 Agent·계획/위임·컨텍스트 전달 설계는 현재 구현 기준에서 제외한다. 현재 기준은 [AGENT_DESIGN.md](./AGENT_DESIGN.md)다.

## ADR-007: 단일 호스트 SQLite 저장소

- 상태: 제안
- 결정: 서비스별 SQLite를 사용한다. 초기 평면 좌표·SVG 지도 제안은 사용자의 지리 지도 요구에 따라 ADR-008로 대체한다.
- 이유: 외부 DB 없이 독립 데모와 영속 이력 검증을 가능하게 한다.
- 트레이드오프: 다중 replica 쓰기를 지원하지 않는다. 후속 운영 요구 시 저장소 어댑터를 교체한다.
- 검증: 재시작 후 큐·실행 이력을 확인하고 고정 시계로 벡터 계산을 검증한다.

## ADR-008: 지리 지도와 적아 벡터 객체

- 상태: 지리 지도·적아 벡터 객체는 확정 요구사항, 세부 기술은 제안
- 결정: 원천은 WGS84 경위도와 동·북 방향 m/s 벡터로 표현한다. MapLibre GL JS의 GeoJSON 레이어로 적아 심벌·이동 선을 렌더링하고 C4I Python 서버가 매초 pyproj.Geod 기반 WGS84 이동을 계산한다. 표시 벡터 끝점도 Python이 계산한다. 소속·운용 상태·AI 위험 평가를 분리한다.
- 이유: 실제 위치 맥락과 벡터 이동을 두 시스템에서 일관되게 확인한다.
- 트레이드오프: 배경 지도 네트워크·출처 표기·지리 계산·투영 처리가 추가된다. 지도 공급자는 교체 가능하게 하고 장애를 C4I 장애와 구분한다.
- 검증: 적아 색·형태 구분, 경위도 순서·단위, 네 방향 이동, 지도 회전·줌 후 벡터 일치, 단독 C4I 지도 실행을 확인한다.

## ADR-009: OpenAI GPT API와 앱 소유 실행 loop

- 상태: OpenAI Provider는 확정 요구사항, Responses API 브리지는 제안
- 결정: 공식 OpenAI Python SDK·Responses API로 단일 Agent의 native 함수 호출과 구조화 결과를 받는다. 함수 호출은 얇은 Runtime이 검증한 후 실제 MCP Python Client 또는 Python 로컬 계산으로 연결한다. 구체 GPT 모델은 설정으로 선택한다.
- 이유: localhost MCP에 OpenAI 서버가 직접 접속할 필요 없이 허용 Tool·실제 호출·근거를 플랫폼이 관리한다.
- 트레이드오프: function_call_output·대화 상태·예산·오류 처리를 앱이 관리한다. 최근 대화와 현재 run의 입력만 유지하고 별도 컨텍스트 전달 계층은 두지 않는다.
- 검증: 실제 OpenAI→함수 요청→MCP 호출→근거→답변 연결, call_id 대응, 대화 격리·권한 거부·run 예산·불완전 응답 처리를 확인한다.

## ADR-010: 단일 Agent·native tool calling·최소 하네스

- 상태: 단일 Agent 전환은 확정 요구사항, 구체 모듈·상한은 제안
- 결정: 하나의 상황 분석 Agent가 OpenAI native function calling으로 조회·관찰·추가 호출·답변 loop를 수행한다. 직접 답변도 허용한다. 별도 계획·위임·완료 제어 Tool은 두지 않는다.
- 멀티턴: 최근 완료 질문·답변을 conversationId로 연결하고 질문마다 새 run을 만든다. 현재 C4I 사실은 새 MCP 조회로 확보한다.
- 하네스: agent.py·loop.py·tools.py·conversation.py와 SDK 어댑터로 제한한다. 일반 Agent 프레임워크·장기 기억·Artifact/ContextPacket 계층은 이번 범위에서 제외한다.
- 이유: 실제 Tool 선택과 다단계 조회를 핵심으로 검증하면서 조율·컨텍스트 관리 복잡도를 줄인다.
- 트레이드오프: 역할별 독립 평가·병렬 전문 분석·장기 대화 복구는 제공하지 않는다. 긴 요청은 명확화·부분 결과 또는 실행 제한으로 처리할 수 있다.
- 검증: 직접 답변·native function_call/call_id 대응·관찰에 따른 추가 조회·간단한 후속 질문·시점 고정·실행 제한·유효한 세 방책을 확인한다.
- 상세: [AGENT_DESIGN.md](./AGENT_DESIGN.md).

## ADR-011: 프론트엔드 외 Python 구현

- 상태: Python 언어 경계는 확정 요구사항, 라이브러리·배포 세부는 제안
- 근거: 사용자가 프로젝트를 Python 프로젝트로 지정했다.
- 결정: C4I·MCP Server/Client·분석 API·Agent·시뮬레이터·지리 계산·작업 큐·DB 접근은 Python으로 구현한다. API는 FastAPI/Uvicorn, 비동기는 asyncio/HTTPX, 검증은 Pydantic, LLM·MCP는 각 공식 Python SDK를 사용한다.
- 프론트엔드: React·TypeScript·Vite만 Node 빌드 도구를 사용한다. UI 정적 파일을 각 Python 서버에 포함해 운영 Node 서버·SSR·BFF는 두지 않는다.
- 패키지·검증: uv workspace·Python wheel·uv.lock, pytest/pytest-asyncio·Ruff·mypy를 사용한다. E2E는 Playwright Python으로 수행한다.
- 계약: Pydantic이 원본이며 OpenAPI/JSON Schema로 UI용 TS 타입을 생성한다. 원천 이동·지리 계산을 양쪽 언어로 중복 구현하지 않는다.
- 영향: 이전 서버 언어·Node 서버·공통 TypeScript 런타임 제안은 본 결정으로 대체한다. 단일 Agent·독립 C4I·실제 MCP·지리 지도·방책 UI 요구는 유지한다.
- 트레이드오프: Python/UI 빌드 도구와 계약 생성 단계를 별도로 관리한다. UI 빌드가 포함된 Python 배포물 검증이 필요하다.
- 검증: Node 없는 환경의 C4I 단독 실행·세 Python 서비스 통합·정적 자산/API/SSE 경계·계약 일치·Python 비동기 loop를 확인한다.

## ADR-012: 객체 유형·가용 상태 분리와 원천 집계

- 상태: 유형 구분·가용 조회·적 탱크 수 분석은 사용자 요구사항, 코드·상태 enum·집계 계약은 제안
- 결정: kind는 tank / naval_vessel / unknown을 초기 지원한다. affiliation·status·availability를 분리하고 가용 상태는 C4I 원천의 available / unavailable / unknown 값으로 조회한다.
- 조회: 목록과 집계는 같은 EntityFilter와 snapshot을 사용한다. c4i_summarize_entities는 공개 C4I 집계 API를 MCP로 노출하고 실제 합산은 Python 서버가 수행한다.
- 이유: 탱크·함정을 구분하고 가용 장비 조회와 적 탱크 수를 재현 가능한 근거로 답한다. 이동 상태·이름 문자열·페이지 개수로 소속·유형·가용성·전체 수를 추측하지 않게 한다.
- 트레이드오프: 원천의 가용성·유형 분류를 초기 시나리오에 명시하고 미확인 상태와 집계 범위를 UI·답변에 표시해야 한다.
- 검증: 가용 아군 탱크 목록·적 탱크 수·함정 제외·미확인·0건·페이지 전체 일치 수·가용 상태 변경 후 새 snapshot 집계 일치를 확인한다.

## 후속 확정 항목

정확한 패키지 버전, GPT 모델 ID, 지도 공급자·초기 지역, 상태 전이·시나리오·객체 규모, 자동 이벤트 범위, 제안된 실행 예산의 튜닝, 이력 보관과 선택 변경 정책은 아키텍처 13절에 따라 후속 Design에서 결정한다. 실제 지리 지도·적아 객체·OpenAI Provider는 미정 항목에서 제외한다.


