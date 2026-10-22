# Implement 검증 보고서

## 2026-10-22 Review 중 원천 UI의 EX-01 반복 표시 수정

사용자가 관측 4건/함정 2건 목록에 EX-01 버튼이 반복해서 남는 현상을 제보했다. 실행 중 원천 API의 관측 O1~O4, 함정 N-S01/N-S02, 문서 4개는 정상이며 문서 추가 발생이 아니었다. 참조 기록 E1/E2가 동일한 documentId=EX-01을 가지는데 UI identity가 associationId보다 documentId를 먼저 선택하여 React key가 중복됐다. 이 상태에서 탭 전환 시 이전 버튼이 남는 표시 오류였다.

TDD: 실제 Chromium에서 참조 기록의 E1 버튼을 찾지 못하는 RED를 확인했다. 자체 observation/receipt/association/entry ID를 문서 참조보다 우선하고 React key에 system/tab을 포함했다. 참조→관측→함정 반복 전환 시 항목 수 2/4/2를 확인하는 테스트를 추가했다. 수정 후 원천/Fabric UI **4 passed, 1 deselected (24.56초)**, TypeScript·Ruff 통과. 두 원천 UI를 재빌드하고 Python static 경로에 반영했다. 이미 열린 브라우저는 새로고침해야 새 코드를 사용한다. DB/seed/Graph는 변경하지 않았고 Review 단계는 유지한다.

## 2026-10-22 C0~C7: Native C2 + Data Fabric v3

사용자가 승인한 현재 계획의 구현·검증을 마무리하고 Human Review로 인계한다. 사용자 REVIEW는 작성하거나 완료 처리하지 않았다. 기존 DB/Graph/대화·평가 artifact를 삭제하지 않았으며 커밋/푸시는 수행하지 않았다. 아래 이전 S8 기록과 v3 결과를 구분한다.

### 구현한 수직 경로

- **C0/C1:** 기존 회귀·환경 제약을 확인했다. 독립 `tests/fixtures/c2-domain-demo-v3`에 원천 입력과 F1~F7 기대값을 고정하고 생산 코드의 gold 참조를 금지했다. T0/T1과 source별 문서 4개씩을 고정했다.
- **C2:** 육군/해군 native 모델·자체 SQL 테이블·API/제어·UI·시뮬레이터를 분리했다. 육군 offset/items·장비 정비 코드와 해군 envelope/continuation·복합 contact/항적·함정 engineering/mission을 사용한다. 공유 ledger는 snapshot/event/auth/persistence만 담당한다. v2는 legacy 분기에 보존한다.
- **C3:** 실제 원천 MCP를 확장하고 Fabric API/콘솔을 독립 추가했다. 원천 공개 API를 통해 catalog·표시 projection·SSE·분석 context를 제공한다. OFF는 Graph 없이 동작하며 부분 원천은 coverage로 구분한다. sources/fabric/platform/off/full 프로필을 추가했다.
- **C4:** 검토된 문서 hash/version·adapter·규칙·Graph 저장/탐색을 분리했다. Ontology 3.0.0/adapter 3.0.2와 catalog hash로 build를 식별한다. 명시적 association만 동일성으로 연결하고 미연결 contact를 남긴다. 위치·실시간 상태·활동 진행·ACK는 Graph에 저장하지 않는다. Semantic MCP 7개와 bounded 관계/절차 조회를 제공한다.
- **C5:** 기존 단일 native loop에 현재-run 규칙 평가/계산을 추가했다. OFF에는 Semantic 연결/helper가 없고 native 문서·코드표는 동일하게 제공한다. ON 집계는 scope·페이지·동일성·상태 평가·정책의 근거를 요구하며 불완전 조회를 0으로 확정하지 않는다. canonical 지원 중복을 병합하고 유형·상태 교차 집계를 반환한다. claims 참조 검증, 기준보고/T0 고정, Fabric 경유 표시 수집·자동 사건 분석을 연결했다.
- **C6:** 육군/해군 업무 화면, Fabric 읽기 콘솔, 플랫폼 예시 질문·기준보고·주장 배지·교차 집계 표·비교 조건 상세를 구현했다. 제품 4개와 legacy를 포함한 5개 정적 앱을 각 Python package에 포함했다.
- **C7:** 일반/실제 MCP·Neo4j·browser·독립 wheel·실제 GPT를 나눠 검증하고 기존 spec의 첫 절에 v3 구현 기준을 반영했다. 자연어 품질을 도구 실행 성공과 분리했다.

### TDD와 수정 근거

새 source/semantic/Fabric/Agent/MCP/Graph/플랫폼/browser 계약 테스트를 먼저 추가했다. 실패를 확인한 항목에는 코드/문서 hash 불일치, 미래 knownAt, 복합 키, ACK/근거 누락, OFF helper 차단, 다른 run 근거, 만료 지원, 불완전 scope 집계가 있다. 최근 scope 일부만 조회한 빈 참조는 기존 코드에서 0으로 집계되는 RED를 확인하고 거부하도록 수정했다.

실제 GPT F7이 `groupBy=kind,status`를 두 번 요청했으나 도구가 거부한 trace를 확인했다. 교차 집계 지원 테스트의 RED 후 구현했고 별도 F7 ON/OFF를 실행했다. 원본 14회 artifact는 덮어쓰지 않았다. 장시간 테스트 서버 stderr PIPE 포화도 재현 테스트 실패 후 drain thread로 수정했다. UI record 버튼의 접근 가능한 이름도 browser 실패로 확인 후 명시했다. 최종 근거 점검에서는 SourceRecord의 기계적 참조가 무관한 REPORT-LINEAGE 규칙으로 표시되는 실패를 추가하고 adapter 3.0.2의 명시적 provenance로 분리했다. 실제 GPT artifact는 이 수정 전 adapter 3.0.1의 결과이며 동일 원천/규칙의 수량 기대값을 새 코드의 실측으로 바꿔 쓰지 않는다.

### 현재 검증 결과

검증 환경: 저장소 내부 Python 3.12.10 / `var/implementation-venv/Scripts/python.exe`. 원래 `.venv`는 존재하지 않는 Python312 경로를 가리켜 보존하고 별도 환경을 만들었다. sandbox 기본 TEMP/캐시 권한 문제는 저장소 `var/test-tmp`, `var/uv-cache`, `var/test-cache`로 우회했다. 독립 wheel의 공개 의존성을 캐시에 준비한 후 offline 설치를 검증했다.

| 명령/검증 | 결과 |
| --- | --- |
| pytest -m "not live and not performance and not neo4j and not ui" -q | **119 passed, 28 deselected (120.58초)**; 독립 wheel 2개 포함 |
| 최신 domain_agent | **5 passed**; 불완전 scope 반례 포함 |
| 최신 domain_integration + domain_graph -m neo4j | **3 passed (19.99초)**; 실제 MCP/Neo4j, P1/P2·교차 집계 |
| domain_platform -m neo4j | **1 passed (55.26초)**; 직접 원천 REST poison, Fabric 수집·비교·사건 큐 |
| Ruff check / mypy | check 통과; **63 source files** mypy 통과 |
| 계약 export / UI | export 완료; TypeScript 및 **5개 Vite build 통과**, Python 정적 경로 복사 완료 |
| 전체 Neo4j 최종 회귀 | **13 passed, 134 deselected (198.19초)**; Docker 접근 가능한 환경에서 실제 중단·복구와 비교 UI 포함 |
| 원천/Fabric UI / 기존 지도 UI | **3 passed (16.08초)** / **2 passed (39.78초)**; 지도는 네트워크 허용 환경에서 통과 |
| 최종 provenance 수정 회귀 | **8 passed (30.33초)**; ontology 5개·실제 Graph/MCP 통합 3개 |
| v3 플랫폼 비교 browser | **1 passed (58.16초)**; 기준보고/공통 조건·모바일 ON/OFF 전환; screenshot `artifacts/domain-comparison.png` |

