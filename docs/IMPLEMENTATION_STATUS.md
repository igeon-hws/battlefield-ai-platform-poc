# IMPLEMENTATION_STATUS

## 현재 상태

2026-10-26 Data Fabric Graph 탐색·버전 선택 구현과 관련 검증을 마쳐 **Human Review 대기**다. 기존 비교 UI 회귀 한 건의 snapshot 준비 오류는 아래에 남긴다. 현재 기준은 c2-domain-demo-v3, Ontology3.0.0/adapter3.0.2다. [ARCHITECTURE](ARCHITECTURE.md)는 구현 구조/실행 방법, [PLAN](IMPLEMENTATION_PLAN.md)은 다음 유효 작업이다. 이 문서는 실제 결과·제약·주요 이력만 관리한다.

## 구현 범위

- 독립 육군/해군 native UI·API·SQL·시뮬레이터. 공유 runtime은 ledger/auth/snapshot/event 등 기계 기능이다.
- 원천 MCP2, Fabric API/콘솔·catalog/projection/분석 context, Neo4j Builder, Semantic MCP7개. 공개 원천 API·실제 MCP 경계를 유지한다.
- 검토 문서 hash/version·adapter·규칙 분리, 명시적 association ER, 안정 Graph와 live 상태 소유권 분리.
- 단일 native tool loop, OFF helper 차단/원천 문서 허용, ON 현재-run 근거 평가·집계·유형×상태 계산, 기준보고/T0 고정·비교 대화 격리.
- F1~F7·주장 배지·계산 표·비교 조건·세 방책 선택. 제품4개와 legacy의 정적 UI5개.
- 실행별 UTF-8 파일 로그와 핵심 경계 주석. 로그는 기본 var/logs/agent/<runId>.log이며 전체 근거는 DB/UI trace가 기준이다.

## Data Fabric Graph 탐색·버전 선택 — 2026-10-26

생성된 READY v3 Graph를 생성 일시(KST)·데이터셋·짧은 ID로 선택하고, 개요·객체 검색·주변 관계·원천 문서·규칙·assertion 근거를 읽는 UI/API를 구현했다. 공통 선택 버전을 기존 규칙/build 콘솔에도 적용했다. 최초 활성 선택 이후 조회 버전을 고정하고 전체 ID 복사·ID 충돌 구분·누락 정보 표시·페이지 밖 선택 유지를 제공한다. 그래프는 SVG와 실제 저장 관계만 사용하며 목록/키보드 대체 경로와 좁은 화면 전환을 제공한다.

API는 기존 인증을 적용하고 버전/유형/필터·깊이/개수 상한을 서버에서 검증한다. 신규 탐색은 전체 `DomainService.model()`을 사용하지 않는다. READY Graph의 기존 domainJson을 조회하므로 기존 데모 데이터/Graph를 수정하거나 재생성하지 않았다. Agent/MCP/ON·OFF 정책·도구 수 변경과 유료 모델 호출은 없다.

| 검증 | 이번 실행 결과 |
| --- | --- |
| 선행 실패 | 신규 API 404, 신규 UI 선택기 미존재, 새 build 삽입 중 offset 페이지 중복을 각각 확인 후 구현/수정 |
| 신규 전체 테스트 | `test_graph_explorer.py`, `test_graph_explorer_ui.py`, `test_graph_explorer_contract.py`: 12 passed /17.85초. 실제 별도 Neo4j/API/정적 UI 경로와 명시적 mock UI 경계를 구분 |
| 문서·규칙 이동 추가 검사 | 실제 Neo4j/UI 1 passed /8.49초: 동일 버전 규칙 조회와 원천 문서 상세 이동 |
| 기존 관련 회귀 포함 | Graph/Fabric/API/원천 UI/비교 UI 포함 14 passed, 1 failed /289.44초. 아래 실패 참조 |
| 저장소 검사 | Ruff check 통과, format 117파일 통과, mypy 66 source files 통과, 계약 export 실행. TypeScript 검사·전체 UI build 및 최종 Fabric 재빌드/정적 패키징 통과 |
| 시각 확인 | 1440×960·640×900 Playwright 캡처 확인: `artifacts/fabric-explorer-desktop.png`, `artifacts/fabric-explorer-mobile.png` |
| 제한 초과 합성 측정 | 별도 폐기용 test build의 210노드 star/self-loop/평행 관계 fixture: neighborhood 0.053초, JSON 30,642 bytes, 반환200노드/201관계·partial. 대규모 성능 보장은 아님 |

