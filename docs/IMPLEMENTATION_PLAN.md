# IMPLEMENTATION_PLAN

## REFLECT — 세 체계 군수 시나리오·독립 객체 조회·A/B/C 별도 진입

2026-10-27 사용자 Review 대화에서 합의한 방향을 다음 구현 계획으로 반영한다. [REVIEW](REVIEW.md)의 기존 지도·채팅 요구는 유지하며, 이번 추가 의견의 출처는 해당 파일에 대신 작성하지 않고 이 대화로 명시한다. 이번 Reflect는 이 파일만 수정한다. 코드·다른 spec·REVIEW 원문·STEP/AGENTS의 Human Review 표시는 변경하지 않는다. 구현은 별도 Implement 지시 후 수행한다. 기존 결과는 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)에 보존한다.

### 1. 검토 의견과 구현 목표

| 검토 의견 | 다음 구현의 해결 지점 |
| --- | --- |
| 군수 Mock을 추가하면 온톨로지 효용이 잘 드러나는가 | 독립 군수 원천을 추가하고 ATCIS 자산·KNCCS 해상 수송·군수 정비/부품/보급을 실제 명시적 기록으로 연결. 단순 조회부터 시간·다중 관계 질의까지 비교 |
| 차량 클릭으로 기본 자산·정비·재고·각 시점·연결 규칙을 보고 싶음 | LLM 없이 동작하는 Fabric 객체 상세 조회. Semantic은 동일성/관계/근거, Fabric은 공개 API 수집·조합, 원천은 현재 사실을 소유 |
| Semantic 활용이 Agent에 집중됨 | 같은 의미 조회 서비스를 UI와 Semantic MCP가 재사용. 객체 클릭만으로 통합 조회와 연결 근거를 확인하고 Agent는 추가 분석에 사용 |
| A에서 Semantic 정보를 어떻게 제한할 것인가 | 원천은 세 조건 모두 조회. Fabric 문서는 B/C, 검증된 자동 연결·구조화 상세는 C. UI뿐 아니라 서버·도구·간접 호출에서 조건 강제 |
| 채팅의 A/B/C 선택 대신 별도 UI 페이지로 시연 | 진입 선택 화면과 A/B/C 고정 페이지, 별도 동일 기준 비교 화면. 지도·검색·채팅의 공통 레이아웃을 재사용하고 모드별 상태 격리 |

목표는 C의 승리를 연출하는 것이 아니다. A의 자체 해석 성공과 B의 문서 기반 연결도 허용하고, 지식 제공(A↔B)과 같은 지식의 구조화·평가 도구 재사용(B↔C)을 구분한다. C에 helper가 있으면 Graph 저장 형식만의 효과로 주장하지 않는다. 통합 UI의 편의성과 Agent의 답변 품질도 별개로 평가한다.

### 2. 현재 코드와 차이

- `frontend/apps/platform-web/src.tsx`는 config의 contract4에서 단일 `KnowledgeApp`을 연다. `KnowledgeApp.tsx`의 composer가 모드를 바꾸며 sessionStorage key와 화면 상태를 공유한다. 지도·대화 동시 표시와 이력·비교 확대는 유지해야 한다.
- `KnowledgeApp.tsx`의 선택 상세는 상황 projection에서 원천 ID·좌표·관측 시각·native 상태를 표시한다. 여러 체계의 상세를 합치는 조회는 없다.
- `semantic_api/fabric.py`는 원천 공개 API의 projection/context를, `semantic_core/domain.py`는 의미 조회를 담당한다. `/v1/entities/resolve`, `/v1/relations`, `/v1/evidence/{id}`는 이미 Agent 없이 호출할 수 있다. 다만 현재 resolver는 ATCIS 장비·KNCCS 접촉 관계에 특화돼 있고 API의 systemId도 두 체계로 제한된다. 군수 식별자와 연결된 sourceRefs를 실제로 반환하도록 확장해야 한다.
- v4 KnowledgeToolRunner와 runtime에는 A/B/C 도구 경계·같은 snapshot/지식 집합 비교가 있다. 세 번째 원천의 discovery·snapshot·capture·coverage·Graph provenance와 페이지별 서버 계약까지 확장해야 하며, URL만 나누는 것으로 완료하지 않는다.
- 현재 [PRD](PRD.md)·[ARCHITECTURE](ARCHITECTURE.md)·[UI_GUIDE](UI_GUIDE.md)·[ADR](ADR.md)는 두 원천·v4·composer 모드 전환이 기준이다. 해당 문서의 수정은 다음 Implement에 포함한다.

