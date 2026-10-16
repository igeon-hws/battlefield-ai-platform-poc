# Architecture Decision Records

- 기준: [아키텍처 초안](./ARCHITECTURE.md)
- 작성일: 2026-10-15
- 상태는 사용자 요구사항에 따른 확정 원칙과 검토 전 설계 제안을 구분한다.

## 2026-10-16 고도화 결정 — ADR-017~022

아래는 v0.5 Design 입력에 대한 결정/제안이다. ADR-001~016은 이전 baseline의 이력이며 상충하는 단일 원천·단일 snapshot·전체 SQLite 한정 전제는 아래 범위에서 대체한다. 단일 Python Agent/native loop 원칙은 유지한다.

### ADR-017: 두 개의 독립 합성 C4I

- 상태: 사용자 확정 요구사항.
- 결정: Mock ATCIS/KNCCS를 각각 UI·Python API·DB·시뮬레이터·MCP 경계로 제공한다. 실제 내부 구조를 모사하지 않고 가상 스키마를 사용한다.
- 이유/영향: 이종 연동과 원천 독립성을 시연한다. 실행 단위는 늘어나지만 기존 C4I/지도/SDK 코드를 재사용한다. ADR-001/002를 원천별로 확장한다.
- 검증: 다른 원천·플랫폼·Neo4j·LLM 없는 독립 배포 실행 및 실제 MCP HTTP 조회.

### ADR-018: Ontology·Builder·Graph·Semantic 서비스 분리

- 상태: 분리·Neo4j/Python 공식 driver는 사용자 확정 요구사항. Python core + API + 별도 thin MCP 프로세스는 설계 제안.
- 결정: Git 관리 의미 규칙 → Python Builder → Neo4j → Semantic API → Semantic MCP로 책임을 나눈다. MCP를 Ontology 정의/저장 자체로 취급하지 않는다.
- 이유/영향: Agent 밖에서도 의미 해석을 재사용하고 도구 설명과 지식 규칙을 분리한다. 기존 SQLite는 원천/플랫폼에 유지하며 관계 저장용 Neo4j를 추가한다(ADR-007 범위 확장).
- 검증: API/MCP 같은 결과, 원천 live 상태의 Graph 비복제, 무제한 Cypher/Graph 쓰기 도구 부재.

### ADR-019: 검증된 매핑과 결정론적 ER

- 상태: 근거 기반 관계·LLM 관계 생성 금지는 사용자 확정 요구사항. 구체 규칙은 설계 제안.
- 결정: 원천 조직/배속 데이터 및 검증된 연습 식별자/crosswalk로 관계를 생성한다. 이름 유사성은 확정 동일성으로 쓰지 않는다. unresolved/conflict와 모든 출처를 보존한다.
- 이유/영향: 설명 가능한 의미 연결을 얻는 대신 모호한 사례는 답을 유보한다.
- 검증: 중복 ID·동명·타입 충돌·누락 식별자 반례, 원천 근거 없는 edge 0건.

### ADR-020: 불변 Graph build와 원천 snapshot 집합

- 상태: 설계 제안. ADR-005의 불변 근거 원칙을 확장한다.
- 결정: graphVersion별 materialization, 검증 후 공개, 안정 관계 변경에만 rebuild한다. run은 원천별 snapshot 및 대응 Graph 버전을 고정한다.
- 이유/영향: 실시간 최신 Graph와 과거 상태를 섞지 않고 재현한다. 작은 PoC에는 단순하지만 build 저장량이 늘어 참조 기반 보관/정리가 필요하다.
- 검증: 중간 실패 비공개·재구축 중복 없음·reset/gap 복구·참조 build 보존·미래 관계 유입 0.

### ADR-023: Semantic 코드 실행 경계와 무충돌 v2 데이터 (S8)

- 상태: 사용자 Review 반영. ADR-021의 로컬 집계 동일 권한 정의 중 공유 의미 해석/ER 부분을 대체한다.
- 결정: OFF=원천 native 도구+일반 계산. Semantic 개념·상태/유형 해석·조직 해소·동일성 판정 helper의 간접 호출도 금지한다. ON은 실제 Semantic 근거의 sourceMappings·조직 범위·canonical 연결을 적용한다. 로컬 계산은 해석 규칙을 소유하지 않는다.
- 계약: 원천 목록/집계는 typeCode/statusCode native 필터, 일반 계산은 필드 빈도/동등 비교·합계. Semantic 집계는 identityEvidenceIds/conceptEvidenceIds 및 필요한 scopeEvidenceIds를 요구한다. 과거 정책 대화는 새 대화로 전환한다. run/manifest에 정책 2-native-off·원천 도구 계약 2를 기록한다.
- 데이터: semantic-demo-v2는 공유 UAV의 가용 상태·초기 위치/벡터·유형/소속을 일치시키고 비전속 공동지원 배속을 명시한다. S2 raw 8/unique 7/available 4/unavailable 2/unknown 1/conflicting 0. v1 DB/Graph/평가는 보존한다.
- 검증: 의미 helper를 예외로 막은 실제 source MCP 11종 조회와 OFF 계산/좌표, 정책별 history 격리, ON 실제 Semantic 근거·모든 관측/페이지 검사, 기본 seed 일관성. OFF 모델 추론 성공을 금지하지 않는다.

