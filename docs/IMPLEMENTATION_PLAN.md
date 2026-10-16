# Implement 계획

현재 단계: **Review (Human)**, 2026-10-16. S8-1~5 구현 및 일반 97개·실제 Neo4j 9개·GPT 시나리오 검증을 완료했다. 추가 GPT 호출·실패/부분 완료·계측 한계는 IMPLEMENTATION_REPORT.md의 S8 절을 따른다. 기존 P0~P7·Builder 복구·평가는 역사적 기록으로 보존한다. 다음 사용자 Review는 아직 수행하지 않았다.

## 다음 구현 계획 — Semantic 실행 경계와 일관된 데모 데이터

### 입력과 우선순위

입력은 [REVIEW](./REVIEW.md)의 Semantic OFF/ON 구분 및 사용자 채팅의 보충 설명이다. Review의 날짜 문자열은 기존 기록과 같으므로 날짜만으로 다른 Review와 혼동하지 않고 내용으로 추적한다.

1. **OFF:** 원천 C4I 도구와 일반 계산만 사용한다. Semantic 해석·관계 해소·동일성 판정 코드를 호출하지 않는다.
2. **ON:** Semantic Layer가 제공하는 개념·관계·동일성 해석을 추가로 사용한다.
3. **기본 데모 원천 데이터의 상충을 제거한다.** 사용자가 확인한 동일 UAV의 ATCIS 가용/KNCCS 불가용을 의도적 시연 조건으로 유지하지 않는다. 배속도 상충하지 않도록 정리한다.

이 절이 이전 공유 Semantic 집계 및 충돌 중심 시나리오를 대체하는 **S8 구현 기준**이다. 코드와 문서를 이 기준으로 수정했으며 이전 구현/실측 결과를 새 기준에서 검증된 것으로 취급하지 않는다. 사용자 Review 원문은 보존한다.

### 확인한 문제와 수정 경계

현재 `agent/multi_tools.py`는 양 모드 공통 `aggregate_evidence`에서 `normalize_equipment`와 `resolve_identity`를 직접 실행한다. 원천 `list_equipment`/`summarize_equipment`도 공통 kind/availability로 필터·집계한다. 원천 MCP의 설명에는 데이터셋/유일성/타입 호환성을 이용한 동일성 판정 규칙이 들어 있다. 따라서 Semantic MCP 미접속만으로 OFF 격리를 통과 처리할 수 없다.

| 경로 | OFF | ON |
| --- | --- | --- |
| 원천 공개 MCP | native 필드·코드·조직/배속·식별참조 원문 조회 | 같은 원문과 같은 snapshot 조회 |
| 원천 계약 설명 | 필드·단위·조회 범위·원천이 공개한 코드 설명 | 동일 |
| 일반 계산 | 근거 레코드 수, 명시적 필드값의 빈도·동등 비교·합계, 좌표 계산 | 동일 |
| 조직 예하 범위/공통 개념/가용성 의미 | 서버가 자동 해석하지 않음 | Semantic 서비스가 버전 있는 규칙·근거로 반환 |
| 서로 다른 원천 ID의 canonical 연결 | 공통 집계 코드가 생성하지 않음 | Semantic 조회 결과의 검증된 연결만 사용 |
| Graph·규칙표·해석 helper | Agent의 OFF 실행 경로에서 호출/주입 금지 | Semantic API/MCP 뒤에서 실행 |
| 지도/원천 UI 표시 | 화면 표시용 변환 허용, 그 결과를 Agent 근거로 전달하지 않음 | 동일 |

필드 이름에 접근하거나 동일한 원천 레코드의 중복 페이지를 제거하는 것은 기계적 처리다. `R → 공통 가용`, `AIR+UNMANNED → uav`, 조직 예하 재귀 확장, 공통 연습 ID를 canonical 동일 객체로 확정하는 것은 Semantic 처리다. 원천 응답의 native ID·공통 연습 참조를 감추거나 질문/프롬프트를 약하게 만들어 OFF를 실패시키지 않는다. OFF의 LLM이 원천 사실로 스스로 추론한 답은 추론·근거를 구분해 허용하며, 서버가 확정한 Semantic 결과와 구분한다.

### 구현 순서와 TDD 종료 조건

#### S8-1. OFF 실행 경계의 실패 테스트와 원천 도구 계약

- [x] 실제 MCP 도구 설명·schema·응답·원천 조회 handler와 집계 helper의 의미 처리를 먼저 추적한다. legacy/지도/Graph Builder 경로와 OFF 분석 경로를 구분해 기록한다.
- [x] OFF 분석 중 Semantic 개념/상태/유형 매핑, 조직 범위 해소, `resolve_identity`를 호출하면 예외를 내는 테스트를 먼저 작성한다. import 문자열 검사만으로 격리를 증명하지 않는다.
- [x] 원천 Agent용 목록/집계는 native 유형·상태 코드와 명시적 직접 배속으로 조회한다. 기존 공통 kind/availability 인자를 native 계약으로 바꾸고 schema/설명/호출 테스트를 함께 수정한다. 응답에 공통 availability·canonical ID·계산된 예하 범위를 넣지 않는다.
- [x] 원천의 필드·단위·코드 설명은 남기고, 두 체계 연결 정책·조직 고유 해석 규칙·Semantic 권고 절차는 원천 도구 설명에서 제거한다. 두 모드에 동일 원천 도구를 제공한다.
- [x] source-runtime/플랫폼의 표시용 정규화는 Agent 조회 경로와 분리한다. 지도·시뮬레이터는 유지하며 OFF의 근거/대화/자동 컨텍스트에 표시용 정규화 결과가 섞이지 않게 한다. snapshot ID/epoch/hash는 시점 고정 메타데이터로만 사용한다.

대상: `packages/source-runtime`, `services/atcis-mcp`, `services/knccs-mcp`, 플랫폼 `agent/multi_tools.py`, `multi_runtime.py`, source MCP/semantic Agent 테스트. 종료 조건: OFF의 실제 source MCP 조회가 동작하면서 Semantic helper 호출·연결·주입은 0건이다. Graph Builder의 배경 실행까지 중지시키는 전역 스위치를 만들지는 않는다.

#### S8-2. Semantic 서비스 소유 해석과 일반 계산 분리

- [x] `aggregate_evidence`의 모드별 동작 실패 테스트를 먼저 작성한다. OFF에 identity/scope Semantic 입력을 넣으면 거부하고 raw 집계가 canonical ID나 의미 상태를 생성하지 않는지 확인한다.
- [x] 공통 계산 helper는 현재 run의 완결된 native 근거를 대상으로 지정된 필드/값의 수량만 계산한다. 중복 페이지 제거는 `(system, epoch, nativeId)` 기준이며 체계 간 장비 병합을 하지 않는다. 근거 없는 LLM 생성 레코드를 계산 입력으로 받지 않는다.
- [x] ON의 개념·유형·상태 코드 해석, 조직 범위, 동일성 규칙은 SemanticService/API/MCP 소유로 둔다. 기존 5개 도구의 typed 계약을 필요한 만큼 확장하며 플랫폼에 규칙을 복사하거나 별도 Agent/프레임워크를 추가하지 않는다.
- [x] ON 집계는 Semantic 근거가 제공한 source refs·해석 규칙/코드 대응·canonical 그룹을 검증하고 적용하는 계산만 수행한다. 원천 가용 상태는 고정 snapshot에서 조회한다. Graph에 실시간 상태를 저장하지 않는다.
- [x] Semantic 장애 시 ON의 공유 Python helper/직접 Neo4j/숨은 규칙표 fallback을 금지한다. 기존 native 단일 loop·dynamic discovery·시점 고정·대화 격리·이벤트 실행은 유지한다.
- [x] 일반 질의·비교·자동 이벤트 분석에 같은 경계를 적용한다. 과거 ON history/read_evidence/지도 결과나 모델용 tool instruction으로 OFF를 보강하지 않는다.