### 3. 범위·버전·보존 경계

- 신규 군수 Mock의 작업명은 `mock-logistics`, source ID는 `logistics`로 한다. 독립 Python 서버·SQLite DB·UI·시뮬레이터·공개 읽기/제어 API·원천 MCP를 제공한다. Node는 UI 빌드에만 사용한다. 단독 실행에 C4I/Fabric/Graph/OpenAI가 필요 없어야 한다.
- 신규 세 체계 데모는 `c2-logistics-demo-v5`, 계약/정책5 계열과 별도 DB·독립 fixture/gold를 사용한다. 정확한 계약 필드는 선행 테스트에서 확정하고 구현 문서에 기록한다. 기존 v4/v3/v2/v1/legacy 데이터·Graph·run·기대값을 덮어쓰거나 새 결과로 재해석하지 않는다. 기존 fixture와 production seed의 정답 로직을 공유하지 않는다.
- ATCIS/KNCCS의 새 계약 데이터는 기존 자산과 일관된 합성 자산/수송 기록을 사용한다. 대화의 A-001은 설명 예시이며 기존 L-T01 등을 무단 rename하지 않는다. UI에는 원천 ID를 그대로 표시하고 전역 동일성은 별도 canonicalId로 표현한다.
- 단일 Python Agent/native tool loop를 유지한다. 새 Orchestrator·전문 Agent·위임은 도입하지 않는다. Agent 원천 조회는 실제 MCP Client→Server→공개 API이며 직접 REST/DB 우회는 없다. UI/Fabric의 공개 API 조회와 Agent MCP 경로를 구분한다.
- 범용 군수 ERP·실제 군 교리·실전 보급 최적화·임의 문서 업로드/LLM 관계 생성·새 대형 UI 라이브러리는 제외한다. live 유료 GPT 효과 측정은 이번 구현 완료 조건에 포함하지 않고 별도 사용자 지시 범위에서만 실행한다.

### 4. 군수 원천과 세 체계 데이터

최소 자원은 군수 자산, 정비 작업/진행 기록, 부품 품목·적용 관계, 창고 재고·예약, 보급 요청·화물/수송 참조다. KNCCS에는 공개 업무 기록으로 수송편·입항/인도 상태를 제공하고 군수 화물과 연결한다. ATCIS에는 장비·소속·현재 상태를 유지한다. 새 record도 각 소유 체계가 독립 API로 제공해야 한다.

- 군수 자산 ID는 ATCIS 장비 ID와 다르게 둔다. 명시적 자산 매핑/등록 근거로만 연결하며 이름·근접 좌표·LLM 확신으로 확정하지 않는다. 원천이 실제로 보유한 명시적 매핑/상호 참조는 A/B/C 모두 읽을 수 있다. Fabric이 관리하는 설명/매핑 문서는 B/C의 같은 지식 집합에 포함한다.
- 부품은 차량의 단일 속성이 아니다. 차량→정비 작업→필요 품목/수량→적용/대체 조건→창고/예약 또는 화물→수송편의 관계로 모델링한다. 재고 총량·예약량·사용 가능량·입고 예정량을 구분하고 단위/동일 부품 중복 할당을 검증한다.
- 수송 도착·부품 인도·정비 완료·원천 운용 상태는 서로 다른 사실이다. 도착만으로 복구 완료를 단정하지 않는다. 작업 소요 시간·다른 미해결 고장·예약·컷오프 시각을 합성 문서/규칙에 명시한다.
- 같은 자산의 동시 상태를 의도적으로 모순되게 만들지 않는다. 시차·미수신·정정은 명시적 기록으로 표현한다. 미연결·복수 후보·유효 기간 만료·누락·단절 반례는 독립 negative fixture로 검증한다.
- 정지/시작/1초 진행과 수송 지연·인도/정비 진행 등 재현 가능한 업무 변경을 제공한다. 상태 소유권·이벤트 의미를 분리하고 매 tick 모델 호출/Graph 재생성을 하지 않는다.