검증한 반례는 인증/Neo4j 장애, 없는/비READY 버전, 잘못된 관계·깊이·cursor, 버전별 페이지 격리, 새 build 추가 중 목록 중복, endpoint 완결성·상한, 고립 노드·평행 관계, 짧은 ID 충돌·누락 메타데이터, 늦은 응답 후 버전 변경, Graph 장애 중 Catalog 사용이다. 테스트는 별도 Neo4j 컨테이너/volume을 사용하고 생성한 test build만 정리했다.

**남은 회귀 제약:** `test_semantic_comparison_ui_runs_two_isolated_columns_and_restores_history`가 “완전 비교” 대기에서 실패했다. 테스트 SQLite에는 run 생성 전 `ValueError: incomplete or inconsistent source snapshot capture`가 저장됐다. 단독 재실행도 같은 준비 오류로 실패(137.98초)했다. 이 실패는 통과로 처리하지 않으며 이번 기능에서 해당 v2 비교 준비 경로를 수정하지 않았다. v3 Graph 탐색·도메인 비교를 포함한 나머지 선택 회귀는 통과했다.

JSON 문자열 검색/정렬과 summary 집계는 DB 스캔이 가능하며 검색 전용 인덱스·대규모 배치 최적화는 없다. 기본 1-hop100노드/150관계, API 최대2-hop200노드/300관계, 화면 누적200노드/300관계로 제한한다. 일부 절차/정의는 payload이며 없는 관계를 만들어 표시하지 않는다. 실제 실행 중 서비스에는 재시작과 브라우저 새로고침 후 반영된다.

## 최근 구현과 검증 — 2026-10-22

로그 신규 계약 테스트10개의 ModuleNotFoundError RED부터 구현했다. JSON 문자열 credential 노출, stat 권한 오류 전파, 취소 중 응답 수 오기록의 반례도 실패 확인 후 수정했다. 파일 생명주기는 Runtime, 모델/도구 이벤트는 선택적 AgentLoop callback으로 연결했다. legacy/v3 모두 적용하며 비공개 reasoning을 수집하지 않는다. I/O 실패·마스킹·취소·재시작 복구·부분 usage를 검증했다.

| 검증 범위 | 당시 실제 결과 |
| --- | --- |
| 비live/performance/Neo4j/UI 일반 회귀 | 136 passed, 30 deselected /108.99초 |
| test_domain_platform.py -m neo4j | 1 passed /64.71초; 실제 원천/MCP/Builder/Neo4j/Fabric의 OFF/ON 로그와 DB callId·도구명·evidenceId 대조 |
| 최종 로그/Agent/경계/근거 관련 회귀 | 37 passed /10.58초 |
| Ruff check/format, mypy, diff check | 통과; format115 Python files, mypy64 source files |

이는 중첩된 검사 집합이며 합산하지 않는다. 환경은 Python3.12.10, var/implementation-venv/Scripts/python.exe, TEMP/TMP=var/test-tmp, 캐시=var/uv-cache·var/test-cache였다. 기존 .venv는 없는 Python 경로를 가리켜 보존하고 별도 환경을 사용했다. 테스트 Neo4j는17687이었다. 프론트 변경이 주석뿐이라 이 변경에서 UI/GPT를 다시 실행하지 않았다.

가독성 예시 var/logs/agent/sample-fixture-8ed0fa2ea488.log는 **합성 fixture provider** 결과로 실제 GPT 답변이 아니다. 파일을 열어 한글·모델2회/도구1회·evidenceId·usage unavailable 표시를 확인했다. 강제 종료 후 마지막 usage는 미확인이며 다음 시작에서 recovery_interrupted로 표시한다. 자동 로그 삭제는 없다.

## v3 구축·UI 수정 검증 이력