종료 조건: 동일한 입력을 주어도 OFF helper는 원천 레코드/필드값 집계만, ON은 실제 Semantic 근거를 사용한 공통 해석/연결 집계를 반환한다. OFF에서 공통 문자열을 만들지 않는다는 이유로 사용자 자유 텍스트 추론을 금지하거나 정답을 강제로 실패 처리하지 않는다.

#### S8-3. 충돌 없는 기본 seed와 독립 gold

- [x] 새 기본 시나리오를 `semantic-demo-v2`로 관리한다. 이전 v1 원천/Graph/평가/실패 결과는 보존하며 새 결과로 덮어쓰지 않는다.
- [x] `U-A01`과 `C-K77`은 공통 `EX-U01`의 같은 UAV이며 양쪽 모두 **가용**으로 통일한다. 유형·아군 구분 등 동일 객체 속성도 일치시킨다.
- [x] 공유 UAV의 B11/S11 관계는 서로 다른 전속 소속으로 주장하지 않도록 **명시적 비전속 공동지원 배속**으로 통일한다. 각 원천에 배속 역할을 원문으로 기록하고 Semantic 관계에도 그 역할/출처를 보존한다. 필드 이름/설명이 전속 소유를 뜻하면 함께 정정한다. LLM이나 Builder가 공동지원이라는 사유를 추측해서 생성하지 않는다.
- [x] 동일 객체의 상태·유형·소속/배속 역할 일관성을 두 독립 production seed와 별도 expected fixture로 검사하는 실패 테스트를 먼저 작성한다. seed가 gold를 import하지 않는다.
- [x] 정상 데모에서 충돌 수치는 0이어야 한다. 충돌 방어 코드를 삭제하지는 않으며, 오류 검증용 충돌은 별도 negative fixture에만 둔다. 정상 UI/평가에 negative fixture를 기본 제공하지 않는다.

| 시나리오 | v2 기대값/검증 |
| --- | --- |
| S1 조직 범위 | 모의 1사단 예하 탱크 4건: 가용 2·불가 1·미확인 1. D2 장비 제외 |
| S2 이종 통합 | 원천 기록 8건, 검증된 고유 자산 7개: 가용 4·불가 2·미확인 1·충돌 0. 공동지원 UAV를 두 번 세지 않음 |
| S3 동일 객체 | 서로 다른 ID U-A01/C-K77을 EX-U01로 연결하고, 일치하는 상태와 명시적 공동지원 관계·출처·규칙 근거를 설명. 원인 불명 충돌 시연 제거 |

기존 source DB는 자동 reset하지 않는다. Implement에서 v2로 새 DB를 생성하거나 운영자가 명시적으로 v2 reset을 선택하도록 실행 안내/시나리오 표시를 제공한다. 사용자의 기존 v1 화면에 새 seed가 적용됐다고 주장하지 않는다.

#### S8-4. 문서·UI·평가 기준 동시 정렬

- [x] PRD FR-16/18, ARCHITECTURE, SEMANTIC_ARCHITECTURE, ONTOLOGY_DESIGN, AGENT_DESIGN, SEMANTIC_DEMO, UI_GUIDE, README 및 ADR의 OFF 정의·계산 경계·v2 시나리오/기대 수량을 같은 기준으로 수정한다. 이 작업은 Implement에 포함한다.
- [x] UI의 두 열에 mode·원천 snapshot·데이터셋 버전·Semantic 근거 유무를 표시한다. 기본 데이터에서는 “상충 1개” 설명/지표/질문 예시를 제거하고 “동일 객체 연결·중복 제거”를 보여준다. 실제 오류/negative fixture까지 0으로 숨기지는 않는다.
- [x] `evaluation.py`는 모드별 능력에 맞게 검사한다. OFF의 raw 근거/수량과 ON의 Semantic 근거/연결/고유 수량을 구분한다. OFF가 7개를 추론했으면 native 근거에 따른 모델 추론인지, 금지된 helper가 실행됐는지를 따로 평가한다.
- [x] 실행 manifest에 계약/의미 경계 버전을 남기고 과거 비교는 이전 정책 버전으로 표시한다. 이전 15쌍 평가를 새 격리 기준의 효과 입증에 재사용하지 않는다.
- [x] docs/IMPLEMENTATION_REPORT.md의 이전 “OFF 차단 정상” 결론을 당시 MCP 접근만 검사한 결과로 한정하고, Review에서 발견한 공통 helper 경계 누락을 명시한다. 과거 성공/실패 수치를 재작성하지 않는다.

종료 조건: 문서·tool instruction/schema·기본 seed·예상값·화면 설명·평가가 OFF 의미와 무충돌 시나리오에 관해 일치한다. 코드가 바뀌기 전 문서만으로 수정 완료를 선언하지 않는다.

#### S8-5. 통합 검증과 다음 Human Review

- [x] OFF Semantic endpoint/helper를 실패하도록 차단한 실제 MCP 통합, ON 실제 Neo4j/Semantic MCP 통합, 미완결 페이지·잘못된 해석 근거·다른 run 근거 거부를 검증한다.
- [x] 두 원천 독립 wheel/UI·지도/vector/SSE/reset·이벤트 분석·멀티턴·기존 세 방책 선택·Builder scope 격리·과거 이력 보존을 회귀 검증한다. 일반/Neo4j/브라우저 검증과 Ruff/mypy/계약 export/UI 빌드를 수행한다.
- [x] 로컬 GPT 설정으로 v2의 S1~S3를 ON/OFF **각 1쌍** 실제 검증한다. 3쌍/6 run 및 실패를 별도 artifact에 남긴다. 최소 검증에서 미해결 문제가 있으면 원인 해결 후 추가 호출을 별도로 기록한다. 15쌍 전체 성능 재평가는 이번 기본 범위에 자동 포함하지 않는다.
- [x] 원천/Graph/정책 버전·실제 Semantic 호출 여부·정답/원천 집계·출처·도구/모델 호출·토큰·준비/실행 시간·추론/미확정 표시를 기록한다. OFF 실패를 Semantic 효과의 전제로 두지 않는다.
- [x] 보고서에 실제 명령/통과/실패/미검증과 v2 실행 순서를 기록한 후 STEP/AGENTS를 Review로 전환한다. 사용자 REVIEW.md는 변경하지 않는다.

핵심 수용 조건은 **OFF의 Semantic 코드 실행 0건, ON의 해석 근거 추적 가능, 정상 v2 seed의 충돌 0건**이다. 실제 실행 명령과 결과는 구현 보고서 S8 절을 따른다. 사용자 Review와 커밋/푸시는 임의로 수행하지 않는다.

## 이전 구현 계획과 결과 — P0~P7

아래는 이전 baseline의 계획과 완료 기록이다. 공통 상태 매핑/ER를 양 모드에 허용하거나 v1 충돌을 기본 데모로 쓰는 부분은 S8로 대체했으며 당시 구현 사실을 보존하기 위해 남긴다.

## 고도화 구현 범위와 순서

### Review 중 오류 수정: Builder 작업 큐 격리

사용자 채팅의 Semantic ON `stable-export 404`를 입력으로 처리한다. :4300의 원천 snapshot을 같은 Neo4j를 공유한 검증용 :5420 Builder가 가져가 :5100 원천에 조회한 것이 원인이다.