### 5. Agent와 독립된 Fabric 객체 상세

| 구성 | 책임 |
| --- | --- |
| 원천 세 체계 | 자산·상태·정비·재고·수송의 사실, source ID/기준 시각·업무 변경 이력 |
| Semantic 서비스/Graph | canonical identity, 검증된 관계·유효 기간·적용 규칙·문서/원천 assertion·graphVersion |
| Fabric 객체 상세 서비스 | 선택 원천 키를 해소하고 허용된 관계의 sourceRefs로 공개 원천 데이터를 조회/조합. 출처별 시점·수신·coverage·부분 실패 반환 |
| UI | 기본 자산/정비/관련 부품/수송/연결 근거를 읽기 전용으로 표시. 결과·버전·오류를 숨기지 않음 |
| Agent | 동일 서비스의 공개 Semantic API를 MCP로 사용한 후속 분석. UI 실행에 필수 아님 |

새 객체 상세 API는 다음 Implement에서 계약을 정의한다. 선택 입력은 system/dataset/epoch/recordType/nativeId로 식별하고, C 조회는 고정 graphVersion과 조회 기준/source snapshot 참조를 포함한다. 응답은 canonicalId·identityStatus, 원천별 레코드/출처, sourceRefs·관계/규칙/근거, knowledge/adapter/Graph 버전, coverage와 부분 실패를 포함한다. 안정 Graph와 현재 원천의 epoch/stable 기준이 맞지 않으면 stale/mismatch로 표시하고 새 객체를 과거 관계로 잘못 연결하지 않는다.

각 기록의 **원천 기준 시각**, 제공되는 경우 **상태 변경 시각**, Fabric의 **마지막 성공 수신 시각**을 구분한다. 누락 시각을 현재 시각으로 채우지 않는다. live 통합 화면은 서로 다른 기준 시각을 그대로 표시하고, 공식 비교에서는 세 체계 고정 snapshot 집합을 사용한다. Graph가 live 위치/재고/정비 상태의 주인이 되지 않는다.

C의 차량 클릭 상세는 기본 자산→정비 작업→관련 부품/재고→관련 수송→연결 근거 순서다. 근거에는 원천 매핑/association ID, ruleId/버전(실제 의미 규칙이 적용된 경우), adapterVersion, 유효 기간·문서·Graph 버전을 제공한다. 모든 기계적 연결에 가짜 도메인 규칙을 붙이지 않는다. 미연결/모호/충돌은 확정 통합하지 않고 원천 기록과 이유를 보인다. 군수/KNCCS 단절도 기본 ATCIS 상세·채팅을 막지 않는다.

### 6. A/B/C 별도 진입과 서버 경계

진입 선택 화면에서 A 원천 데이터/B 문서 지식/C 구조화 지식과 ‘동일 기준 비교’를 선택한다. 신규 경로의 계획안은 `/demo/a`, `/demo/b`, `/demo/c`, `/demo/compare`다. 같은 지도·원천 검색·채팅 shell을 재사용하고 상단에 조건을 고정 표시한다. 각 페이지의 composer 모드 선택기는 제거하며 조건 변경은 명시적 진입 이동이다. 직접 URL·새로고침·이전/다음·잘못된 경로·정적 SPA fallback도 처리한다. 기존 v4/v3 진입 동작은 호환 경로로 보존한다.