독립 tests/fixtures/c2-domain-demo-v3에 T0/T1·원천8개 문서·F1~F7 gold를 고정했다. 문서 hash/미래 knownAt/복합 키/ACK·원본 근거/다른 run evidence/만료 지원/불완전 scope 반례를 테스트했다. 일부 범위의 빈 조회를 전체0으로 집계하는 RED 후 거부하도록 수정했다. 생산 코드는 gold를 읽지 않는다.

| 당시 확인 | 결과/해석 |
| --- | --- |
| C0 초기 기준 | 97 passed/4 failed/13 deselected; wheel 캐시/권한2, 외부 지도2 제약 확인 |
| v3 비UI·비Neo4j 일반 회귀 | 119 passed/28 deselected,120.58초; 독립 wheel2 포함 |
| 전체 Neo4j 최종 회귀 | 13 passed/134 deselected,198.19초; 실제 Docker 중단/복구·비교 UI 포함 |
| 원천/Fabric UI·기존 지도 UI | 3 passed/16.08초, 2 passed/39.78초 |
| adapter3.0.2 provenance 수정 | 8 passed/30.33초; 무관한 REPORT-LINEAGE 참조를 기계적 provenance로 분리 |
| v3 비교 browser | 1 passed/58.16초; 모바일 조건 영역 높이/스크롤 수정, artifacts/domain-comparison.png |
| 정적 UI/계약 | 계약 export·TypeScript·Vite5개 빌드/복사 통과; 지도 bundle 크기 경고 잔존 |

초기 sandbox 실행의 Docker 접근1·비교 대기2, UI의 외부 지도2·비교1 실패는 Docker/네트워크 허용 및 실제 두 run 예산에 맞춘 테스트 대기 후 재검증했다. 앱 실행 예산을 늘려 통과시키지 않았다.

EX-01 반복 표시는 DB에 문서가 추가된 것이 아니라 associationId보다 documentId를 먼저 사용한 React key 충돌이었다. 자체 ID 우선/system·tab key로 수정하고 참조→관측→함정 탭 반복 전환의 개수2/4/2를 검증했다. 원천/Fabric UI4 passed/1 deselected,24.56초, TypeScript/Ruff 통과·두 UI 재빌드. DB/seed/Graph 변경 없음.

## 실제 GPT 결과와 품질 한계

아래는 당시 로컬 모델 gpt-6-luna, 동일 snapshot/질문/문서/T0와24/20/120초 예산 실험이다. 원본 artifact를 보존했다. 로그 추가 이후 새 GPT 검증으로 간주하지 않는다.

| artifact | 결과 |
| --- | --- |
| artifacts/domain-live-20261021T091030Z.json | 초기 저장 run7개. F1 ON 시간/도구 문제, 이후 F4 ON MCP ReadTimeout 중단; 저장되지 않은 호출도 있어 전체 비용 집계 아님 |
| artifacts/domain-live-20261021T091825Z.json | F1~F7 OFF/ON14회 completed,574.83초. run 시간합561.20초, input662627/output35686 tokens. completed≠14개 정답 |
| artifacts/domain-evaluation-20261022.json | F3 절차/F6 계산 일치. F2/F4/F5 ON 필수 규칙 coverage 누락. F7 ON 집계2회 실패 후 수동 표 작성으로 계산 검증불가 |
| artifacts/domain-live-20261022T005227Z.json | 교차 집계 수정 후 F7 추가2회 completed,145.96초. OFF6 tool/37.73초, ON10 tool/88.27초 |
| artifacts/domain-evaluation-f7-20261022.json | ON 고유7/상태4·1·1·1 gold 일치. input/output OFF35014/2297, ON131535/3684 |

저장 run은7+14+2=23개이며 중단된 추가 호출의 usage를0으로 세지 않는다. 달러 비용은 환산하지 않았다. GPT artifact는 adapter3.0.1 때 생성됐으며3.0.2 기계적 provenance 수정 후 새 실측으로 바꿔 쓰지 않는다. 규칙/Graph 테스트와 자연어 답변의 충분한 근거는 별개다. 핵심 사실·금지 결론·주장 충분성은 Human Review 대상이다.