- [x] 원천 주소가 다른 두 Builder의 요청 ID 충돌과 재시작 시 다른 작업 재대기화를 실제 Neo4j에서 실패 테스트로 재현한다.
- [x] source endpoint hash를 작업 ID·BuildRequest scope·조회/대기 큐·RUNNING 복구·checkpoint 키에 적용한다. 토큰은 scope에 포함하지 않는다.
- [x] 잘못 처리된 요청 1건은 이전 오류를 보존하고 원래 Builder로 재대기시켜 READY를 확인한다. 기존 실패 run/답변을 수정하지 않는다.
- [x] 관련 Graph/비교 회귀 6개와 Ruff/mypy 검사를 통과했다. 사용자 Review로 돌려주며 간섭한 검증 서버는 중지 상태를 유지한다.

배포: 실행 중 Python 프로세스는 변경 코드를 자동 reload하지 않으므로 이후 큐 격리 코드 적용에는 full 프로필 재시작이 필요하다. 기존 scope 없는 BuildRequest는 감사 기록으로 보존하며 새 worker가 임의 인수하지 않는다. 새 요청은 scoped ID로 생성한다. 이 변경은 다중 writer 운영을 공식 지원한다는 뜻이 아니며 독립 환경은 별도 Neo4j DB/인스턴스가 기본이다.

입력: 사용자의 Mock ATCIS/KNCCS 독립 확장, Neo4j·Ontology·ER·Semantic API/MCP, 같은 원천 snapshot의 ON/OFF 비교 요구. [PRD](./PRD.md) FR-10~18, [아키텍처](./SEMANTIC_ARCHITECTURE.md), [Ontology](./ONTOLOGY_DESIGN.md), [시연](./SEMANTIC_DEMO.md)가 설계 기준이다. 아래 계획에 따라 구현하며 체크박스와 구현 보고서에 실제 결과를 기록한다.

기존 코드 확인: [runtime.py](../services/platform-api/src/platform_api/runtime.py)는 단일 c4i_url/mcp_url과 수집 경로를, [tools.py](../services/platform-api/src/platform_api/agent/tools.py)는 고정 c4i_* allowlist·단일 self.snapshot·로컬 도구 2개를 가진다. 따라서 설정에 서버 주소만 추가하는 변경으로 끝나지 않는다. P5에서 원천별 cursor/snapshot·신뢰 서버별 바인딩·집계 근거 모델을 함께 확장한다. 기존 loop/provider/schema 변환은 가능한 한 유지한다.

| 단계 | 요구사항 | 먼저 작성할 실패 테스트 | 구현 범위 / 종료 조건 |
| --- | --- | --- | --- |
| P1 계약·fixture | FR-11/12/15/18 | 이종 코드/단위 매핑·조직 경로·ER 중복/충돌·독립 gold 집합 | 타입·규칙 버전·SourceRef/SnapshotSet·S1~S3/반례 고정. 테스트가 production 규칙으로 정답을 만들지 않음 |
| P2 두 독립 원천 | FR-10/11 | 다른 서비스 없는 wheel 실행·자체 UI/API/시뮬레이터·조직 raw 조회·snapshot/SSE reset | 기존 C4I를 ATCIS로 단계 전환, KNCCS 추가, DB/포트/epoch 독립. 기존 동작 회귀 통과 |
| P3 Neo4j·Builder | FR-12/13/15 | 실제 Docker Neo4j에 version 제약·재구축·실패 build 비공개·gap/reset·이동 rebuild 방지 | 공식 driver·고정 image/lock·명시적 매핑·초기 build/동기화·build retention. 무근거 edge 0 |
| P4 Semantic 서비스 | FR-14/15 | API/MCP 동일 의미 결과·bounded 탐색·동명 모호성·원천 근거·버전 강제 | 재사용 Python core/API와 thin MCP. 쓰기/임의 Cypher 노출 없음 |
| P5 Agent/수집 확장 | FR-11/16 | 실제 다중 MCP discovery·namespace 충돌·OFF Semantic 미연결·고정 시점·집계/대화 격리 | 기존 single loop·strict 변환 재사용, 원천별 registry/projection·aggregate_evidence. 기존 대화/방책 유지 |
| P6 비교/UI | FR-17 | 동일 manifest·빈 대화/근거 격리·Graph 불일치·한쪽 실패·과거 run 고정 | 비교 준비/실행 API, 세 앱 원천 표시·ON/OFF 두 열·관계/충돌 근거 상세 |
| P7 통합/평가 | FR-18 | S1~S3 기계 대조·반례·장애 격리·기존 지도/이벤트/배포 회귀 | 실제 GPT 반복 비교와 도구/token/시간 기록. 실패도 보고하고 사용자 Review로 이동 |

각 단계에서 테스트 실패 확인 → 최소 구현 → 통과 → 관련 통합/정적 검사를 수행한다. 기존 원천 DB를 자동 분할/초기화하지 않는다. 새 DB/합성 시나리오를 별도로 생성하고 기존 snapshot/보고서/회귀 fixture를 유지하는 전환을 기본으로 한다.

### 이번 Plan의 기본안

설계 문서의 가상 스키마·소규모 gold fixture·안정 관계 변경 때 전체 build 방식·Semantic API와 MCP 별도 프로세스·aggregate_evidence 도구 추가·빈 대화의 순차 비교를 기본안으로 채택한다. 사용자가 조정하면 해당 명세와 계획을 함께 갱신한다. 도구 수가 늘었다고 Agent 프레임워크·Multi-Agent를 도입하지 않는다.

| 항목 | 구현 기본안 |
| --- | --- |
| 주소 | ATCIS 4100/MCP 4200, KNCCS 4110/MCP 4210, 플랫폼 4300, Semantic API 4400/MCP 4410, Neo4j 7474/7687. 모두 설정 가능 |
| 기본 모드 | 일반 대화/자동 분석은 OFF. ON은 명시적 선택. 모드 전환은 새 대화 |
| 비교 | 두 원천을 pause한 합성 fixture로 시작. pause/resume은 운영자 제어이며 Agent 도구로 제공하지 않음. 일반 비교 API가 몰래 pause하지 않음 |
| 시점 | 원천별 snapshot 집합 고정. 실행 중 채집은 capture skew 2초 이하를 초기값으로 검증하고 초과는 준비 오류 |
| 조회 제한 | Semantic maxDepth 8, pageSize 기본/최대 100. continuation으로 추가 조회하고 잘림을 완전 결과로 취급하지 않음 |
| 예산 | 초기 model 12회/tool 20회/120초로 측정한 결과, S2 OFF의 정상 원시 조회가 model 한도에 걸려 고도화 기본값을 model 24회/tool 20회/120초로 조정했다. 양 모드에 동일 적용하고 run/manifest에 기록한다. AGENT_MAX_ITERATIONS/MAX_TOOLS/DEADLINE_SECONDS로 설정. 서버별 discovery 5초·전체10초, Graph 준비30초 유지 |
| Graph 보관 | PoC에서는 READY build/snapshot 자동 GC를 도입하지 않음. 명시적 reset은 운영자가 대상 DB/volume을 확인한 뒤 별도 실행하며 참조 데이터 삭제를 자동화하지 않음 |
| 버전 | P0에서 현재 lock/환경 기록, P3 시작 시 공식 Community image tag/digest와 Python driver를 실제 연결·제약 테스트로 검증 후 compose/uv.lock에 고정. 최신 tag 사용 금지 |
| 반복 평가 | S1~S3 각각 쌍 비교 5회, OFF→ON/ON→OFF 순서 교대. 기본 15쌍/30 run이며 추가 호출/재시도는 따로 기록 |

## 실행 순서와 중간 확인점

`P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7` 순서로 진행한다. 사용자 요청 없이 서브에이전트/병렬 위임을 사용하지 않는다. 각 단계는 검증 가능한 변경 단위로 나누고 이전 단계의 종료 조건을 충족한 뒤 진행한다. 중간 확인점은 AI의 기술 검증이며 Human Review를 대신하지 않는다.