전체 회귀 명령은 위 환경의 python으로 실행했다. 기본 pytest 설정은 neo4j/live/performance를 제외하므로 별도 `-m "neo4j and not live"`가 필요하다. 테스트 Neo4j는 17687/17474의 전용 컨테이너다. 실제 사용자 데모 Neo4j를 테스트 초기화 대상으로 사용하지 않는다. Vite의 지도 bundle 크기 경고는 남아 있으며 build 실패는 아니다. 앞선 sandbox 전체 실행은 Docker 접근 1개·비교 대기 시간 2개가 실패했고, UI 실행은 외부 지도 2개·비교 1개가 실패했다. Docker/네트워크 허용 및 실제 두 run 예산에 맞춘 비교 대기 시간으로 재검증해 위 결과를 얻었다. 앱 실행 예산 자체는 늘리지 않았다.

새 v3 browser 검증에서는 공통 조건을 펼쳤을 때 모바일 전환 버튼이 화면 밖으로 밀리는 실제 RED를 확인했다. metadata 높이/스크롤을 제한해 수정하고 같은 테스트를 통과했다. 플랫폼 UI를 재빌드·복사하고 TypeScript, Ruff check/format, mypy를 재확인했다. 최종 screenshot을 열어 두 비교 열과 접힌 영역의 배치를 확인했다. `git diff --check`는 저장소의 CRLF 정책 기준으로 확인한다. 별도 `core.autocrlf=false` 일회성 검사에서 CR 문자 전체를 공백으로 오인한 출력은 실제 코드 공백 오류와 구분한다.

### 실제 GPT 실행과 평가

모델: 로컬 설정 `gpt-6-luna`, 동일 질문·sourceSnapshotSet·T0·문서·model/tool/time 예산(24/20/120초), 모드별 독립 컨텍스트. 키는 출력하지 않았다.

| artifact | 결과와 보존 이유 |
| --- | --- |
| `artifacts/domain-live-20261021T091030Z.json` | 초기 7개 저장 run 중 F1 ON 시간/도구 문제, 이후 F4 ON MCP ReadTimeout으로 중단. 저장되지 않은 중단 호출도 있었으므로 완전한 비용 집계로 취급하지 않는다. 앞선 fixture 단계 실패는 모델 호출 전이었다. |
| `artifacts/domain-live-20261021T091825Z.json` | F1~F7 OFF/ON **14회 completed**, 테스트 574.83초. 기록된 run 시간 합 561.20초, input 662,627/output 35,686 tokens. 실행 완료를 정답 14개로 표기하지 않는다. |
| `artifacts/domain-evaluation-20261022.json` | 위 14개 offline 근거 평가. F3 절차와 F6 계산 일치. F2/F4/F5 ON 필수 규칙 조회 coverage 누락. F7 ON 집계 호출 2개 실패 뒤 모델이 수동으로 수량을 작성해 계산 검증 불가(null). |
| `artifacts/domain-live-20261022T005227Z.json` | 교차 집계 수정 후 **F7 추가 2회 completed**, 테스트 145.96초. OFF 6 tool/37.73초, ON 10 tool/88.27초. 원본과 별도 실험. |
| `artifacts/domain-evaluation-f7-20261022.json` | F7 ON 계산이 고유 7개·상태 4/1/1/1 gold와 일치. OFF boundary 유효. input/output OFF 35,014/2,297, ON 131,535/3,684 tokens. |

저장된 run은 초기 7 + 완결 14 + 재검증 2 = **23개**이며 중단된 추가 F4 ON은 저장된 완결 run으로 세지 않는다. 실제 API 비용은 token 사용량만 기록하며 검증하지 않은 달러 가격을 적용하지 않았다. 중단된 실험의 누락 usage를 0으로 간주하지 않는다.

L1 형식/페이지·L2 객체/동일성·L3 scope·L4 상태/정책 계산은 deterministic 계약/통합 테스트로 확인했다. L5 lineage/정정·L6 절차는 Graph/규칙 테스트로 확인했지만 실제 F2/F4/F5 답변의 규칙 근거 연결은 불충분했다. L7 복합 질의는 실행 가능하며 F7 계산을 재검증했다. 자연어 핵심 사실·금지 결론·주장 충분성은 자동 채점하지 않았고 **Human Review 필요**로 남긴다. OFF도 코드표를 읽어 올바르게 추론할 수 있다. 소표본 결과로 ON 우위나 군 도메인 정답률을 일반화하지 않는다.

### 실제 범위와 한계

합성 사건 INC-1, 등록 자산 7개·부대 5개·contact 3개, 고정 T0/T1의 최소 데모다. 명칭 이력은 단일 previousName이며 완전한 기간별 조직 변천 모델이 아니다. 관계 유효기간 조회는 build 입력 시점 기준이며, stable 자료 변경 없이 시계만 기간 경계를 넘는 장시간 운용의 시점별 재해석은 이번 실측 범위가 아니다. 일부 공통 정의/절차 노드는 payload로 연결 정보를 보유한다. 임의 SOP/문서 자동 추출·Graph 편집·RDF/OWL/범용 CDC는 구현하지 않았다. 공개 개념 참고와 합성 SOP를 구분하며 실제 군 내부 구조/권한을 주장하지 않는다.

재현은 README의 v3 절을 따른다. REVIEW는 사용자 소유이며 모델 답변 자연어 검토를 AI가 대신 완료하지 않는다.

## 2026-10-16 Review 중 질의 404 수정

질의 시 `404: {"error":"not_found"}`가 발생한다는 사용자 제보를 확인했다. 브라우저 sessionStorage의 이전 conversationId가 현재 플랫폼 DB에 없으면 enqueue의 KeyError가 일반 not_found로 반환됐다. v2 DB 전환 후에도 브라우저 대화 ID는 유지되어 같은 오류가 재현된다. 실행 중 서버는 분석 이력이 비어 있었으며 사용자 브라우저 저장소는 직접 조사하지 않았다.

- 누락 대화를 전용 ConversationNotFound 예외와 `404 conversation_not_found` 응답으로 구분했다. 서버에서 임의로 기존 대화를 재생성하지 않는다.
- UI는 해당 응답에 한해서 이전 ID를 해제하고 질문·Semantic 모드를 유지한 새 대화로 한 번만 요청한다. 새 대화 시작 안내를 표시한다. 일반 404·500은 자동 재요청하지 않는다.
- TDD: 기존 API의 일반 not_found 응답과 기존 배포 UI의 복구 실패를 먼저 확인했다. 수정 후 `tests/test_conversation_recovery.py`의 API 1개·실제 Chromium 3개 및 multi_source/semantic_boundary 회귀를 합쳐 **21 passed (24.75초)**. API 테스트는 거절된 요청이 run을 생성하지 않는 것도 검사한다. 브라우저 API 응답은 제어하며 실제 GPT를 호출하지 않는다.
- TypeScript/4개 Vite 앱 빌드·Python 정적 자산 반영, 수정 Python 파일 Ruff 및 mypy 2개 소스 검사 통과. 기존 MapLibre bundle 크기 경고는 유지된다. 현재 STEP은 Review로 유지하며 사용자 서버·DB는 종료하거나 초기화하지 않았다. 적용에는 실행 중 Python 서버 재시작과 브라우저 새로고침이 필요하다.