## 알려진 제약과 검토 지점

- 단일 사건 INC-1·고유7자산·5부대·3접촉·T0/T1 최소 데모다. 대규모/실전 성능 근거가 아니다.
- previousName은 하나이며 완전한 조직 변천 이력이 아니다. 관계 기간은 build 입력 시점 기준으로 해석한다. stable 입력 변경 없이 시계만 만료 경계를 넘는 재해석은 충분히 검증되지 않았다.
- Graph 조회는 현재 노드/관계를 읽어 Python에서 필터링하는 부분이 있어 대규모 최적화가 아니다. 일부 정의/절차 연결은 payload다. 임의 문서 추출·Graph 편집·RDF/OWL·범용 CDC는 없다.
- 원천 문서와 규칙은 개발 시 작성한 합성 지식이다. 독립 군 전문가의 교리 인증을 받지 않았다. EX-01 내 공통 통합 정책 등 지식 소유권 분리가 완전하지 않다.
- Fabric 콘솔은 READY v3 활성 버전 최초 선택과 과거 버전 목록 선택을 지원한다. 활성 버전이 없으면 직접 선택해야 한다. 실제 버전/근거가 없으면404이며 all로 규칙12개를 볼 수 있다. active 문자열을 의미 조회 버전으로 전달하지 않는다.
- interpret_concept가 넓은 질문에 규칙 전체를 반환해 컨텍스트가 커질 수 있다. 규칙 종류별 실행 계약과 참조 검증 오류는 사용자에게 불명확할 수 있다. 근거 ID 유효성이 문장 의미 정확성을 증명하지 않는다.
- 최근 논의한 효율/근거 구조/규칙 계약 개선은 아직 승인된 다음 구현 계획이 아니다. 실행 로그 한 건만으로 OFF/ON 효용을 입증하지 않는다.

## 이전 호환 이력

2026-10-16 두 원천/Neo4j·Semantic 도입 후 OFF의 로컬 집계에서 의미 helper가 호출되던 누락을 S8에서 차단했다. 그 이전 ON/OFF 비교는 새 격리 정책의 증거로 재사용하지 않는다. v2의 원천8/고유7·가용4/불가2/미상1 기대값은 v3의4/1/1/1과 다르다. v1의 의도적 충돌 fixture도 역사/negative 검증용이다.

snapshot stable-export404는 공개 snapshot 경로/기준 정합 문제를 수정했다. 대화404는 이전 DB의 conversationId를 새 DB에 재사용한 경우를 전용 오류/1회 UI 복구로 분리했고 API/Chromium/경계 회귀21 passed(24.75초)를 확인했다. 초기 단일 C4I/도구 discovery/대화·방책/접경120개 구현은 legacy에 보존한다. 이전 세부 수정 내역은 Git 이력, 측정 원본은 artifacts와 var의 기존 데이터에 남으며 이번 통합에서 삭제하지 않는다.

## 문서 통합 — 2026-10-26

기술 설계·원천 조사·Agent·Ontology를 ARCHITECTURE, 시나리오/평가를 PRD, 실행 기록을 이 문서로 통합했다. 중복·폐기 설계 문서는 제거하고8개 문서를 유지한다. REVIEW 원문·제품 코드·데이터·artifact·현재 Review 단계는 보존한다. 문서 검증 결과는 이 절에 기록하며 과거 테스트를 이번 실행 결과로 주장하지 않는다.

문서 검증: docs의 파일8개 일치, 로컬 Markdown 링크41개 연결, UTF-8 읽기, REVIEW SHA256 불변을 확인했다. battlefield-sdd는 skill-creator의 quick_validate로 통과했다. Git diff 공백 검사도 통과했다. 문서/지침만 바꿔 제품 회귀나 유료 GPT 호출은 추가 실행하지 않았다. 이전 조사명은 seed/fixture의 출처 문자열에 남지만 살아 있는 문서 링크는 아니며, 관련 공개 출처를 ARCHITECTURE에 보존했다. 서비스별 README의 실행 안내도 ARCHITECTURE로 통합하고 루트 README는 진입 링크로 줄였다.