- **P2 종료:** 두 원천이 독립 동작하고 원시 관계를 실제 MCP로 조회할 수 있다.
- **P4 종료:** 원천 고정 snapshot → 검증된 Neo4j build → Semantic API/MCP 관계 근거를 확인할 수 있다.
- **P6 종료:** 같은 질문의 격리된 OFF/ON run과 UI 비교가 작동한다.
- **P7 종료:** 실제 GPT·Neo4j·MCP 검증과 회귀 결과를 보고하고 Review 단계로 이동한다.

### P0. 기존 동작·환경 기준 확보

- [x] 현재 `uv.lock`, 프론트엔드 lock, Python 버전, 테스트 marker/실행 명령과 서비스 실행 방식을 기록한다. 비밀 값은 출력하지 않는다.
- [x] 기존 일반 테스트·UI 빌드·정적 검사를 실행해 출발 상태를 기록한다. 기존 실패와 새 변경의 실패를 구분한다.
- [x] Docker CLI/daemon 및 사용 가능한 포트는 읽기 검사한다. Plan 단계에서는 실행하지 않으며 Implement에서 확인한다. 실제 Graph 검증이 불가능하면 대체 mock 결과를 통과로 보고하지 않는다.
- [x] 기존 `mock-c4i`/`c4i-mcp`, 11개 fixture·120개 지도 시나리오, 기존 플랫폼 이력의 보존 범위를 확인한다.

주 변경 대상: Implement에서 `docs/IMPLEMENTATION_REPORT.md`에 이번 고도화 섹션 추가. 이 단계는 환경/회귀 확인이므로 의미 없는 새 테스트를 만들지 않는다. 종료 조건: 재현 가능한 baseline 결과와 환경 제약이 기록됨.

### P1. 계약·Ontology·독립 gold fixture

- [x] 먼저 `tests/test_ontology.py`, `tests/test_source_contracts.py`를 작성한다(이하 신규 파일명은 구현할 목표).
- [x] `packages/ontology`에 SourceRef/SnapshotSet, 개념/관계 타입, rule/version, 모드·coverage·ER 결과 모델을 정의한다. source-specific 공개 계약과 의미 규칙을 분리한다.
- [x] ATCIS/KNCCS native schema·상태/유형/좌표·속도 매핑을 구현한다. 안정 hash에는 조직/배속/식별·유형과 dataset/epoch 범위를 반영하고 위치·속도·가용 상태·tick 시각은 제외한다.
- [x] `tests/fixtures/semantic-demo-v1/`에 원천 입력과 독립 expected JSON을 분리한다. Builder는 expected 파일을 import하지 않는다.
- [x] S1 가용 탱크 2, S2 raw 8/canonical 7/확정 가용 3, S3 동일 UAV 및 상태·배속 충돌을 검증한다. 별도 dataset으로 동명/미해결/잘못된 공통 ID 반례를 추가한다.

실패 테스트: 좌표 순서/knots 변환, unknown 코드, system/epoch ID 충돌, 가짜 동일성, 예하 cycle·유효 범위. 종료 조건: 원천 계약·매핑·gold 검증이 통과하고 Ontology 패키지가 OpenAI/Neo4j/원천 서비스에 의존하지 않음.

### P2. 독립 Mock ATCIS·KNCCS와 원천별 MCP

- [x] P2a: 기존 구현을 재사용해 `services/mock-atcis`, `services/atcis-mcp`와 지상 UI를 만든다. 기존 C4I 명령/회귀는 전환 기간 유지한다. 기존 패키지 제거는 별도 정리이며 이 계획의 필수 범위가 아니다.
- [x] P2b: `services/mock-knccs`, `services/knccs-mcp`와 해상 UI를 추가한다. DB·설정·시뮬레이터·reset·원천 계약을 분리한다. 상대 서비스 내부 모듈을 import하지 않는다.
- [x] 각 원천에 불변 snapshot, 원시 조직/상하위·배속/식별 기록, 안정 export/hash, 구조 변경 이벤트를 제공한다. 원천 ID를 다른 체계 ID로 사전 병합하지 않는다.
- [x] 각 MCP는 자기 원천 공개 API만 호출한다. 기존 snapshot/객체/집계/변경/이벤트/이력 기능과 원시 조직·관계·배속·식별 조회의 description/typed schema를 소유한다.
- [x] 원시 관계를 조회하는 API/MCP 계약은 OFF에서도 충분한 페이지/필터/근거를 제공한다. 준비된 Semantic scope를 원시 도구에 넣지 않는다.
- [x] `frontend/apps/mock-atcis`, `mock-knccs`와 정적 UI 빌드/배포 경로를 추가한다. 원천별 단독 README와 `.env.example` 설정을 작성한다.

선행 테스트: `test_atcis.py`, `test_knccs.py`, `test_source_mcp.py` 및 기존 `test_packaging.py` 확장. 서로 다른 독립 프로세스/실제 MCP 연결, token·pagination·단일 tick·snapshot 불변·reset/gap을 확인한다. 깨끗한 별도 환경에서 각 wheel은 상대 체계/플랫폼/Neo4j/OpenAI/Node 없이 UI·API·이동을 제공해야 한다. 종료 조건: 두 원천 독립 실행과 실제 MCP 조회 통과.

### P3. Neo4j 저장소·Graph Builder·변경 동기화

- [x] `compose.yaml`에 Neo4j만 추가한다. localhost·named volume·인증 환경변수·readiness를 설정하고 검증된 image/driver를 고정한다. 시작 명령에 volume 삭제를 넣지 않는다.
- [x] `packages/semantic-core`의 GraphRepository 및 `services/graph-builder`를 추가한다. official driver의 명시적 database·parameterized query·version-scoped 제약을 사용한다.
- [x] 공개 원천 API의 고정 snapshot export → deterministic ER/관계 → BUILDING → 검증 → READY 공개를 구현한다. build metadata·안정 근거 원문/hash·규칙 버전을 보존한다.
- [x] 반복 build는 중복 없는 MERGE, 관계 endpoint의 같은 graphVersion, 검증 실패 시 기존 active 유지, 공개 transaction 내 active/cursor 갱신을 보장한다.
- [x] structural SSE의 중복/공백/reset·worker 재시작을 처리한다. 이동·가용 상태 변경만으로 Graph를 다시 만들지 않는다. reset 후 epoch 재검증을 생략하지 않는다.
- [x] 비교 준비용 build 요청은 Builder의 인증된 내부 `POST /internal/build-requests`(기본 :4420)로 받는다. 입력은 검증할 SourceSnapshotSet/규칙 버전이며 임의 node/edge/Cypher를 받지 않는다. 단일 worker가 순차 처리하고 요청 ID/상태를 GraphBuild에 보존해 재시작·중복 요청을 처리한다. 플랫폼은 요청/상태 조회만 하며 직접 Neo4j 쓰기를 하지 않는다. 이 관리 기능은 Semantic 조회 MCP와 분리한다.

선행 테스트: `test_graph_builder.py`(순수 매핑/ER), `test_neo4j.py`(실제 DB), `test_graph_sync.py`(공개 source HTTP/SSE). BUILDING 중 실패·cycle·식별 충돌·재실행·source gap/reset·미래 버전 조회 거부·관리 요청 인증/중복/재시작을 검증한다. 테스트 DB/컨테이너는 데모 데이터와 분리한다. 종료 조건: 실제 Neo4j에 S1~S3 관계/근거가 정확히 저장되고 실패/복구 테스트 통과.

### P4. 재사용 Semantic API와 thin MCP