| 기능 | A | B | C |
| --- | --- | --- | --- |
| 세 원천의 검색·기록·native ID/상태·출처/시각 | 허용 | 허용 | 허용 |
| 선택 원천 객체의 기본 상세 | 허용 | 허용 | 허용 |
| 원천에 실제 포함된 명시적 매핑·참조 | 허용 | 허용 | 허용 |
| Fabric 설명·매핑·판정 문서 | 불가 | 허용 | B와 동일 집합 |
| Semantic 동일성 해소·관계·규칙 평가 | 불가 | 불가 | 허용 |
| 검증된 연결을 이용한 자동 통합 상세·Graph 근거 | 불가 | 불가 | 허용 |
| 모델이 허용된 원천/문서에서 직접 해석 | 허용 | 허용 | 허용 |

- A/B는 다른 원천을 별도로 검색/조회할 수 있다. C만 군수 원천 자체를 볼 수 있도록 제한하지 않는다. A/B의 map projection·기본 상세·검색 응답·추천 질문에 Semantic의 canonical 연결/해석/파생 집계를 몰래 넣지 않는다. UI에서 문서를 숨기고 응답 payload에 남기는 것도 금지한다.
- 신규 서버의 page/session 실행 context가 mode·policy·dataset을 결속하고 run 생성/대화/상세/API를 검사한다. UI body/header의 임의 mode만 신뢰하지 않는다. 요청한 mode와 conversation/context 불일치는 명시적 거부이며 저장된 run의 정책을 바꾸지 않는다. URL 분리는 실제 사용자 인증/인가 경계라고 주장하지 않는다. 데모 사용자는 C 페이지에 명시적으로 진입할 수 있고 운영자 Fabric 콘솔은 별도 관리 진입점이다. 브라우저에 전체 Fabric 토큰을 내려 A/B의 우회 경로로 쓰지 않는다.
- A/B는 Semantic client/helper/Graph 접근을 하지 않는다. A는 Knowledge client도 만들지 않는다. 원천 조회 API 내부의 간접 Semantic 호출까지 negative test로 차단한다. A/B는 Neo4j/Builder/Semantic MCP 없이 동작하고, A는 문서 서비스 장애에도 동작한다.
- 페이지별 대화·선택 객체·원천 상세/구조화 상세·문서·스크롤·storage·요청 세대·캐시 key를 mode/policy/dataset과 필요한 버전에 묶는다. C→A/B 이동 시 C의 응답 payload·drawer·오래된 fetch 결과가 남지 않는다. 채팅 이력은 해당 조건만 보이고 비교 이력은 별도 화면에 둔다.
- 지도 클릭은 모델 호출을 만들지 않는다. ‘이 객체에 질문’은 사용자가 명시적으로 실행할 때만 허용된 원천 참조/질문을 전달한다. C 통합 내용을 A/B에 자동 전달하지 않는다. 원천 식별자를 받은 Agent도 실제 MCP로 근거를 조회한다.

### 7. 비교 시연과 질의·평가

세 페이지의 체험 결과는 사용자가 본 정보·질문이 달라질 수 있으므로 공식 A/B/C 측정으로 취급하지 않는다. 별도 비교 화면은 같은 질문·세 원천 snapshot 집합·기준보고/T0·모델/예산을 고정하고 B/C의 같은 지식 version/hash, C의 Graph provenance를 검증한다. 세 대화·도구 registry를 격리하며 실행 순서 회전·부분 실패 보존·준비 비용과 loop 비용 분리를 유지한다. C에서 선택한 구조화 상세나 이전 답변은 공통 질문에 자동 첨부하지 않는다.