### ADR-021: 하나의 Agent와 실행별 Semantic capability (S8 이전 기록)

- 상태: 단일 native loop/모드별 도구는 사용자 확정 요구사항. namespace와 새 집계 도구는 설계 제안.
- 결정: OFF=원천 MCP만, ON=원천+Semantic MCP. 런타임이 신뢰 서버별 discovery/allowlist/bindings를 고정하고 단일 loop가 도구를 동적으로 선택한다. 원천 데이터를 다루는 로컬 read/geo/집계는 양 모드 동일 권한이다.
- 이유/영향: Semantic 기능을 Agent 수 증가와 혼동하지 않는다. 다중 MCP 이름 충돌과 과거 ON 컨텍스트 유출을 방지해야 한다.
- 검증: OFF Semantic 세션/근거 0, 실제 다중 MCP, 명시적 identity evidence 없는 중복 제거 거부.

### ADR-022: 같은 원시 정보·시점의 쌍 비교

- 상태: 같은 질문/snapshot 비교는 사용자 확정 요구사항. 빈 대화·소규모 fixture·반복 방식은 설계 제안.
- 결정: 공통 manifest로 두 격리된 run을 만들고 원시 조직/식별 정보는 OFF에도 공개한다. 원천/관계 근거·효율·정확성을 비교하며 OFF 실패를 전제하지 않는다.
- 이유/영향: 추가 비공개 데이터 효과와 의미 구조화 효과를 구분한다. LLM 변동성 때문에 단일 화면만으로 우수성을 일반화하지 않는다.
- 검증: 독립 gold, 동일 snapshot 집합, Graph hash/버전 일치, 반례 및 반복 측정. Graph 준비 시간과 모델 실행 시간을 분리한다.

상세 규칙은 [고도화 아키텍처](./SEMANTIC_ARCHITECTURE.md), [Ontology](./ONTOLOGY_DESIGN.md), [시연·평가](./SEMANTIC_DEMO.md)를 따른다.

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

## ADR-013: 대화 타임라인과 응답별 방책 선택

- 상태: 2026-10-15 Review의 R1–R3 기반 구현, 사용자 재검토 대기.
- 결정: conversationId는 대화, runId는 개별 질문·응답의 식별자로 사용한다. 비교 대상 runId를 활성 응답과 분리하고 선택은 `(runId, courseId)`에 저장한다. UI는 대화 전체를 표시하며 현재 대화 ID만 sessionStorage에 보관한다.
- 맥락: 최근 6턴·UTF-8 8,000바이트 한도 안에서 선택한 방책 ID·원문을 다음 질문에 전달한다. 과거 분석은 최신 C4I 사실과 구분한다. 대화 복원은 전역 실행 이력 200개 한도와 분리한다.
- 이유: 후속 질문과 SSE 갱신으로 비교·선택 대상이 바뀌는 결합을 제거하고 선택한 방책에 관한 후속 질문을 지원한다.
- 한계: 장기 기억이나 요약 메모리는 추가하지 않는다. 최근 이력 한도를 벗어난 정보는 모델 입력에서 제외될 수 있다.
- 검증: 3턴 대화·연속 선택·과거 응답 선택 변경·저장 실패 후 재시도·새로고침 복원, 실제 GPT의 선택 방책 후속 응답.

## ADR-014: 시스템 역할과 공유 도구 계약, 모의 객체 확장