## 2026-10-16 S8 — Semantic 실행 경계와 무충돌 v2

사용자의 REVIEW와 채팅 설명에 따라 구현했다. 이전 P0~P7의 “OFF 차단”은 MCP 연결만 검사한 결론이었다. 공통 집계에서 상태 정규화/ER를 실행한 누락을 이번 S8에서 수정했으며 이전 15쌍의 효용 평가는 새 격리 정책의 증거로 재사용하지 않는다.

### 변경 내용

- 원천 API/MCP 목록·집계는 native typeCode/statusCode만 비교한다. 도구 설명에서 체계 간 동일성 판정 규칙을 제거했다. OFF Agent 조회 경로는 공통 의미 정규화를 호출하지 않는다.
- `agent/calculation.py`의 일반 계산은 native 필드 빈도·동등 필터·raw 수량만 제공한다. OFF는 Semantic 집계 인자를 거부하며 canonical ID/공통 가용 상태를 생성하지 않는다. 좌표 계산도 native 좌표를 직접 읽는다.
- ON은 Semantic MCP의 scope/identity/reference 및 interpret_concept의 sourceMappings·mappingRule 근거를 계산에 적용한다. 로컬 계산에 원천 매핑표·ER 규칙·직접 Graph 접근을 두지 않았다. 모든 sourceRef의 관측과 전체 페이지가 필요하며 빈 결과와 누락/미해결을 구분한다.
- Semantic 해석의 Ontology/매핑 버전은 2.0.0이다. 이전 Graph 근거는 읽을 수 있지만 새 코드 해석을 과거 규칙 버전으로 표시하지 않는다. 다른 정책 대화·대기 run·준비된 비교는 새 정책으로 자동 전환하지 않는다.
- 새 기본 semantic-demo-v2의 UAV는 양쪽 가용·아군·동일 초기 위치/벡터이며 B11/S11에 명시적인 비전속 공동지원 관계다. 기본 통합값은 raw 8/unique 7/가용 4/불가 2/미확인 1/충돌 0. production seed와 독립 gold를 분리했다. 충돌 방어는 negative fixture에 남겼다.
- 기본 DB 경로는 atcis-v2.db·knccs-v2.db·platform-vnext-v2.db로 분리했다. 기존 .env 경로가 있으면 유지하므로 README의 명시적 v2 실행 명령을 사용한다. 과거 v1 stable hash에 새 기본 역할 필드를 끼워 넣지 않는 호환성을 검사했다. 기존 DB·Graph·실행 중인 사용자 서버는 reset/종료하지 않았다.
- UI는 native 계산을 “의미 해석 없음”으로 표시하고 공통 수량을 채워 넣지 않는다. 정책/데이터셋 버전·이전 정책을 표시한다. PRD/아키텍처/Ontology/Agent/시연/UI/README/ADR-023을 같은 경계로 정렬했다.

### TDD와 검증

`tests/test_semantic_boundary.py`에서 OFF helper 호출·원천 조회 정규화·v1 seed·과거 대화 재사용·구버전 혼용 등의 실제 실패를 확인한 뒤 구현했다. 실제 source MCP 테스트는 startup 이후 원천 normalize_equipment를 예외로 차단한 서버에 11개 도구를 호출하며 양 원천에서 통과했다. ON은 Semantic 근거·모든 관측·완결 페이지·미해결/유형 근거 누락·빈 결과를 검증한다.

최종 현재 STEP은 **Review (Human)**이다. 커밋/푸시와 사용자 REVIEW 작성은 수행하지 않았다.

| 최종 검증 | 결과 |
| --- | --- |
| `uv run pytest -q` | **97 passed, 13 deselected, 149.79초**. 일반 회귀·source wheel/실제 MCP·기존 UI 포함 |
| `uv run pytest -m "neo4j and not live" -q` | **9 passed, 101 deselected, 142.76초**. 실제 Neo4j/API/MCP·Builder scope/동기화·비교 UI·물리 장애 복구 |
| Ruff check / format check / mypy | 모두 통과. 91개 파일 형식, 49개 Python 소스 타입 검사 |
| 계약 export / TypeScript / 4개 앱 Vite 빌드 / build_ui.py | 통과, 각 Python 패키지에 배포 자산 반영. MapLibre 포함 큰 bundle 경고 유지 |
| UI 시각·동작 | OFF native 집계 안내·v2/정책·ON 관계/근거·모바일 탭/키보드/이력 복원 통과. screenshot을 직접 확인 |
| 문서 상대 링크 / diff 공백 | 깨진 링크 및 이번 변경의 공백 오류 없음. 사용자 REVIEW 원문은 수정하지 않음 |

이전 전체 94개 통과 후 과거 정책 대기 run/Graph 혼합 및 v1 hash 호환성을 더 검증해 최종 97개가 통과했다. Live/performance는 일반 성공 수에 합산하지 않았으며 실제 GPT 실행은 아래 별도 기록한다. 검증 중 자동 승인 검토의 사용량 한도로 실행되지 못한 호출은 사용자의 재개 지시 후 정상 실행했다. 현재 남은 검증 차단은 없다.

### 실제 GPT 검증 및 한계

설정 모델은 기존 `gpt-6-luna`를 유지했다. 사용자 서비스와 다른 포트(:6300 등), 별도 var/s8-*-v2.db 및 **테스트 Neo4j :17687**로 실행했다. 검증 프로필은 종료했으며 데모 Neo4j :7687과 사용자 :4100/:4300 프로세스는 조작하지 않았다.

| 최초 v2 1쌍씩 | OFF | ON |
| --- | --- | --- |
| S1 | completed, native 근거 검사 통과. 7 tools/8 turns/51,578 tokens/63.50초 | completed, 가용 ID 2개·집계 정답. 6/7/52,715/42.48초 |
| S2 | budget_exceeded. 존재하지 않는 evidenceId를 반복 조회, 6/6/29,916/16.33초 | completed, raw 8/unique 7/available 4·정답 집계. 13/14/141,318/81.39초 |
| S3 | partial, 원천 관측은 조회하되 검증된 동일성을 확정하지 않음. 4/6/40,501/43.89초 | completed, 명시적 연결/공동지원·일치 상태 확인. 6/7/51,628/44.10초 |

S2 OFF의 도구 오용을 해결하기 위해 read_evidence에 사전 근거 조건과 snapshotId/evidenceId 차이를 명시하고, 없는 ID 오류에 현재 run의 사용 가능한 ID를 반환했다. 추가 1쌍에서 OFF는 원천 8건과 원천 코드 수량을 제공하며 고유 객체 확정을 보류하는 partial로 끝났다(6/7/44,512/59.75초). 이는 Semantic helper를 사용한 확정 결과로 올리지 않았다.