- [x] SemanticService와 `services/semantic-api`, `services/semantic-mcp`를 구현한다. API/MCP에서 규칙을 중복 구현하지 않는다.
- [x] interpret_concept, resolve_unit_scope, find_equipment_refs, resolve_entity, get_semantic_evidence의 다섯 조회를 구현한다. API/도구의 버전 입력·응답 모델을 일치시킨다.
- [x] 동명 후보/미해결/충돌과 빈 결과·잘림·Graph 장애를 구분한다. 조직 경로와 모든 source/rule evidence를 반환하고 현재 가용 상태는 반환하지 않는다.
- [x] build 상태/입력 hash 조회를 플랫폼에 제공한다. Builder 작업 접수는 Agent 조회 MCP 권한과 분리한다.

선행 테스트: `test_semantic_api.py`, `test_semantic_mcp.py`. 실제 Neo4j + HTTP API + MCP에서 같은 결과/근거를 대조한다. depth/page 제한, 잘못된 버전, arbitrary Cypher/쓰기 capability 부재를 확인한다. 종료 조건: Agent 없이도 API/범용 MCP Client로 조직·동일성·근거를 조회 가능.

### P5. 다중 원천 수집·native Agent·모드 격리

- [x] `platform_contracts`, `app.py`, `repository.py`, `runtime.py`를 원천 registry/SourceSnapshotSet/모드·build 참조로 확장한다. 원천별 수집 task·커서·projection·연결 상태를 분리한다.
- [x] `mcp/client.py`, `agent/tools.py`에 신뢰 서버별 세션/allowlist·namespaced native bindings를 추가한다. 기존 `mcp/schema.py`, loop, provider를 재사용하며 실제 tools/list 설명/schema를 사용한다.
- [x] OFF는 Semantic 연결/discovery 없이 작동한다. ON은 source+semantic 조회를 허용하되 고정 순서를 강제하지 않는다. ToolRunner가 원천별 snapshot/Graph 버전과 schema를 검증한다.
- [x] aggregate_evidence를 추가한다. 현재 run 근거의 완결성·scope·명시적 식별 증거를 검증하고 raw/canonical·unknown/conflict를 분리한다. read_evidence/geo_measure도 source namespace와 고정 snapshot을 확인한다.
- [x] 모드별 대화와 근거를 격리한다. 이전 ON 대화/지도 canonical 결과/다른 run evidence로 OFF를 보강하지 않는다.
- [x] 이벤트 자동 분석은 enqueue 시 모드/시점 고정, 상태/구조 이벤트 중복 제거, ON build 대기·시간 초과를 처리한다. tick 자동 분석은 금지한다.

선행 테스트: `test_multi_source.py`, `test_semantic_agent.py`, 기존 discovery/agent/provider/platform/resilience 테스트 확장. 서로 같은 tool명·entityId·eventId, 잘못된 서버/epoch, Semantic 함수명 위조, 과거 근거 유출, 누락 페이지·충돌 집계, 한 원천/MCP 단절을 검증한다. 종료 조건: 실제 MCP + 결정론적 model adapter로 OFF/ON 실행·격리·기존 대화/세 방책/선택 회귀 통과.

### P6. 비교 준비·실행 API와 세 앱 UI 통합

- [x] 비교 상태와 manifest 저장/API를 구현한다. 질문/모델/프롬프트·도구 변환 버전·snapshot 집합·Graph 안정 hash 일치 확인 후 빈 대화 두 run을 생성한다.
- [x] preparing/ready/failed와 양 run 진행을 따로 저장한다. 한쪽 partial/failed는 incomplete로 표시하고 재시작 시 중복 run 생성 없이 interrupted/재시도 상태를 처리한다. 재시도는 새 실행 ID를 남긴다.
- [x] 플랫폼 지도는 원천별 표시·필터·복합 객체 키를 적용한다. Semantic 상태와 OFF/ON 선택·대화 분리·비교 진입을 추가한다.
- [x] 고정된 두 열 결과/trace/evidence, 관계 경로, 출처별 상태·배속 충돌, raw/canonical 단위, 기준 시각·버전을 표시한다. 기존 세 방책 비교/선택은 별도 run에 유지한다.
- [x] `scripts/dev.py`에 기존 legacy, 두 원천+플랫폼 OFF, Semantic 포함 전체 실행 프로필을 추가한다. 원천 단독 명령은 이 스크립트 없이 가능해야 한다. 하나의 앱 종료가 다른 단독 실행 앱을 종료하지 않으며, script는 자신이 시작한 child만 정리한다.
- [x] `.env.example`, 계약 export/프론트엔드 생성 타입, build_ui.py, README 실행·검증 안내를 실제 명령으로 갱신한다. 실행 스크립트가 Docker volume/기존 DB를 reset하지 않는다.

선행 테스트: `test_comparisons.py`, `test_semantic_ui.py`(Playwright Python), `test_dev.py`/`test_packaging.py` 확장. 동일 snapshot/미래 Graph 거부·빈 대화·한쪽 실패·Graph 부재 OFF 실행·새로고침/이전 비교 보존·좁은 화면·키보드·방책 선택 독립성을 확인한다. 종료 조건: 브라우저에서 세 시나리오를 비교하고 실제 호출·관계·상태 근거를 열어볼 수 있음.

### P7. 통합 회귀·실제 GPT 평가·사용자 검토 준비

- [x] 일반/Neo4j/UI 통합 테스트와 독립 wheel 실행을 완료한다. map/vector/SSE/reset·native loop·이벤트 분석·멀티턴·방책 선택의 기존 기능을 검증한다.
- [x] 별도 opt-in `test_semantic_live.py`와 평가 스크립트로 로컬 OpenAI 설정을 사용한다. 실제 API가 불가능하면 live 미검증으로 보고하며 skip을 성공에 합산하지 않는다.
- [x] S1~S3 gold와 ID 집합·유형별 수량·근거/시점/격리를 기계 대조하고, 원인 추정/동명 명확화 등 답변 품질을 기록한다. model adapter 결과는 live 효용 평가로 사용하지 않는다.
- [x] 15쌍 비교의 각 run/manifest, 모델 ID, tool/model call, token/usage, 준비/실행 시간, 순서·실패/한계를 저장한다. 비용은 사용량·모델/단가 근거가 있을 때만 계산하며 모델 우수성을 미리 단정하지 않는다.
- [x] Graph 종료→OFF 지속, 한 원천 단절→coverage 표시, 구조 변경→새 Graph, 과거 비교 보존을 시연한다. 120개 회귀 규모는 기존 performance test와 분리해 필요한 경우 실행한다.
- [x] `IMPLEMENTATION_REPORT.md`에 실제 명령·결과·실패/미검증·모델/의존성 버전·문서 차이를 기록한다. 모든 필수 검증 통과 후 STEP/AGENTS를 Review로 바꾸고 사용자가 실행할 데모 순서를 제공한다.

종료 조건: FR-10~18의 수용 기준 및 유지 기능 회귀 통과, 실제 Neo4j/MCP/GPT 검증 기록, 재현 가능한 실행 안내. 외부 환경 문제로 필수 검증을 못 했으면 구현 완료를 선언하지 않고 남은 항목을 명시한다. 사용자 REVIEW.md는 AI가 대신 작성하거나 완료 처리하지 않는다.

## 검증 명령과 기록 정책

아래 명령으로 검증한다. 실측 통과 수와 실패 기록은 구현 보고서를 따른다.

```powershell
# 현재 제공되는 회귀·정적 검사
uv run pytest
uv run ruff check services packages scripts tests
uv run ruff format --check services packages scripts tests
uv run mypy services packages
npm --prefix frontend run build

# P3 이후 추가할 실제 Neo4j 통합 marker
uv run pytest -m "neo4j and not live and not performance" -q

# P6 이후 추가할 Semantic UI 검증 (정적 UI 빌드·Chromium 필요)
uv run pytest tests/test_semantic_ui.py -q

# P7 추가할 실제 GPT 평가 (명시적 opt-in, API 비용 발생)
uv run pytest -m live tests/test_semantic_live.py -q
```