| ID | 신규 합성 질의 | 확인 지점 |
| --- | --- | --- |
| L0 | 부품 P-08의 창고별 재고와 예약 수량은? | 단일 원천 대조군. 구조화가 없어도 충분히 답할 수 있음 |
| L1 | 이 차량의 기본 정보·정비 작업·필요 부품·수송 현황과 각각의 기준 시각/연결 근거를 보여 줘 | 객체 동일성·출처별 시점·관계 근거 |
| L2 | B11 예하 운용 제한 전차 중 재고와 해상 입고 예정 부품을 고려하면 내일18시까지 복구 조건을 충족하는 장비는? | 조직·동일성·부품 적용/예약·작업 소요 시간·컷오프. 충족/미충족/정보 부족 구분 |
| L3 | 수송편 N-21의 입항이6시간 지연되면 어느 부대의 장비 복구 일정이 영향을 받는가? | 화물→부품→정비→장비→부대의 역방향 영향. 가정 분석이며 원천 상태를 변경하지 않음 |
| L4 | 수송 중 부품과 관련된 정비 작업 중 이미 재고가 확보된 것과 해당 입고에 의존하는 것을 구분해 줘 | 재고 존재와 실제 할당 가능량 구분·중복 배정 방지 |
| L5 | 복구 전망을 확정할 수 없는 장비와 추가로 필요한 원천 기록은? | 누락·모호·단절을0/불가로 바꾸지 않는지 |

‘정비 완료인데 C4I 운용 제한’ 같은 시차 질의와 같은 화물로 복구 가능한 고유 장비 수는 보조 사례로 둔다. 업무 상태 차이를 오류나 허위 충돌로 단정하지 않는다. 금지 결론(도착=인도=정비 완료, 재고 중복 사용, ACK=완료 등)과 충분한 근거를 독립 gold에 명시한다.

B 문서에는 C가 사용하는 식별자 매핑의 의미·부품 적용 조건·예약/시간/완료 기준·예외를 같은 범위로 제공한다. 문서 밖의 C 전용 사실/기본값으로 정답을 만들지 않는다. 평가는 정답·허용 해석, 연결 누락/오연결, 근거 완결성·시점, 불확실성, 도구 수·usage·지연/실패를 분리한다. C helper의 자동 평가/계산 효과를 함께 기록한다. 합성 정답과 실제 도메인 검증, 결정론적 provider와 실제 GPT 측정을 혼동하지 않는다.

### 8. 구현 순서와 먼저 실패시킬 검증

각 단계는 새 테스트 작성→기존 코드에서 관련 실패 확인→최소 구현→관련 검사 통과 순서로 수행한다. 과거 통과 기록을 새 기능의 증거로 재사용하지 않는다.

| 단계 | 선행 테스트/반례 | 구현·완료 기준 |
| --- | --- | --- |
| P1. 계약·독립 fixture | 세 번째 원천 계약/자원 부재, fixture 수량·관계·시간/예약 정답 검증 | v5 별도 dataset/schema/policy/DB와 독립 gold. source 키·시점·권한·부분 결과 계약을 확정 |
| P2. 군수 Mock·원천 MCP | 단독 실행/API/페이지·snapshot 재현, 읽기/제어 분리·MCP→공개 API 추적 | 군수 UI/Python/DB/시뮬레이터와 실제 MCP. KNCCS 수송/인도 업무 기록·세 체계 일관성. 단독 wheel/정적 UI 포함 |
| P3. Fabric 수집·Semantic 확장 | 세 원천 capture 누락/epoch gap·부분 단절, B/C 지식 hash 불일치, 잘못된 ID/기간 연결 | 세 원천 context/coverage·이벤트, 군수 relation/adapter·검증된 Graph build. tick만으로 rebuild하지 않음 |
| P4. 독립 객체 상세 | 모델 provider가 실패해도 클릭 조회 성공, unresolved/ambiguous/conflict·부분 장애·stale Graph·시각 누락 | LLM 없는 Fabric 상세 API와 UI. 동일성/관계/근거/버전과 live 정보 분리, 원천별 독립 상태 |
| P5. 페이지/서버 접근 경계 | A/B에서 C API·직접 요청·간접 helper 접근 거부, mode/body 변조·대화 혼용·C 늦은 응답/캐시 유출 | 진입 선택·A/B/C 고정 공통 shell·별도 비교. A/B의 세 원천 접근 유지. 새 route reload/뒤로가기·기존 v4 진입 보존 |
| P6. Agent·공정 비교 | 실제 세 원천 MCP discovery·읽기, A의 문서/Graph 미접속·B의 Graph 미접속, 세 snapshot/지식 pins·C 실패 보존 | 단일 native loop의 세 체계 지원. 비교 manifest·격리된 이력·L0~L5 scenario/gold·측정 도구 |
| P7. 회귀·문서·인계 | 실제 빌드 UI·MCP·Neo4j E2E, 새 페이지/상세/모바일·키보드·v4/v3/원천/Fabric 회귀 | 관련 검사와 capture 검토. 영향받은 spec/README/실측 STATUS 정합화, 완료 PLAN 정리·STEP/AGENTS Human Review 인계 |