같은 추가 쌍의 ON도 partial이었다(19/20/229,261/116.83초). Semantic 서비스가 availability 등의 질의에 지원 용어를 안내하지 않아 모델이 여러 별칭을 반복 시도했다. 실패 테스트 후 명시적 availability/가용성 별칭과 supportedTerms 응답·도구 계약을 보완했다. 이후 **ON S2 단일 재검증**은 8 tools/9 turns/78,701 tokens/46.26초로 completed 및 모든 자동 집계/ID 검사를 통과했다.

총 실제 검증은 최초 3쌍 6 run + 추가 S2 1쌍 2 run + 최종 ON 1 run이다. 자동 점수는 도구 근거·수량 기준이며 자유 텍스트의 정확성/추론 표시는 Human Review 대상이다. OFF의 partial/모델 추론은 실패한 서버 격리와 구분한다. 유효한 근거 없이 확정 집계를 제공하도록 프롬프트를 강제하지 않았다. 소수 시연의 성공/비용 차이를 성능 우위로 일반화하지 않는다.

원본은 Git 제외 artifacts/semantic-evaluation-s8-v2.json, 추가 semantic-evaluation-s8-v2-retry.json, 최종 semantic-s8-v2-on-concept-recheck.json에 각각 보존했다. run별 시작/종료/usage/registry/정책·source refs를 남겼다. 최종 비교 경로는 preparationStartedAt/preparedAt/preparationSeconds를 추가해 Graph/snapshot 준비 시간과 실행 시간을 분리한다. 초기 S8 두 평가 파일은 이 계측 추가 전이므로 준비 시간은 개별 실측되지 않았고 쌍 전체 경과 시간만 기록돼 있다. 비용 단가는 추정하지 않았다.

### Review 실행 안내

현재 켜져 있는 사용자 프로세스는 자동 reload되지 않는다. 기존 터미널에서 Ctrl+C로 종료하고 README의 ATCIS_DB/KNCCS_DB/PLATFORM_VNEXT_DB v2 경로를 지정한 뒤 `uv run python scripts/dev.py --profile full`로 재시작한다. 각 원천과 비교 manifest의 dataset이 v2인지 확인하고 새 대화로 시연한다. 과거 DB는 삭제하지 않는다. REVIEW.md 작성과 다음 Reflect는 사용자의 검토 후 수행한다.

---

아래는 S8 이전 구현·검증의 역사적 기록이다. 당시 “현재 STEP”이나 효용 결론은 해당 시점의 상태이며 S8 상태를 뜻하지 않는다.

## 2026-10-16 이종 C4I·Semantic 고도화

독립 Mock ATCIS/KNCCS, 실제 Neo4j Graph Builder, 재사용 Semantic API/MCP, native 단일 Agent의 ON/OFF 비교를 구현했다. 사용자 Review는 아직 수행하지 않았다. 이전 R6–R7 결과는 아래에 별도로 보존한다.

현재 STEP은 **Review (Human)**다. 커밋/푸시는 수행하지 않았으며 REVIEW.md를 AI가 작성하지 않았다.

### 사용자 Review 중 발견한 Semantic ON 404 수정

사용자 플랫폼 :4300은 원천 :4100/:4110을 사용했다. AI가 띄워 둔 검증용 :5420 Builder와 사용자 :4420 Builder가 같은 Neo4j의 전역 BuildRequest 큐를 읽어, 검증 Builder가 사용자 snapshot을 자기 원천 :5100에 요청했다. 따라서 실제로 존재하는 원천 snapshot도 잘못된 서버에서 404가 났다. snapshot 삭제나 LLM/프롬프트 문제는 아니었다.

검증용 Python 프로필을 중지했다. 확인된 실패 요청 `build-request-aaefb071c0e9047567a7d78a89360a91` 1건에 이전 오류/복구 이유를 보존하고 QUEUED로 재대기시켰으며, 사용자 Builder가 `graph-74ed47f377c5e062894ff75d` READY로 처리했다. 원래 :4100 stable-export와 :4400 해당 Graph 조회가 각각 HTTP 200임을 확인했다. 과거 실패 run을 성공으로 고치거나 LLM을 재호출하지 않았다.

재발 방지: Builder의 source URL 집합을 정규화한 hash를 요청 ID와 sourceScope에 포함한다. 요청 조회·QUEUED 선택·RUNNING 복구·checkpoint를 이 scope로 제한한다. 서로 다른 source endpoint의 두 worker를 같은 테스트 Neo4j에서 실행해 요청 충돌·외부 작업 인수/재대기화가 없음을 검증한다. 기존 unscoped 요청은 자동 이관/삭제하지 않으며 새 실행은 새 scoped 요청을 만든다. 실행 중 사용자 프로세스에 코드를 적용하려면 `scripts/dev.py --profile full`을 재시작해야 한다. 검증 :5300 프로필은 다시 띄우지 않는다.

검증: 신규 scope 테스트의 요청 ID 충돌 실패를 먼저 확인했다. 수정 후 `uv run pytest tests/test_graph_sync.py tests/test_graph_builder.py tests/test_comparisons.py -m "neo4j or not neo4j" -q` **6 passed, 34.55초**. 다른 Builder의 QUEUED/RUNNING 요청 보존·자기 RUNNING 복구·자기 요청 READY와 기존 원천 동기화·실제 MCP 비교가 통과했다. Ruff check·mypy도 통과했다.

### 최종 검증 명령과 결과

| 명령/검증 | 실제 결과 |
| --- | --- |
| `uv run pytest -q` | **85 passed, 12 deselected**, 167.84초. 제외된 live/Neo4j/performance는 성공 수에 합산하지 않음 |
| `uv run pytest -m "neo4j and not live" -q` | **8 passed, 89 deselected**, 121.92초. 전용 test DB에서 실제 Graph/API/MCP/비교/UI/물리 장애 복구 |
| 최종 변경 후 `tests/test_comparisons.py` Neo4j 대상 | 1개 통과. 이어 실행한 UI는 병렬 부하로 strict capture 2초를 초과해 준비 실패 |
| 최종 `uv run pytest tests/test_semantic_ui.py -m neo4j -q` | **1 passed**, 36.70초. 단독 재실행으로 두 열·Graph 원문·모바일·키보드·새로고침 이력 검증. capture 기준을 완화하지 않음 |
| `uv run pytest -m "live and neo4j" tests/test_semantic_live.py -q` | **1 passed**, 125.42초. 실제 GPT + 원천 MCP + Neo4j/Semantic MCP |
| `npm.cmd --prefix frontend run build` | TypeScript 검사 및 4개 앱 Vite 빌드 통과. MapLibre 포함 약 1.3MB bundle 경고는 유지 |
| `uv run python scripts/build_ui.py` | 각 Python 서비스에 소유 UI 배포 자산 복사 완료 |
| Ruff check / format check / mypy | 모두 통과, 89개 Python 파일 형식·48개 소스 타입 검사 |
| 계약 export / Markdown 상대 링크 / `git diff --check` | 일치·깨진 링크 없음·공백 오류 없음. Git CRLF 안내만 있음 |