P3에서 neo4j marker를 등록하고 기본 pytest에서는 live/performance/neo4j를 제외한다. 일반 회귀가 Docker/LLM 없이 가능한 구조를 유지하되, 정식 검증은 일반 + 실제 Neo4j + UI + live 결과를 각각 기록한다. fixture unavailable로 skip한 통합 테스트를 전체 통과로 보고하지 않는다. 동작/오류 계약을 검증하는 테스트를 먼저 작성하며 파일 존재/구현 문자열만 확인하는 테스트는 만들지 않는다.

## 전환·복구와 범위 관리

- 기존 소스/플랫폼 DB는 자동 이관·덮어쓰지 않는다. 새 기본값은 별도 `var/atcis.db`, `var/knccs.db`, `var/platform-vnext.db`를 사용한다. 이전 플랫폼은 기존 모드로 이전 이력을 열 수 있도록 보존한다. 저장 형식 변경에는 schema version과 비호환 오류를 명시한다.
- P2~P5 전환 동안 기존 테스트를 무작정 새 fixture로 치환하지 않는다. 회귀가 새 모델에 그대로 적용되지 않으면 원래 의도를 보존한 테스트로 옮기고 이유를 보고한다.
- 의존성/디렉터리 추가와 서비스 wiring은 단계별로 수행한다. 중간 실패 시 이전 프로필·DB·READY build가 유지된다. 기존 실행 단위의 대규모 이름 정리/삭제는 검증과 분리한다.
- 범위 밖: 실제 체계 내부 모델, 명령 실행, Multi-Agent/Agent 프레임워크, RDF/OWL 추론 엔진, 벡터 DB, fuzzy/LLM 자동 병합, 범용 CDC/대규모 운영/전체 서비스 컨테이너화.
- 추적표 P1~P7과 개별 체크박스에 실제 결과를 반영하고 필요 시 문서를 수정한다. 계획 변경을 이유로 새 기능을 먼저 구현하거나 Human Review/Reflect를 임의로 완료하지 않는다.

### 기존 완료 기록

R6–R7은 이전 단일 C4I baseline의 구현·검증 완료 기록이다. 아래 “다음 구현 계획” 제목과 체크된 항목은 당시 이력이며 현재 차기 작업 목록이 아니다.

## 다음 구현 계획 — 2026-10-16 Review 반영 (R6–R7)

입력: docs/REVIEW.md의 두 항목. 120개·유형 분포·구역·p95 2초 목표의 기본안을 사용자의 구현 지시에 따라 적용했다. 현재 DB는 자동 초기화하지 않았으며 새 시나리오 적용은 사용자 조작으로 수행한다.

| ID | 사용자 Review | 구현 목표 | 우선순위 |
| --- | --- | --- | --- |
| R6 | MCP 서버가 도구 정의를 소유하도록 정리 | 서버의 tools/list에서 설명·schema를 발견하고 native tool로 변환 | P0 |
| R7 | 남북 접경 지역 전반으로 지도 변경·객체 증가 | 접경 지역을 아우르는 모의 시나리오·지도 메타데이터·확장 규모 검증 | P1 |

순서: R6의 실패 테스트 → 서버 소유 정의 및 발견·변환 → R7의 시나리오 계약·고정 fixture 테스트 → 원천 시뮬레이터·지도 적용 → 규모·통합 검증 → 사용자 Review. 각 변경은 테스트 실패 확인 → 구현 → 통과 순서로 진행한다.

### R6. MCP 서버가 C4I 도구 정의 소유

구현 전: 공유 설명 import·플랫폼의 중복 C4I 입력 모델·이름만 반환하는 목록을 사용했다. 구현 후: MCP 서버가 정의를 소유하고 플랫폼이 전체 tools/list로 발견한다.

목표 흐름:

```text
MCP 서버: 이름·설명·입력 schema 소유
  → MCP Client: tools/list 전체 페이지 조회
  → 플랫폼: 허용 목록 적용·native 함수 형식 변환·run별 정의 고정
  → GPT: 도구 선택
  → ToolRunner: 인수·권한·snapshot 검증
  → MCP tools/call → C4I 공개 API
```

- [x] C4I 설명을 MCP 내부로 이동하고 서버 typed 함수에서 입력 schema를 생성했다. 공통 도메인 계약은 유지하며 플랫폼의 설명 import·중복 C4I 호출 모델을 제거했다.
- [x] MCPClient가 description·inputSchema를 포함한 전체 tools/list 페이지를 반환한다.
- [x] 발견한 정의를 native strict 함수로 변환한다. read_evidence·geo_measure만 내부 정의로 유지한다.
- [x] typed filter·groupBy·참조·enum·선택 필드를 보존한다. optional→required/nullable 변환 후 호출 시 원천 기본값·생략으로 정규화하고 원래 schema로 검증한다. 미지원 schema는 거부한다.
- [x] 허용 목록·snapshot/epoch/sequence·예산·근거 발급은 플랫폼에 유지했다. 발견한 임의 도구를 자동 허용하지 않는다.
- [x] run 시작 시 발견하고 해당 run에 고정한다. 다음 run의 새 세션에서 재발견하며 실행 도중 정의를 교체하지 않는다.
- [x] LazyMCP에서 발견·호출을 같은 세션으로 처리한다. 발견 최대 5초, 실패 시 오류를 기록하고 C4I 정의를 노출하지 않는다. 일반 설명은 계속 가능하며 로컬 C4I 복사 fallback은 없다.
- [x] 실행 상세·근거·이벤트·직접 답변·방책·대화 회귀와 실제 발견 정의의 모델 전달을 검증했다.

완료 기준·선행 테스트:

- MCP 서버의 설명 또는 허용된 인수 계약을 바꾸면 플랫폼의 중복 정의 수정 없이 다음 발견 시 모델에 반영된다. 플랫폼이 공유 설명 파일을 직접 읽어 통과하는 테스트는 사용하지 않는다.
- 실제 HTTP tools/list → 변환 → 모델에 전달한 정의 → tools/call의 연결을 확인한다. 서버 검색의 pagination·스키마 검증 오류·허용 목록 밖 도구·내부 도구 이름 충돌을 검증한다.
- 실제 C4I 필터 enum·선택 필드·groupBy·중첩 schema가 변환 전후 동일한 조회 의미를 갖는다. snapshot 불일치·미래 이력 조회·잘못된 인수는 계속 거부한다.
- MCP 미연결·검색 실패·재연결·캐시 갱신 및 run 중 정의 고정을 검증한다. 도구 없는 답변이 MCP 장애에 불필요하게 종속되지 않는지 확인한다.
- 실제 GPT opt-in 검증에서는 발견한 도구로 집계·거리 계산을 수행하고 근거를 제시하는지 기록한다. 테스트 어댑터의 성공과 구분한다.

### R7. 남북 접경 지역 전반의 모의 시나리오

구현 전: 서해안 모의 객체 11개와 고정된 지도·이동 경계를 사용했다. 구현 후: 시나리오 metadata·구역·120개 기본 seed를 사용하고, 100+20개 페이지와 원천 집계를 검증했다.

범위: 실제 지도 배경에서 남북 접경의 서부·중부·동부와 양쪽 연안 해역을 함께 볼 수 있도록 넓힌다. 객체·부대명·소속·속도·상태는 합성 시나리오로 구성하고 실제 부대 배치 자료는 사용하지 않는다. 접경선/구역 overlay를 추가한다면 출처와 정확도를 명시하고 시연용 구역과 구분한다.