- 상태: R4–R5 기반 구현, 사용자 재검토 대기. ADR-012의 유형·필터 범위를 확장한다.
- 결정: 시스템 프롬프트는 정체성·서비스 역할·동적 실행·근거 원칙을 담당한다. 개별 도구의 사용 조건·입출력·한계는 도구 설명과 schema에 둔다. c4i-contracts의 설명 상수를 MCP 검색과 native 어댑터가 공유한다.
- 객체: armored_vehicle·support_vehicle·uav와 선택적 세부 유형·부대·관측 시각·출처, 독립적인 maintenanceStatus를 추가한다. 과거 필드 누락은 null/unknown으로 해석하며 기존 snapshot과 DB를 자동 재작성하지 않는다.
- 도구: 단일 객체 관측 이력은 공개 C4I API와 c4i_list_entity_history로 제공한다. 고정 epoch·sequence 상한과 nextAfter 페이지 이동을 적용한다. 거리 비교는 기존 목록과 geo_measure를 조합한다.
- 이유: 시스템 프롬프트의 개별 도구 의존성을 줄이고 설명 불일치를 방지한다. 기존 조회·집계로 가능한 기능은 확장하여 중복 도구 추가를 줄인다.
- 한계: 이력은 변화가 없는 snapshot 관측도 포함하며 limit은 스캔 수다. 객체 수 증가에 따른 전용 공간 검색·이력 최적화는 이번 범위 밖이다.
- 검증: 실제 MCP 설명 일치·필터 집계·이력 페이지/빈 결과/미래 조회 거부·이전 DB 호환·신규 유형 UI·Node 없는 독립 wheel 실행.

## ADR-015: MCP 서버 소유 정의의 run별 발견

- 상태: R6 구현, 사용자 Review 대기. ADR-014의 공유 설명 상수 방식을 대체한다.
- 결정: MCP 서비스가 description과 typed 입력 schema를 소유한다. 플랫폼은 tools/list 전체 페이지에서 허용된 정의를 받아 native strict 함수로 변환하고 그 run에서 고정한다. 다음 run에 재발견하며 공통 도메인 패키지·플랫폼에 C4I 설명이나 호출 모델을 복사하지 않는다.
- 실패 정책: 발견 최대 5초, 실패하면 C4I capability 없이 일반 설명을 허용하고 한계를 기록한다. schema 변환 오류·이름 충돌은 실행 실패다. 임의 발견 도구의 자동 허용이나 로컬 복사 fallback은 없다.
- 이유: 독립 MCP 연동을 제품 경계로 드러내고 서버 계약 변경을 플랫폼 중복 수정 없이 반영한다. 내부 근거/지리 도구·snapshot 정책·실행 예산은 플랫폼 소유로 유지한다.
- 검증: 검색 pagination·설명 변경·모델 전달·인수 검증·실제 HTTP 호출·실제 GPT·연결 장애·run 내 고정.

## ADR-016: 시나리오 metadata와 접경 120개 seed

- 상태: R7 구현, 사용자 Review 대기.
- 결정: border-demo v1의 120개 합성 객체와 8개 시연 구역을 기본으로 한다. 원천 snapshot의 scenario metadata가 표시명·bounds·지도 초기 범위·구역을 제공하고, 시뮬레이터와 두 UI가 이를 따른다. zoneId 필터·집계를 제공한다.
- 호환성: 기존 DB와 과거 snapshot의 scenarioId·경계를 보존하고 초기화 때만 새 설정의 seed·epoch로 전환한다. 과거 cursor의 metadata 보완은 그 시점을 유지하여 미수집 상태 이벤트를 건너뛰지 않는다.
- 이유: 서해안 하드코딩을 제거하고 접경 전체를 탐색하는 데모와 100개 초과 페이지/규모 검증을 지원한다. 초기 좌표와 상태는 실제 배치 자료가 아닌 재현 가능한 합성 데이터다.
- 한계: 구역 경계에서 정지하는 단순 이동이며 실제 접경선·도로·지형·항로 추종 모델은 없다. 60초 로컬 지연 표본은 보고서에 기록하고 운영 성능으로 일반화하지 않는다.
- 검증: seed·구역·페이지/집계·이전 DB/epoch·원천/플랫폼 일치·브라우저·독립 wheel·60초 실행.

## 후속 확정 항목

### 고도화 실행 예산 조정 — 2026-10-16

초기 15쌍 비교에서 이종 체계 원시 관계를 조회하는 OFF가 12회 모델 호출 한도에 4회 걸렸다. 고도화 프로필은 model 24회/tool 20회/120초를 양 모드에 동일 적용하며 설정과 run/manifest에 기록한다. legacy loop 기본값은 유지한다. 예산 변경 전·후 평가를 별도 산출물로 보존하고, 조정 후 1쌍의 성공을 반복 안정성이나 Semantic 우위로 일반화하지 않는다. 실제 호출 경로의 동적 선택은 유지하고 특정 도구 순서를 강제하지 않는다.

정확한 패키지 버전, GPT 모델 ID, 지도 공급자·초기 지역, 상태 전이·시나리오·객체 규모, 자동 이벤트 범위, 제안된 실행 예산의 튜닝, 이력 보관과 선택 변경 정책은 아키텍처 13절에 따라 후속 Design에서 결정한다. 실제 지리 지도·적아 객체·OpenAI Provider는 미정 항목에서 제외한다.