마지막 일반 회귀의 최초 실행은 종료 메타데이터 race 1건이 실패했다. 실패 테스트를 강화하고 최종 progress/종료 저장을 수정한 뒤 전체 85개가 통과했다. 독립 wheel 검증은 일반 회귀에 포함되며 깨끗한 venv에서 상대 체계/LLM/Neo4j/Node 없는 실행을 확인한다. 60초 performance 측정은 기존 baseline 기록을 유지하고 이번에는 재실행하지 않았다.

| 구간 | 실제 검증 결과 |
| --- | --- |
| P0 baseline | 기존 `uv run pytest -q`: 39 passed / 3 deselected. 기존 UI 빌드·Ruff·format·mypy 통과. Python 3.12.10, uv 0.12.10 |
| P1 계약/Ontology | 미구현 import 실패 확인 후 구현. 원천 복합 ID·가상 코드/단위·안정 hash·조직 범위·명시적 ER·독립 gold·잘못된 geometry·중복 ID·타입 계약 검증 |
| P2 원천 | API 3개, 실제 MCP 2개, 독립 브라우저 UI 2개, 격리 wheel 2개 테스트 통과. 각 원천 MCP의 11개 도구 실제 호출 확인 |
| P3 Graph/Builder | 실제 Neo4j 저장/불변·실패 build 격리 2개, 공개 HTTP 동기화/reset·관리 요청 인증/중복 2개, 일시 DB 장애 재연결 1개 통과 |
| P4 Semantic | 실제 Neo4j→Semantic API→Semantic MCP 조직/장비/동일성/근거 통합 통과. 버전·깊이·페이지·모호성·누락·인증·장애 검사 |
| P5 Agent/수집 | 실제 두 원천 MCP 발견·native 호출, 원천별 고정 snapshot, OFF Semantic 미접속, 모드/대화/근거 격리, 이벤트 자동 실행, 페이지·충돌 집계 검증 |
| P6 비교/UI | 동일 manifest/격리된 두 run, 한쪽 실패·재시작 정리, 지도·원천 필터·비교 이력·두 열 trace/근거·Graph 원문·모바일 탭·Escape/focus·기존 세 방책 기능 검증 |
| P7 실제 연동 | 일반 회귀, 전용 Neo4j 통합 8개, 실제 GPT smoke 1개, S1~S3 각 5쌍/30 run 반복 측정. 실패와 예산 조정 후 추가 측정을 아래에 구분 |

TDD: 각 신규 계약/원천/Graph/Agent/비교 테스트의 import·행동 실패를 확인한 후 구현했다. 실제 Neo4j 검증은 `-m "neo4j and not live"`로 별도 실행했다. P2 UI에서 지도 절대 위치가 목록을 덮는 오류, 실제 ON 실행에서 빈 Bearer 헤더의 HTTP 오류, SSE reset 후 epoch 재연결, 비교 재시작 정리, 평가기의 식별 레코드 상태 덮어쓰기 오류를 발견·수정했다. 채점 수정은 실패하는 회귀 테스트를 먼저 확인했다.

원천: 별도 var/atcis.db·var/knccs.db, 독립 wheel/정적 UI. 기존 var/c4i.db·platform.db는 자동 수정/초기화하지 않았다. clean venv wheel 검증은 상대 Mock·platform_api·openai·neo4j·mcp 미설치 및 PATH 비우기로 확인했다.