- [x] scenario.py에 시나리오 이름·버전·bounds·initialBounds·zones·seed를 분리하고 snapshot/API로 metadata를 전달한다.
- [x] 서부·중부·동부 남/북측 육상 6구역과 양쪽 해역 2구역을 정의하고 실제 지도 렌더링을 확인했다. zone 경계에서 정지하는 단순 이동이며 지형·도로·항로 추종은 없다.
- [x] 기본 120개: 탱크 40·장갑차 24·지원 차량 20·무인기 12·함정 24. 고정 seed·DEMO ID/부대명으로 재현한다.
- [x] 소속·가용·정비·운용 상태와 이동/정지·unknown을 혼합한 합성 데이터다.
- [x] 매초 WGS84 이동과 구역 경계 정지를 유지한다. 기존 DB·과거 snapshot의 시나리오를 보존하고 초기화 때 새 설정·epoch를 적용한다. 이전 플랫폼 metadata 보완이 상태 이벤트를 건너뛰지 않음을 검증했다.
- [x] 두 UI가 원천 metadata의 이름·범위를 사용한다. 전체 보기·구역 이동을 제공하며 tick 후 줌/팬을 유지한다.
- [x] 100+20개 페이지·matchedCount·전체/구역 집계를 검증했다. 객체 전체를 모델 초기 컨텍스트에 자동 삽입하지 않는다.
- [x] 11개 회귀 fixture와 120개 확장 시나리오를 분리했다.

완료 기준·선행 테스트:

- 양쪽 UI에서 같은 scenarioId·전체 객체 수·위치·유형·상태를 확인한다. 전체 보기에서 서부·중부·동부 시연 구역을 확인하고 확대 후 장비를 식별할 수 있다.
- 120개 초기 목표의 seed 재현성·ID 유일성·좌표 유효성·구역 경계·육해상 시연 구역·속성 분포를 검증한다. 100+개 조회의 다음 페이지 및 원천 집계가 전체 fixture와 일치한다.
- 60초 연속 실행에서 1초 tick·SSE 수집을 관찰하고 source/platform의 동일 snapshot 위치 일치를 확인한다. 초기 성능 목표는 로컬 데모 환경에서 상태 전달 지연 p95 2초 이내다. 측정 환경·표본·실제 결과를 보고서에 남기고 미달 시 최적화 또는 규모 조정 근거를 제시한다.
- 새 시나리오 초기화·이전 DB 재시작·과거 snapshot 재조회·새 epoch 수집·사용자 지도 이동 유지·지도 연결 실패 시 객체/목록 유지를 확인한다.
- 실제 MCP 집계·객체 상세·변화/이력 도구가 확장 데이터에서도 동작한다. tick만으로 LLM 호출이 증가하지 않는지 확인한다.
- 독립 C4I wheel에 시나리오 정의와 UI를 포함하고, Node·MCP·플랫폼·OpenAI 없는 별도 Python 환경에서도 새 시나리오가 실행된다.

### R6–R7 구현 전 확인 및 인계

- [x] 사용자의 구현 지시에 따라 기본안의 규모·구역·목표를 채택했다. 발견은 run별·최대 5초, strict 변환 실패는 명시적 실패다.
- [x] PRD·아키텍처·Agent 설계·UI 가이드·README·독립 C4I 안내·ADR을 현재 구현에 맞게 갱신했다.
- [x] 일반 테스트 39개·실제 GPT 2개·60초 성능 1개·독립 배포·타입/빌드와 마지막 구역 집계 관련 8개 재검증을 보고서에 기록했다. 성능 목표 p95 2초에 대해 측정값은 0.2768초다.
- [x] 사용자 Review 절차를 보고서에 제공했다. 다음 Review와 Reflect는 사용자 검토 후 진행한다.

## 이전 구현 계획 — 2026-10-15 Review 반영 (R1–R5 완료)

입력: docs/REVIEW.md의 `2026/10/15 17:05` 피드백과 이후 프롬프트·도구 역할 분리 논의. 아래 체크박스는 후속 구현 결과다. 검증 근거와 한계는 docs/IMPLEMENTATION_REPORT.md의 2026-10-16 기록을 따른다. 기존 구현 결과는 하단에 보존한다.

### 리뷰 추적 및 순서

| ID | 사용자 Review | 구현 항목 | 우선순위 |
| --- | --- | --- | --- |
| R1 | 첫 방책 선택 후 이어지는 채팅에서 방책 선택 오류 | 실행별 방책 선택의 상태·API·UI 연결 수정 | P0 |
| R2 | 한 세션에서 채팅과 conversation context 유지 | 대화 단위 타임라인 및 후속 질의 컨텍스트 | P0 |
| R3 | 선택한 방책을 해당 채팅에 표시 | 선택 결과의 메시지 내 표시·저장·복원 | P0 |
| R4 | 시스템 프롬프트와 도구 instruction 역할 분리 | 역할·실행 원칙과 개별 도구 계약 분리 | P1 |
| R5 | 객체 종류·속성·tool 확장 | 모의 상황 조회 Use Case에 기반한 계약·MCP 확장 | P2 |

실행 순서: R1 오류 재현 → R2 대화 상태 구조 정리 → R1·R3 선택 연결 및 표시 → R4 → R5 → 통합 검증. 각 항목은 실패 테스트를 먼저 작성한 뒤 구현하고 통과시킨다.

### R1. 연속 대화에서 방책 선택 오류 수정

- [x] 연속 질의·선택의 회귀 테스트를 작성하고 runId/courseId 연결 및 422 오류 주입·재시도를 검증했다. 최초 사용자 오류의 원본 응답은 없어 같은 원인이라고 단정하지 않는다.
- [x] 활성 run에 의존하던 비교·선택 상태를 조사하고, 작은 화면에서 오류 영역이 재시도 버튼을 가리는 문제를 재현·수정했다.
- [x] 방책 선택은 해당 응답의 `(runId, courseId)`에 귀속시킨다. 다른 턴의 활성 상태 변경이 기존 방책의 선택 대상을 바꾸지 않도록 한다.
- [x] 성공 응답은 해당 턴에 반영하고, 실패는 비교 창에서 확인·재시도할 수 있게 표시한다.

완료 기준·테스트: 같은 대화에서 두 턴 연속 선택 성공, 과거 턴과 최신 턴 각각 올바른 run에 저장, SSE 갱신 뒤 선택 유지. 잘못된 courseId와 미완료 run은 API가 거부하며 다른 턴 상태는 보존한다. API 테스트와 브라우저 회귀 테스트로 검증한다.

### R2. 세션 내 대화 연속성과 컨텍스트

- [x] 사용자가 새 대화를 시작하기 전까지 같은 conversationId를 유지하고 사용자 질문·응답을 시간순 타임라인에 누적 표시한다. 새 질의로 이전 응답을 대체하지 않는다.
- [x] 각 턴에 runId·실행 상태·근거·방책을 연결하고, SSE 갱신 결과를 해당 실행에 연결한다. 자동 이벤트 분석은 사용자 대화에 섞이지 않게 식별한다.
- [x] 대화 이력을 열면 그 conversation의 전체 턴을 복원한다. 새로고침 시 선택 중인 conversation을 복원하고, 명시적 새 대화는 별도 ID로 시작한다.
- [x] 다음 턴에는 최근 대화와 선택한 방책의 출처 runId·courseId·내용을 전달한다. 기존의 간단한 최근 이력 한도를 유지하며 오래된 조회 결과를 최신 상태로 취급하지 않는다.

완료 기준·테스트: 3턴 이상 대화가 같은 ID로 이어지고 UI에 누적된다. “선택한 방책을 설명해줘”가 선택 정보를 전달받는다. 이력 열기·새로고침·새 대화·처리 중 중복 제출을 검증한다. 현재 상황 질의에는 새 snapshot을 조회한다.

### R3. 선택한 방책의 채팅 내 표시