P4의 의미/원천 조합을 공통 서비스로 구현하고 UI와 Semantic MCP가 재사용하게 한다. 공통 서비스가 Agent를 호출하거나 UI가 Agent MCP를 우회하는 구조는 만들지 않는다. P5의 서버 context와 P6의 run policy는 같은 capability 검사로 정합화한다. 기존 DomainService에 새 체계 특수 분기를 계속 누적하기보다 sourceRef 해소/관계 조회와 도메인별 adapter·규칙 책임을 분리한다. 불필요한 전체 backend 재작성은 하지 않는다.

### 9. 검증·완료 조건

- 계약/단위: ID scope·관계·유효 기간·예약/단위/수량·시간·coverage·정책 검증. 같은 지식 집합과 source refs를 B/C에서 대조한다.
- 실제 통합: 군수 단독 실행, 세 원천 공개 API→각 MCP, Fabric capture→Builder→Neo4j→Semantic API/MCP, 페이지별 run·비교 manifest. 테스트용 DB/Neo4j prefix를 격리하고 기존 데모 volume·DB·Graph를 초기화하지 않는다.
- 접근 반례: A/B에서 Semantic/Graph 호출 횟수0, A에서 지식 호출0을 spy뿐 아니라 실제 서비스가 없는 환경으로 확인한다. 다른 모드 conversation/run/detail URL·payload·브라우저 storage·늦은 응답과 직접 상세 API 요청도 검증한다. compare/운영자 API를 A/B의 숨은 지식 공급 경로로 쓰지 않는다.
- UI:1440×900/1280×800/1024×768/640×900/390×844와 줄어든 가용 높이에서 지도·대화·객체 상세를 유지한다. 진입/모드 고정 표시·새로고침/이력·근거 이동·모바일 상세·탭/포커스·긴 ID/표·타일 장애·원천별 부분 오류를 확인한다. 정상/미연결/부분 실패·A/B/C 차이를 capture하고 직접 확인한다.
- 품질: TypeScript·Python 관련 정적 검사/production build/정적 패키징 및 영향받는 기존 테스트를 완료한다. PRD(산출물·시나리오/평가), ARCHITECTURE(세 원천·API·MCP·시점·실행), UI_GUIDE(진입·상세·비교), ADR(책임 분리·새 계약), README(실행/사용)와 STATUS(실제 결과/한계)를 기존 파일에 정합화한다. docs8개를 유지하고 REVIEW 원문은 수정하지 않는다.
- 최종 수용: 사용자가 각 조건의 별도 페이지에 들어가 같은 원천을 탐색할 수 있고 C에서는 클릭만으로 연결된 정보·시점·연결 근거를 조회한다. Agent가 없어도 그 기능이 동작한다. A/B는 구조화 정보를 우회 제공받지 않으면서 허용된 원천/문서로 올바른 해석을 할 수 있다. 별도 비교는 같은 세 체계 기준과 B/C 같은 지식을 고정한다. 구현 통과와 실제 모델 효과 측정을 구분해 Human Review에 넘긴다.