Neo4j: 공식 Community 2026.09.0, image digest `sha256:6f3f17e72d69bb6f26b03f6186f5afb15a201f8b460bb69b0cd8030717f9f01a`, official driver 6.4.0을 고정했다. 실제 테스트는 localhost 17687/17474 및 전용 named volume에서 수행했다. 로컬 .env에 Neo4j 전용 임의 비밀번호를 추가했고 출력/Git 포함 없이 사용했다. Docker Desktop이 처음에는 중지돼 있었으나 사용자가 실행한 뒤 실제 통합 검증을 진행했다. 공식 근거: [Docker image](https://neo4j.com/docs/operations-manual/current/docker/introduction/), [driver 호환성](https://neo4j.com/docs/python-manual/current/install/).

초기 lock SHA256: uv.lock `C22F935EF7DF55BBCC735776798D6F2D44B206B0E086FF12978C11623AE80CC2`, frontend/package-lock.json `613E1DA323ABC3A7B4666A828225D75BE16A38DAF8A2E66361F1982EA2478DC4`. 새 workspace/의존성 추가로 lock은 변경됐다. Windows에서 npm.ps1 실행 정책은 변경하지 않고 npm.cmd를 사용했다. uv/Python 및 Docker 자격 증명 접근은 승인된 실행 권한으로 처리했다.

### 구현 구조와 설계 구체화

- `packages/ontology`: Python/Pydantic 타입·명시적 코드/단위 매핑·ER. `packages/semantic-core`: 버전별 Neo4j 저장/관계 조회와 재사용 SemanticService. Builder만 Graph를 쓴다.
- 두 Mock은 별도 seed/SQLite/UI/시뮬레이터를 소유한다. 공통 `source-runtime`은 상태 없는 코드 재사용이며 DB나 원천 정보를 공유하지 않는다. MCP 의존성은 별도 adapter 패키지에만 있다.
- Graph는 위치/가용 상태를 보관하지 않는다. 원천 공개 export의 안정 정보로 검증된 관계와 Observation 근거를 생성한다. ON은 관계 참조를 얻고 실제 상태는 원천 MCP로 다시 조회한다.
- Builder 관리 요청은 인증된 :4420 API와 단일 worker를 사용한다. Semantic MCP에는 쓰기·임의 Cypher·build 도구가 없다. OFF는 Semantic 서버에 연결하지 않는다.
- 기존 단일 C4I 프로필과 loop/provider/schema 변환을 유지했다. 새 플랫폼 런타임은 다중 원천/고정 시점/비교를 담당한다. Multi-Agent·별도 Agent 프레임워크는 없다.
- Ontology는 별도 YAML DSL 대신 Python 타입/함수와 검토된 개념 사전으로 구현했다. 일반 crosswalk 편집·기간 추론·범용 별칭 관리·fuzzy 병합은 미구현이며 이번 세 시나리오는 공개 연습 ID와 원천 조직 관계만 사용한다.

### 실제 GPT 반복 측정

모델은 로컬 `OPENAI_MODEL=gpt-6-luna`를 그대로 사용했다. [OpenAI 공식 function calling 문서](https://developers.openai.com/api/docs/guides/function-calling)를 확인했고 native 호출·실제 MCP를 사용했다. 자동 평가는 자연어 설명의 완전한 품질 평가가 아니라 **완료 상태·도구 근거·정답 수량/ID** 검사다. 답변 설명과 한계의 타당성은 Human Review 대상이다.

초기 예산은 양 모드 동일 model 12회/tool 20회/120초. S1~S3 각 5쌍을 실행하고 OFF 우선/ON 우선 순서를 교대했다. 각 쌍은 질문·원천 snapshot·Graph 버전·프롬프트/registry hash·모델 설정을 보존한다.

| 시나리오 | OFF 완료·정답 | ON 완료·정답 | 평균 도구 OFF / ON | 평균 토큰 OFF / ON |
| --- | --- | --- | --- | --- |
| S1 조직 범위 탱크 | 5/5 | 5/5 | 6.4 / 5.4 | 44,000 / 46,018 |
| S2 이종 통합 집계 | 1/5, 4회 budget_exceeded | 5/5 | 11.8 / 8.8 | 81,804 / 86,374 |
| S3 동일 객체·불일치 | 2/5, 3회 partial | 5/5 | 8.8 / 8.0 | 65,377 / 68,781 |

S3의 partial은 도구 실패가 아니라 모델이 원천 간 관측 시각·조직 코드·원인 확인의 한계를 표시한 결과다. OFF의 처음 두 completed 결과도 실제 상태 근거를 확보했다. 초기에 평가기가 뒤이어 조회한 상태 없는 identity 레코드로 상태 레코드를 덮어써 오채점했으므로, 원본을 보존하고 별도 파일에 재채점했다. partial 상태는 정답 성공으로 올리지 않았다.

ON은 조직·동일성을 명시적 근거로 처리하면서 평균 호출을 줄였지만 이 측정에서 평균 토큰은 더 많았다. OFF도 같은 원시 관계로 정답을 낼 수 있다. 적은 합성 fixture/동일 모델의 결과이며 비용·속도·실사용 정확성의 일반적 우위를 주장하지 않는다. 실패한 OFF는 일찍 종료돼 호출/토큰 비교에 편향이 있다.

S2 OFF는 정상적으로 두 체계의 snapshot/조직/상하위/배속/장비/식별 정보를 조회하는 동안 12회 한도에 걸렸다. 고도화 기본값을 **양 모드 동일 model 24회/tool 20회/120초**로 조정하고 run/manifest의 `agentBudget`에 기록했다. 기존 12회 측정을 교체하지 않고 추가 결과를 별도 보존한다.

24회 예산의 추가 S2 **1쌍**은 양쪽 모두 정답 집계로 완료했다. OFF는 10 tools/11 model turns/78,827 tokens/63.46초, ON은 12 tools/13 model turns/129,681 tokens/77.72초였다. 쌍 전체 시간은 준비·두 실행을 포함한 142.60초다. 이 표본에서 ON의 호출·시간·토큰은 더 많았다. 1회 추가 검증으로 안정성 개선이나 평균 성능 우위를 단정하지 않는다. 마지막 종료 메타데이터 검증에서 terminal 상태가 finishedAt보다 먼저 보이는 race를 재현하여, progress는 running으로 유지하고 최종 상태/registry/시각을 함께 저장하도록 수정했다.

검증 산출물은 Git 제외 `artifacts/`에 있다: `semantic-live-smoke.json`, 원본 `semantic-evaluation.json`, 수정 평가기 `semantic-evaluation-regraded.json`, 추가 `semantic-evaluation-budget24.json`, UI `semantic-comparison.png`. 원본 15쌍은 run별 시작/종료 계측 추가 전이므로 정확한 개별 실행 시간은 미기록이다. 쌍 전체 createdAt/finishedAt은 보존했고, 이후 run은 startedAt/finishedAt 및 executionSeconds를 기록한다. 비용은 단가 추정으로 계산하지 않았다.

### 사용자 검토 방법

README의 설치/빌드 후 `docker compose up -d neo4j`, `uv run python scripts/dev.py --profile full`을 실행한다. ATCIS :4100, KNCCS :4110, 플랫폼 :4300이다. 기존 프로세스가 포트를 쓰면 `--port-offset 1000`을 사용한다. 검증 서버는 별도 var/validation-* DB와 플랫폼 :5300을 사용했으며 기존 :4100 서비스/DB를 변경하지 않았다.

두 원천을 정지 상태로 두고 S1~S3 질문을 각각 `동일 기준으로 비교`한다. 두 열에서 답변·호출 인수·근거·조직 경로·Graph 원문과 버전을 확인한다. 이후 원천에서 이동/상태를 변경하여 지도 반영과 자동 분석 이력을 확인한다. 비교를 열었던 과거 run은 고정 snapshot/Graph를 유지한다. 사용자 Review는 docs/REVIEW.md에 사용자가 작성한다.

> 아래는 기존 단일 C4I baseline의 역사적 검증 기록이다. 최신 고도화 결과와 구분한다.

## 2026-10-16 R6–R7 구현

기존 baseline 기록이다. 2026-10-16 10:03 Review의 두 항목을 구현했으며 다음 사용자 Review는 아직 수행하지 않았다.

### R6: MCP 서버가 도구 정의 소유

- C4I 설명은 c4i_mcp/tool_instructions.py로 이동했고 인수 schema는 MCP 서버의 typed 함수에서 생성한다. 공통 계약 패키지의 도구 설명과 플랫폼의 중복 C4I 호출 모델을 제거했다. EntityFilter 같은 원천 도메인 계약은 C4I·MCP가 공유한다.
- MCPClient가 tools/list의 전체 페이지를 읽어 이름·설명·inputSchema를 반환한다. ToolRunner는 허용된 7개 C4I 정의만 받아 native 함수로 변환하고 현재 run에서 고정한다. read_evidence·geo_measure는 플랫폼의 내부 정의다.
- 다음 run은 새 MCP 세션에서 다시 발견한다. 정의가 실행 도중 바뀌지 않으며, 서버 설명 변경이 플랫폼의 별도 문자열 수정 없이 반영되는 테스트와 실제 HTTP 발견→모델 전달→호출을 확인했다.
- optional 필드는 native strict 형식의 required+nullable로 변환하고 호출 시 원천 기본값/생략으로 정규화한다. 원래 schema로 인수를 검증하고, 지원하지 않는 키워드·open object·외부 참조·이름 충돌은 거부한다. 범용 JSON Schema 전체 변환기는 아니다.
- 발견은 run 시작 시 최대 5초다. 실패하면 로컬 C4I 정의로 대체하지 않고 조회 불가를 기록해 내부 도구만 노출한다. 일반 설명은 계속 가능하며 schema 변환 실패는 run 실패다. snapshot·epoch·sequence 검증과 실행 한도는 계속 플랫폼이 담당한다.
- strict 규칙은 [OpenAI 공식 Function calling 문서](https://developers.openai.com/api/docs/guides/function-calling)를 확인했다. 모델 ID와 API 키는 기존 로컬 설정을 유지했다.

### R7: 접경 전역 시나리오와 120개 모의 객체

- 기본 border-demo v1: 탱크 40·장갑차 24·지원 차량 20·무인기 12·함정 24, 총 120개. 고정 seed로 재현하며 객체 ID·부대·상태·위치·속도는 합성 데이터다.
- 서부·중부·동부의 남/북측 육상 시연 구역 6개와 양쪽 해역 2개를 둔다. 실제 지도 배경 위의 시연용 사각 구역이며 실제 접경선·실전 배치·작전 구역 자료는 포함하지 않는다. 차량과 함정의 seed·이동 경계를 구분한다. 도로·지형·항로 추종은 포함하지 않는다.
- snapshot의 scenario metadata가 표시명·버전·bounds·initialBounds·zones를 제공한다. 양쪽 UI가 이 데이터로 지도를 열며 전체 보기·구역 이동·기존 객체 탐색을 지원한다. tick이 줌/팬을 되돌리지 않는다.
- zoneId를 원천 객체·필터·집계에 추가했다. 목록 100+20개 페이지와 전체 집계, 구역별 8개 그룹을 검증했다. 플랫폼에 zoneId 도구 schema를 추가하지 않고 MCP 서버의 새 schema를 발견해 사용한다.
- 기존 DB의 현재 시나리오와 이동 경계는 보존한다. 초기화 시 설정된 새 시나리오·epoch로 전환하고 과거 snapshot은 원래 scenarioId로 재조회한다. metadata가 없는 이전 플랫폼 cursor는 그 시점에서 보완하여 뒤의 상태 이벤트를 건너뛰지 않는다.

### 검증 결과

| 검증 | 결과 |
| --- | --- |
| 일반 회귀 테스트 | 39개 통과, live 2개·performance 1개는 기본 제외 |
| 마지막 구역 집계 확장 후 | 시나리오·발견 관련 8개 테스트 재통과 |
| 실제 GPT | 2개 통과, 53.97초. 발견한 도구 schema로 적 탱크 집계·세 방책·선택 방책 후속 응답·거리/방위 계산 |
| 브라우저 | 기존 대화·선택 회귀, 접경 실제 배경·120개 객체·구역 이동·tick 후 지도 유지·배경 실패 시 객체 유지 통과 |
| 60초 규모 검증 | 120개, 60개 관측 표본, p95 0.2768초·최대 0.3072초, LLM 호출 0회 |
| 환경 | Windows 11 10.0.26200, Python 3.12.10, localhost 서비스. 0.1초 polling의 첫 플랫폼 관측 시각과 원천 sourceTime 차이로 지연 측정 |
| Python 검사 | Ruff·포맷 및 mypy 21개 소스 검사 |
| UI | 두 앱 TypeScript 검사·프로덕션 빌드 통과, 지도 bundle의 큰 chunk 안내 유지 |
| 독립 C4I | 최신 C4I·계약·지리 sdist→wheel, 별도 Python 환경 설치 및 Node·MCP·플랫폼·OpenAI 없는 실행 검증 |

성능 수치는 이 로컬 데모 환경의 결과이며 네트워크 운영 성능 보장은 아니다. 이벤트와 snapshot은 계속 보관하므로 긴 시뮬레이션은 저장량이 증가한다. 기본 회귀용 11개 시나리오와 120개 확장 시나리오를 분리했다. 스크린샷은 artifacts/border-c4i.png와 artifacts/border-platform.png에 보관한다.

### 사용자 Review

1. 기존 실행 터미널에서 Ctrl+C 후 `uv run python scripts/dev.py`로 재시작하고 브라우저를 새로고침한다. .env의 C4I_SCENARIO가 따로 지정돼 있으면 border-demo로 설정한다.
2. 기존 DB라면 C4I의 초기화를 눌러 새 epoch로 전환한다. 제목이 ‘남북 접경 전역 모의 상황’, 전체 객체 수가 120인지 양쪽 UI에서 확인한다. 기존 snapshot 이력은 남는다.
3. 전체 보기·구역 이동·객체 확대를 확인하고 이동 시작 후 사용자 지도 위치가 유지되는지 확인한다.
4. ‘구역별 객체 수’, ‘가용 아군 탱크’, ‘두 모의 객체의 거리’, ‘선택한 방책 설명’을 질의한다. 실행 상세에서 실제 MCP 호출·근거를 확인한다.
5. 도구 설명·입력 모델을 MCP 서버에서 변경한 후 다음 질의에서 재발견되는지 확인할 수 있다. 플랫폼의 설명 복사본을 수정할 필요가 없다.

다음 피드백은 docs/REVIEW.md에 기록하며 이후 Reflect에서 반영한다.

## 2026-10-16 R1–R5 후속 구현

2026-10-15 사용자 Review를 기반으로 구현했다. 다음 사용자 Review는 아직 수행하지 않았다. 아래 결과가 최신이며 이후의 최초 구현 기록은 당시 검증 이력이다.

| 항목 | 구현 및 검증 |
| --- | --- |
| R1 방책 선택 | 비교 대상 runId를 활성 응답과 분리하고 `(runId, courseId)`로 저장. 서로 다른 방책 ID를 가진 연속 응답과 과거 응답의 선택 변경을 브라우저·저장 결과로 확인 |
| R2 대화 연속성 | conversation별 전체 타임라인, 같은 탭 새로고침 복원, 명시적 새 대화. 최근 6턴·8,000 UTF-8 바이트 컨텍스트에 선택한 방책 ID·제목·내용 포함. 전역 실행 이력 200개와 대화 복원 분리 |
| R3 선택 표시 | 선택한 방책을 원래 응답에 표시. 후속 대화·새로고침·선택 변경 후 유지. 422 오류 주입 후 재시도 확인 |
| R4 프롬프트·도구 역할 | 시스템은 정체성·앱 역할·동적 실행 원칙, 도구는 사용 조건·인수·결과·한계. 공통 C4I 도구 설명을 MCP 검색과 native 어댑터가 공유 |
| R5 객체·도구 | 장갑차·지원 차량·무인기 추가. 부대·세부 유형·정비 상태·관측 시각·출처, 정비·부대 필터/집계, 객체 이력 공개 API 및 MCP 도구 추가 |

### 확인한 원인과 수정

- 기존 구현은 대화 전체 대신 활성 응답 하나를 표시했고, 방책 비교·선택도 그 활성 응답에 의존했다. 비교 대상 실행을 별도로 식별하여 과거·최신 응답을 독립적으로 처리한다.
- 다음 턴의 모델 입력에는 답변 문장만 전달되어 선택한 방책 정보가 누락됐다. 선행 테스트 실패를 확인한 뒤 runId·selectedCourseId·선택 방책 원문을 포함했다.
- 작은 화면에서 긴 방책 카드가 오류 표시 영역과 겹쳐 재시도 버튼 클릭이 차단되는 문제가 브라우저 회귀 테스트에서 재현됐다. 카드 영역과 머리말·오류 영역이 내용 높이를 유지하도록 flex 크기 계산을 수정했다.
- 사용자가 처음 경험한 오류의 원본 HTTP 응답은 확보하지 못했다. 해당 오류와 같은 원인이라고 단정하지 않으며, 연속 선택·과거 턴 선택·저장 실패와 재시도의 동작을 회귀 기준으로 검증했다.

### 최신 검증 결과

- 일반 테스트: **30개 통과**, 실제 OpenAI 테스트 2개는 기본 실행에서 제외.
- 실제 GPT: 이전 구현 세션에서 확장된 live 테스트 **2개 통과(44.93초)**. 실제 HTTP MCP 집계·세 방책 생성, 선택한 방책에 대한 후속 응답, geo_measure 호출 및 WGS84 거리·방위 결과 확인. 이후 변경은 비교 화면 CSS와 브라우저 테스트이며 Agent 경로는 동일하다.
- Ruff 검사·포맷 통과, mypy 20개 소스 파일 통과, 두 UI TypeScript 검사·프로덕션 빌드 통과.
- 브라우저: 실제 지도·객체 렌더링, 3턴 대화, 연속 선택, 과거 턴 재선택, 저장 실패 후 재시도, 새로고침 복원, 새 대화 확인. 스크린샷은 artifacts/platform-conversation.png에 보관한다.
- C4I·계약·지리 패키지를 sdist→wheel로 생성하고 artifacts/c4i-isolated의 별도 Python 환경에 재설치했다. Node 경로·LLM 설정 없이 실행하는 독립 배포 테스트 2개 통과.
- 기존 필드만 있는 DB를 다시 열어 조회·tick할 수 있고, 과거 snapshot은 보존된다. 정비·부대 필터 집계, 객체 이력 페이지 이동·빈 결과·고정 시점 이후 조회 거부 및 실제 MCP 검색 설명 일치 확인.

### 구현 범위와 Review 순서

초기 시나리오는 총 11개 객체다. 기존 DB의 현재 상태를 자동 교체하지 않으므로 새 유형을 확인하려면 C4I UI의 초기화로 모의 상황을 새 epoch로 시작한다. 이력은 보존된다. 신규 속성의 과거 미제공 값은 null/unknown으로 처리한다. 정비·가용·운용 상태는 독립적이다.

MCP 도구는 7개, Agent 내부 도구를 합치면 9개다. 추가 도구 c4i_list_entity_history는 원천 이벤트에 포함된 객체별 snapshot 관측 이력이며 변화가 없는 관측도 포함한다. limit은 스캔하는 snapshot 수이고, 빈 items라도 nextAfter가 있으면 다음 페이지가 남아 있다. epoch·sequence 상한을 고정한다.

거리 비교는 기존 목록 조회와 geo_measure를 조합한다. 전용 정렬 도구는 추가하지 않았다. 모든 후보·페이지를 확보하고 거리·동률·0건을 해석하는 것은 Agent의 역할이다. 실시간 데이터 전체를 항상 순회하는 대규모 공간 검색은 이번 범위에 포함하지 않는다.

1. 기존 서버를 Ctrl+C로 종료한 뒤 `uv run python scripts/dev.py`로 재시작하고 브라우저를 새로고침한다.
2. 첫 질의에서 세 방책을 요청하고 선택한 뒤, 같은 대화에서 선택한 방책 설명과 새로운 세 방책을 요청한다.
3. 두 응답의 방책을 각각 선택·변경하고 원래 응답의 표시, 새로고침 복원을 확인한다.
4. C4I를 초기화한 뒤 장갑차·지원 차량·무인기와 정비 상태를 확인한다. 플랫폼에서 부대·정비 현황 및 객체 이력을 질의하고 실행 상세의 도구·근거를 확인한다.
5. 사용자 피드백은 docs/REVIEW.md에 기록한다. 다음 Reflect는 이 Review 후 진행한다.

## 최초 구현 기록

## 구현 범위

- Python workspace: 독립 Mock C4I·독립 MCP Server·Platform API 및 공통 Pydantic 계약/지리 패키지.
- C4I: 실제 지리 좌표의 적아 탱크·함정, 1초 이동, 가용성·속도 제어, SQLite snapshot/이벤트·SSE 재생.
- MCP: 실제 Streamable HTTP 도구 검색·호출, 원천 공개 API 조회·필터·집계, 읽기 전용 권한.
- Agent: OpenAI Responses native 함수 호출·관찰 loop, 같은 run의 시점 고정, 근거/오류 기록, 실행 한도, 최근 대화.
- Platform: snapshot 초기 동기화·SSE 수집·중복 방지·상태 이벤트 자동 분석·대화/분석 이력·단일 방책 선택 저장.
- UI: 실제 MapLibre 지리 배경·적아/유형 심벌·방향 벡터·필터·C4I 제어·분석 상세/근거·세 열 방책 비교.

## TDD와 자동 검증

구현 전 각 기능의 선행 테스트 실패를 확인한 후 구현·수정·통과를 진행했다.

| 검증 | 결과 |
| --- | --- |
| 일반 자동 테스트 | 25개 통과. live GPT 테스트 1개는 기본 제외 |
| Python Ruff 검사·포맷 | 통과 |
| Python mypy | backend/package 19개 소스 파일 통과 |
| React/TypeScript | 두 UI 타입 검사·프로덕션 빌드 통과 |
| 실제 HTTP MCP | 독립 프로세스의 검색·집계·읽기 전용 호출 확인 |
| 실제 1초 이동 | 동일 snapshot의 C4I·플랫폼 위치 일치, tick의 LLM 미실행 확인 |
| 브라우저 E2E | 지리 배경·실제 심벌 렌더링·가용 상태 변경·조회·세 방책 비교/선택·도구 상세 확인 |
| C4I 배포물 | sdist→wheel 재빌드에도 자체 UI/Worker 포함 |
| 독립 실행 | clean Python 환경에 C4I·계약·지리 wheel만 설치, PATH에서 Node 제거 후 자체 UI/API 실행 확인 |
| 프론트엔드 npm audit | 취약점 0건. 설치 중 확인된 지도 라이브러리는 6.14.0으로 수정 |

일반 테스트의 모델은 테스트 전용 어댑터이며 production 진입점에서 사용하지 않는다. MCP·C4I·브라우저 연결은 실제 실행한다. 테스트 모델의 방책 문구를 실제 GPT 분석 품질로 평가하지 않는다.

실제 GPT 테스트는 사용자가 로컬 .env의 모델 ID를 수정한 뒤 재실행하여 통과했다(2026-10-15, 1개 통과, 26.65초). OpenAI native tool calling → 실제 HTTP MCP → C4I 집계 호출, 적 탱크 3대의 근거 데이터, 세 가지 방책 생성 및 결과 근거 ID를 확인했다. 아래 명령으로 재검증할 수 있으며 실제 OpenAI API 비용이 발생한다.

```powershell
uv run pytest -m live tests/test_openai_live.py -q
```

API 키는 코드·보고서·스크린샷에 포함하지 않았으며 .env는 Git 제외를 확인했다. 인증 오류도 원문 자격증명을 결과에 노출하지 않도록 테스트했다.

## 현재 구현값과 검토할 차이

- 8개 모의 객체·서해안 지역, 일시 정지로 시작한다. 원천 tick은 1초다.
- 상태/속도 PATCH는 상태 이벤트를 생성하며 자동 분석 대상이다. 위치 tick은 자동 분석 대상이 아니다.
- 같은 대화의 최근 완료 6턴을 최대 UTF-8 8,000바이트로 제한했다. 명세의 입력 토큰 상한 제안보다 보수적인 단순 길이 제한이다.
- 개별 HTTP/LLM 클라이언트와 전체 loop deadline은 제한하며 필수 조회 실패를 기록한다. 일반적인 실행 예산은 모델 응답 12회/Tool 20회/120초다.
- 큐와 결과를 SQLite에 저장하고 재시작 시 실행 중 작업은 interrupted로 남긴다. 자동 checkpoint 복구는 제공하지 않는다.
- 조회/제어 토큰을 비우는 로컬 기본 실행과 토큰을 지정한 연결 모두 검증했다. 외부망 운영용 사용자 인증은 범위 밖이다.
- 지형/해상 경로 제약과 실제 장비 성능은 모사하지 않는다. 이력 자동 정리도 구현하지 않았다.
- 지도 포함 UI 초기 JS는 약 1.3MB, Worker는 별도 자산이다. Vite의 큰 chunk 안내는 남아 있다.

## Review 안내

실행 방법은 루트 README.md, C4I 독립 제공은 services/mock-c4i/README.md를 따른다. 사용자 Review에서 실제 모델 설정, 질의별 도구 선택·근거·답변 품질, 지도/방책 UI를 확인한다. Review 종료 후 확정된 피드백과 구현값을 명세에 Reflect한다.