- [x] 세 열 비교 및 선택 기능을 유지하고, 선택 완료 시 원래 응답에 방책 제목·선택 상태를 표시한다.
- [x] 비교 창을 닫거나 후속 질의를 보내도 선택 표시를 유지한다. 같은 턴에서 선택을 바꾸면 해당 턴의 표시만 갱신한다.
- [x] 서버의 selectedCourseId를 기준으로 이력·새로고침 시 복원하고, 선택을 실제 C4I 제어·명령 실행으로 처리하지 않는다.

완료 기준·테스트: 서로 다른 두 턴의 선택을 동시에 확인할 수 있다. 선택 변경·저장 실패·새로고침을 포함해 UI 표시와 저장 결과가 일치한다.

### R4. 시스템 프롬프트와 도구 계약 분리

- [x] 시스템 프롬프트에는 단일 분석 Agent의 정체성, 앱 내 역할, 합성 모의 데이터 환경, 요청 → 도구 선택 → 결과 관찰 → 다음 행동/답변의 동적 반복 원칙을 둔다.
- [x] 근거·추론 구분, 불확실성, 도구 데이터의 지시 불신 등 공통 원칙을 유지한다. 개별 도구의 필드·호출 요령은 도구 설명으로 이동한다. 기존 로컬 프롬프트를 기반으로 보완했다.
- [x] 각 도구 설명·입력 schema에 사용 시점, 선행 조건, 입력 의미·단위·범위, 반환값, 오류·한계를 명시한다. snapshot 고정, pagination과 matchedCount, 가용성과 운용 상태의 차이 등을 해당 계약에 배치한다.
- [x] MCP 도구 검색과 native 어댑터가 C4I 도구 설명을 공유하고 실제 검색 결과의 일치를 검증한다.
- [x] geo_measure는 같은 evidence의 items에 두 객체가 있어야 하는 현재 제약과 거리(m)·방위각·WGS84 계산 범위를 명시한다. 필요한 선행 조회를 설명하고 경로 거리·도달 시간으로 확대 해석하지 않는다.
- [x] loop 종료 한도·도구 권한·snapshot·결과 검증은 하네스에 유지한다. 도구 불필요 요청의 직접 답변과 정확히 세 방책이라는 앱 출력 계약도 보존한다.

완료 기준·테스트: 실제 HTTP MCP의 도구 검색·호출 계약, native 입력 검증, 직접 답변, 복수 도구 순차 호출, 근거 인용, 세 방책 출력을 확인한다. 모의 객체 거리 비교는 알려진 좌표의 결정적 계산과 비교한다. 실제 GPT 검증은 별도 live 실행으로 도구 선택·응답을 기록하며 문구 변경만으로 모델 동작을 보장했다고 판단하지 않는다.

### R5. 객체·속성·도구 확장

초기 탱크·함정과의 호환성을 유지하고 계획의 유형·속성 후보를 아래 범위로 구현했다. 미제공 값은 null/unknown이며 실제 성능 정보는 추가하지 않았다.

- [x] 조회 시나리오: 유형·소속·가용성별 현황, 정비 중 장비, 최근 상태 변화, 지정 영역의 모의 객체 현황, 모의 객체 간 거리 비교.
- [x] 장갑차·지원 차량·무인기, 세부 분류·소속 부대·정비 상태·관측 시각·출처를 추가했다. 정비 상태는 serviceable/maintenance/unknown, 나머지 추가 필드는 미제공 시 null이며 가용·운용 상태와 독립적이다.
- [x] 기존 목록·집계 도구의 필터를 확장하고 c4i_list_entity_history를 공개 C4I API 기반의 새 MCP 도구로 추가했다.
- [x] 거리 비교는 기존 목록과 geo_measure를 조합한다. 전체 후보·페이지·동률·0건 처리 원칙을 도구 계약에 명시했다. 별도 정렬 도구는 추가하지 않았다.
- [x] Pydantic 계약 → C4I 저장소·snapshot·필터·집계 → MCP → Agent schema → 생성 TS 계약·지도 심벌·상세 UI에 일관되게 반영했다. 이전 DB 재실행·누락 필드 기본값·과거 snapshot 보존을 검증했다.
- [x] 확장 도구도 합성 시나리오의 조회·계산으로 제공하고 C4I 읽기 전용 경계를 유지한다. 실제 장비 성능이나 교전 효과를 추정하는 필드는 이번 범위에 추가하지 않는다.

완료 기준·테스트: 확정한 신규 유형·속성을 C4I와 플랫폼이 동일하게 표시하고 MCP 조회·집계 결과가 원천과 일치한다. 누락·미상·0건·페이지 경계·과거 snapshot·리셋을 검증한다. 확정되지 않은 후보는 구현 완료로 처리하지 않는다.

### 후속 구현의 최종 검증과 인계

- [x] R1–R3 API·브라우저 회귀 테스트 및 R4–R5 계약·loop·MCP 통합 테스트 통과.
- [x] Python 정적 검사·UI 타입 검사/빌드·일반 테스트 30개 통과. 최신 wheel을 독립 환경에 설치해 단독 실행 재검증.
- [x] 실제 GPT 테스트 2개 통과와 결정적 테스트의 결과를 구분하여 docs/IMPLEMENTATION_REPORT.md에 기록.
- [x] 대화 연속성·후속 방책 선택·선택 표시·도구 호출의 Review 절차를 보고서에 제공. 다음 Review는 사용자가 수행.

## 최초 Implement 계획 및 결과

1. Python/프론트엔드 workspace와 검증 환경을 구성한다.
2. FR-01/02/03/09: 객체 계약·지리 이동·필터/집계·snapshot/이벤트 저장의 실패 테스트를 먼저 작성하고 Mock C4I API를 구현한다.
3. FR-04/06/07: 실제 HTTP MCP 연결 테스트와 단일 native Agent loop 테스트를 먼저 작성하고 MCP·하네스를 구현한다.
4. FR-03/05/06/08: 수집·중복 방지·자동 분석·대화·방책 선택 테스트 후 Platform API를 구현한다.
5. 지도·적아/유형 심벌·C4I 조작·질의/이력·세 방책 비교 UI를 구현하고 Python E2E로 검증한다.
6. Python 검사·프론트엔드 빌드·독립 C4I 배포물 검증을 수행하고 실행 방법과 Review 자료를 제공한다.

각 기능은 테스트 작성 → 실패 확인 → 구현 → 통과 순서로 진행한다. 구현 중 선택한 값은 이 문서와 검증 보고서에 남기며 사용자 Review 완료 전 Reflect를 수행하지 않는다.

초기 구현값: Python 3.12, 서비스별 단일 worker, 전체 실행 동시성 1, 원천 tick 1초, 상태 변경만 자동 분석, Agent loop 12회/Tool 20회/120초, 최근 완료 대화 6턴. 원천 소속·유형·가용성은 명세 값을 따른다.

실제 OpenAI 검증은 사용자의 로컬 OPENAI_API_KEY·OPENAI_MODEL 설정이 필요하다. 키가 없을 때 사전 작성한 답변을 실제 Agent 결과로 표시하지 않는다. 자동 테스트에서는 주입한 모델 어댑터를 사용한다.

## 진행 결과

- [x] 1–6 단계의 코드 구현·자동 테스트·UI 빌드·독립 C4I 배포 검증
- [x] TDD 실패/통과, 실제 MCP·브라우저 검증, 실행 README와 검증 보고서 작성
- [x] 실제 GPT 최종 검증: 수정된 로컬 모델로 native tool calling·실제 MCP 집계·적 탱크 3대 근거·세 방책 생성 확인 (2026-10-15)
- [x] 사용자 Review: docs/REVIEW.md의 2026-10-15 피드백 수신
- [x] 최초 Review 후 Reflect: 위 R1–R5 후속 계획으로 반영. 이후 후속 구현·검증 완료, 다음 사용자 Review 대기
