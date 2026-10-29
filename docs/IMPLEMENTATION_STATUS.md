# IMPLEMENTATION_STATUS

## 현재 상태

2026-10-28 세 체계 군수 Mock·Agent 독립 객체 상세·A/B/C 별도 진입의 구현과 관련 검증을 완료해 **Human Review 대기**다. 주장 분류·문서 규칙 인용 오류 수정에 이어 업무 UI·공통 표시 메타데이터·의미 관측 보기·반복 평가 도구의 구현과 무과금 검증을 완료했다. 이번 실제 모델 측정은 사용자 지시로 제외했다. 현재 기본은 c2-logistics-demo-v5, source/ontology/adapter5.0.0, 정책5-logistics-abc다. v4/v3 구현·실측은 각 버전의 이력으로 보존한다. 후속 사용자 허용으로 v5 GPT 사전 평가9 runs를 수행했다. 본 반복 측정과 일반적인 우열·일관성 검증은 미완료다. 이어서 사전 평가 REVIEW의 Semantic 조회 범위·run 내 근거 재사용을 구현하고 무과금 검증을 완료했다. 2026-10-29 지식베이스 효용 시연(v6 선언적 온톨로지·업무 질의·Fabric 정의 발행·근거 추적·v6 평가 도구)을 구현하고 무과금 검증을 마쳐 Human Review 대기다. dev.py 기본은 v6 지식 계층이다. [ARCHITECTURE](ARCHITECTURE.md)는 구조/실행, [PLAN](IMPLEMENTATION_PLAN.md)은 다음 유효 작업이며 이 문서는 실제 결과·제약만 관리한다.

## 지식베이스 효용 시연(v6) — 2026-10-29

발표 메시지("같은 지식이라도 지식베이스로 구조화하면, 더 일관되고, 추적 가능하고, 바꾸기 쉬운 답을 얻는다")를 위한 PLAN M1·M2a·M2b·M3을 사용자 지시로 한 번에 구현했다. 유료 모델 평가는 실행하지 않았으며 ①의 실제 효과는 미측정이다.

구현:

- M1: 선언 `ontology_v6.json`(규칙13·업무 질의3·편집 항목1)과 `declaration.py`(검증·렌더링·편집·diff·영향). 선언을 Fabric 문서 ONTOLOGY-01로 담은 v6 기본 지식 집합 `knowledge-52b73da405a6e1cd0a83f8bb`(v5 문서11+1). `build_domain`이 선언 규칙·OntologyDeclaration·BusinessQuery·APPLIES_RULE을 컴파일하고 v6 `interpret_concept`가 선언 용어를 읽는다. 업무 질의 3종을 Semantic API/MCP로 제공하고 C만 허용한다. 정책 라벨을 `comparison_policy()`로 통일했다.
- M2a: 진입 카드 B/C 문구, 주장별 근거 추적 체인(업무 질의→선언·규칙→그래프 간선→원천 기록), Fabric 딥링크(`?graphVersion=&node=`).
- M2b: Fabric "온톨로지 정의 · 검토 · 발행" 화면과 drafts/approve API, 로컬 store(`FABRIC_KNOWLEDGE_STORE`), 발행 이력, 발행 직후 새 Graph 백그라운드 준비.
- M3: v6 fixture(K1~K9, 그룹·hold-out·expectedQueries·변경 gold), 자동 판정·반복 일관성·추적 완결성·업무 질의 선택 정확도·새 정의 준수율 지표, `evaluate_knowledge.py --ontology-profile 6 --variant-knowledge-set`. 스크립트 정책 라벨을 인자로 정하고 플랫폼 정책과 다르면 중단한다.
- 0절: 기존 실패 `test_graph_sync`의 대체 build를 `ensure_build(body, knowledge)` 계약에 맞춰 통과시켰다.
- 부수 수정: Fabric catalog가 계약5에서 `c2-domain-demo-v3`로 표시되던 기존 버그를 `c2-logistics-demo-v5`로 고쳤다. 추적 링크 대비를 높였다.

확인된 효과(무과금, 결정론적): 업무 질의 결과에 구조화 ruleId가 실려, 이를 인용한 주장의 규칙 근거가 검증되고 답변이 partial로 강등되지 않는다(사용자 예시의 "부분 결과"는 `provenance.py`가 미확인 규칙 경고 시 outcome을 partial로 바꾸던 동작이었다). 기본 가용 기준을 P1→P2로 발행하면 같은 질문의 C 업무 질의 결과가 가용 전차 1→2대로, B의 ONTOLOGY-01 본문이 P1→P2로 함께 바뀌고, 이전 Graph·이전 문서 버전은 1대/P1을 유지했다. 영향 분석은 AGGREGATION-POLICY-01→asset-availability-summary→C 가용 현황 답변으로 계산됐다.

| 이번 실행의 검증 | 실제 결과 |
| --- | --- |
| 신규 단위/API 테스트(선언 8, 업무 질의 9, API 3, 평가 지표 6) | 실패 확인 후 통과 |
| 전체 무과금 비UI·비Neo4j 회귀 | 214 passed, 58 deselected / 372.83초 |
| 실제 Neo4j 통합(UI·live 제외, v6 통합·graph_sync 포함) | 18 passed / 597.09초 |
| v6 브라우저 시연 흐름(실제 세 원천·Neo4j·MCP, 결정론적 provider) | 통과 1회 / 292.91초. 근거 추적·Fabric 딥링크·편집·영향 분석·승인·발행·모바일 390px·발행 후 새 대화 2대 확인 |
| 이후 수정(평가 스크립트 정책 검사·v6 dry-run) 재검증 | 관련 단위 13 passed; v6 통합(dry-run 27 planned/0 executed 포함)+v5 MCP 통합 2 passed / 146.87초 |
| 정적 UI 회귀(브라우저, Neo4j 제외) | 29 passed, 243 deselected / 152.44초 |
| 정적 검사 | Ruff check/format, mypy 89 source files, TypeScript, 프론트 빌드·정적 패키징 통과 |

캡처: `artifacts/ontology-v6/`의 c-trace, fabric-deeplink, fabric-impact, fabric-published, fabric-mobile, c-trace-after-publish.

계획과 달라진 점: 새 원천 dataset 대신 v5 원천을 재사용했다(원천 변경 위험 회피, 기존 함정 자산 사용). 업무 질의 후보 중 보고 계보·절차 진행은 구현하지 않았고 미포함 그룹(K7·K8)으로 평가한다. contract6 대신 계약5 원천 + 지식 profile 6으로 분리했다. 의존 규칙에 FORCE-SCOPE-01→ORG-ROLE-01, AGGREGATION-POLICY-01→FORCE-SCOPE-01, REPORT-REVISION-01→REPORT-LINEAGE-01을 선언에 추가했다.

제약·미검증:

- 실제 모델의 일관성·정답률·비용 효과는 미측정이다. 업무 질의가 있다고 Agent가 이를 선택한다는 보장은 없다.
- 브라우저 흐름 테스트 5회 중 3회는 첫 C 질문의 업무 질의 호출이 60초 넘게 끝나지 않아 실패했고, 원인은 확인하지 못했다(같은 경로의 직접 MCP 호출 통합 테스트는 매번 통과). 발표 전에는 서버 기동 후 C 화면에서 질문을 한 번 실행해 예열하고, 발행 직후에는 새 Graph 준비가 끝난 뒤 새 대화로 질문할 것을 권한다.
- 자동 판정은 정규식 기반 참고값이며 한국어 서술 변형에 따라 오판할 수 있다.
- 업무 질의 연산자 종류는 코드이며 선언으로 새 연산자를 만들 수 없다. 편집 가능 항목은 1개다.
- Fabric 승인은 데모 capability이며 로컬 store의 동시 발행 직렬화·인증·발행 취소는 없다. 진행 중인 대화는 시작 시 버전을 유지한다.
- 규모 효과는 다루지 않는다. Neo4j는 버전 고정 저장소로만 쓰인다.

## Semantic 조회 범위·run 내 근거 재사용 — 2026-10-28

사용자 REVIEW의 C 모드 도구 비효율을 반영한 구현과 무과금 검증을 완료했다. 구현은 Codex 세션에서 시작해 사용량 한도로 중단된 뒤 이어서 완료했다. 이전 세션의 테스트 통과 기록은 사용하지 않고 아래 검사를 다시 실행했다. 실제 모델 전후 측정은 수행하지 않았다.

보존된 [9-run 결과](../artifacts/evaluation-pilot-20261028T065440Z/results.json)와 REVIEW 관찰을 대조한 결과:

- L2 C의 `interpret_concept("availability")`는 실제로 규칙12개(14,572자)를 반환했다.
- L2 C의 SOP-01 조회는 모델이 `documentId: null`을 보냈고 서버가 SOP-01을 기본으로 돌려준 경우였다.
- 보존된 C의 `query_relations`는 0건이 아니었다. M-17 기준11건, L-T02 조직 관계3건이었다. REVIEW의 L-T02 군수 관계0건은 이 artifact에서 재현되지 않았다. 다만 ATCIS 장비 key에서 `SAME_AS` 없이 군수 관계만 요청하면0건이 되는 경로를 테스트로 고정했다.
- 같은 run 안의 동일 인자 반복은 L3 A 한 run에만 있었다(`list_cargo`2회, `list_work_orders`3회). `list_supply_requests`의 run 내 중복은 없었다. 9 runs 합계는 `list_cargo`7회, `list_supply_requests`5회다.

변경:

- `interpret_concept`는 검토된 용어→시작 ruleId 표와 명시적 의존만 반환하고 `selectedRuleIds`·`supportedTerms`를 함께 준다. 미지원 용어는 `unresolved`이며 전체 조회는 명시적 `all`만 허용한다(v3 호환 테스트가 사용).
- `get_procedure_definition`은 documentId가 필수이고, 도구 설명에 사고 보고/활동 완료 SOP-01 전용이며 정비·복구 전망을 정의하지 않는다고 명시한다.
- 원천 MCP 응답은 run 범위에서 서버/도구/정규화 인자/sourceSnapshotSet 핀이 같을 때만 원래 evidenceId로 재사용하고 toolCalls에 cacheHit를 남긴다. 실패/partial은 재사용하지 않는다.
- 도구/반복 한도에 도달하면 마지막 모델 요청을 도구 없이 보내 확보한 근거로 답변하게 한다. 출력 교정이 이어져도 예산 종료 안내가 중복되지 않게 수정했다.
- A/B/C 공통 프롬프트에서 Fabric 문서 전용 `laborHours` 해석을 제거했다(프롬프트 digest 변경). v5 gold L3에서 질문에 없는 `컷오프 초과` 판정을 제거했다.
- 평가 metrics에 중복 호출 수·중복률·cacheHit 수를 추가했다.

보존 run 호출을 현재 코드로 재생한 정적 비교(모델 재실행 아님):

| 항목 | 이전 기록 | 현재 코드 |
| --- | --- | --- |
| `interpret_concept("availability")` | 규칙12개 /14,572자 | 3개(AVAIL-LAND-01·AVAIL-NAVAL-01·AGGREGATION-POLICY-01) /4,244자 |
| L3 C `query_relations` 2건 | 11건·3건 | 같은 간선 집합 11건·3건 |
| L3 A 원천 요청 | 12회 | 캐시 적용 시 실제 원천 요청9회. 모델의 도구 호출 수와 예산 소모는 같음 |

| 이번 실행의 검증 | 실제 결과 |
| --- | --- |
| 신규 효율 테스트(규칙 선택·미지원 용어·SAME_AS 경로·핀 캐시 적중/미적중·최종 답변 턴·안내 1회·프롬프트·L3 gold·절차 도구 설명) | 8 passed. 중단 전 세션의 선행 실패 기록은 재확인하지 않았고, 예산 안내 중복은 이번 세션에서 실패(2회)를 확인한 뒤 수정 |
| 전체 무과금 비UI·비Neo4j 회귀 | 188 passed,56 deselected /233.18초 |
| 실제 Neo4j 통합(UI·live 제외) | 16 passed,1 failed /469.43초 |
| 정적 검사 | Ruff check/format(148파일), mypy84 source files 통과 |

Neo4j 실패 `test_graph_sync.py::test_builder_queues_and_restart_recovery_are_scoped_to_source_endpoints`는 단독 재실행에서도 같다. 테스트의 대체 `build(refs)`가 인자1개인데 worker가 `ensure_build(body, knowledge)`로 2개를 넘겨 요청이 FAILED가 된다. graph-builder와 해당 테스트는 이번 작업에서 수정하지 않았으며 이전 지식 집합 도입 이후의 기존 불일치로 판단한다. 이번 범위 밖이라 수정하지 않았다.

제약: 실제 모델의 호출 수·토큰·응답 시간·정답률의 전후 개선은 미측정이다. 캐시는 원천 요청만 줄이며 모델이 같은 도구를 반복 선택하는 것 자체는 막지 않는다. 용어 표에 없는 개념은 `unresolved`가 되므로 C가 오히려 조회에 실패할 수 있다. 프롬프트·gold 변경으로 이전 9-run과 이후 측정은 같은 기준의 반복 비교가 아니다. UI·live 테스트는 실행하지 않았다.

## 실제 GPT 사전 평가 — 2026-10-28

사용자가 유료 모델 실행을 명시적으로 허용한 후 L0/L2/L3 × A/B/C ×1회, 총9 runs를 실행했다. 본 측정54 runs는 수행하지 않았다. 당시 실행 중인 최신 v5 서버를 사용했고 코드·prompt·예산·원천 데이터·지식 집합은 실행 도중 변경하지 않았다. STEP은 Human Review를 유지하며 REVIEW 원문/정답 fixture/기존 로그를 변경하지 않았다.

조건: 실제 응답 모델 gpt-6-luna, 세 원천 T1=2026-10-20 09:10 UTC, knowledge-30b1b2ab4f77148a1f1db9c2(11개 문서), C Graph domain-10b729c4d025e9d5e6349401이다. 첫 비교의 A→B→C, 다음 B→C→A, 마지막 C→A→B로 순서를 회전했다. 매 run은 격리된 빈 대화와 동일 snapshot pins를 사용했다. 각 run은24 iterations/20 tools/120초, batch 최대9 runs/216 모델 응답/관측 토큰 중단 기준2,000,000이었다. 토큰 기준은 비교 사이에서 검사하며 진행 중인 비교의 하드 비용 한도가 아니다.

원천의 모든 records와 기준 시각이 독립 fixture와 일치하는 것을 유료 호출 전에 확인했다. 실행 후에도 records/snapshotId/sourceTime이 변하지 않았다.9개 모두 usage complete·같은 pins/지식 경계 검사를 통과했고, A/B의 Semantic 호출은0이었다. 실제 인용한 evidenceId는 모두 해당 run 안에 존재했다. 이는 문장 전체의 논리적 지지가 자동 증명됐다는 뜻은 아니다. 검증 실패·교정은 모두0이었으며, 원래 사용자가 제시한 과거 실패 run을 재작성하지 않았다.

| 질의 | A 원천 | B 문서 | C 구조화 |
| --- | --- | --- | --- |
| L0 재고/예약 | 핵심 gold 충족,13.30초/2 tools | 핵심 gold 충족,11.20초/2 tools | 핵심 gold 충족,10.45초/2 tools |
| L2 복구 전망 | 핵심 gold 충족,58.25초/11 tools | 핵심 gold 충족,66.80초/16 tools | 최종 답변 없음,73.99초/20 tools, budget_exceeded |
| L3 수송 지연 영향 | 부분 충족,68.11초/12 tools | 부분 충족,45.67초/11 tools | 부분 충족,84.28초/17 tools |

시간은 첫 모델 요청부터 loop 종료까지이며, 큐 대기/기준 준비가 포함된 전체 요청 시간과 구분한다. 판정은 assistant의 독립 gold 대조에 따른 잠정 분석이며 Human Review 완료가 아니다. 실패를 포함한9개 분모에서 핵심 gold 충족5개, 부분 충족3개, 최종 답변 없음1개다. 답변 완료는8/9이며 완료율을 정답률로 부르지 않는다.

| 조건(각3 runs, 실패 포함) | 입력/출력 토큰 합계 | 모델 응답 | 도구 호출 | 평균 loop 시간 |
| --- | --- | --- | --- | --- |
| A | 194,221 /8,219 | 28 | 25 | 46.55초 |
| B | 243,079 /6,559 | 32 | 29 | 41.22초 |
| C | 582,246 /7,089 | 42 | 39 | 56.24초 |

총 입력1,019,546·출력21,867·합계1,041,413 tokens, 모델 응답102회·도구93회다. 입력 중 cached939,247, 출력 중 reasoning8,862이며 각각 입력/출력에 포함된 하위 수치이므로 중복 합산하지 않는다. 금액은 계산하지 않았다. 입력 토큰 합계에는 캐시/누적 문맥이 포함되며 곧바로 비용 금액으로 해석할 수 없다.

관찰과 반례:

- L0는 세 조건 모두 원천 inventory/reservations만2회 읽고 WH-1 보유2/예약1 EA를 정확히 답했다. 단순 조회에서 추가 지식을 사용하지 않았다.
- L2에서 A도 명시적 원천 참조와 자체 해석으로 올바른15시 조건부 전망을 냈다. B는 LOG-01/DISPLAY-01을 읽고 같은 결과를 냈다. C는 원천/문서 조회에 Semantic8회를 추가했고 도구 한도를 소진했다. get_procedure_definition 등 우회 탐색과 개별 identity 조회가 늘었다. 답변 실패를 숨기거나 C만 예산을 늘려 재측정하지 않았다.
- L3는 세 조건 모두 C111/모의111중대·L-T02/EQ-781·M-17의 직접 영향 연결과 가정 분석을 답했다. A/C는 인도17시를 제시했으나 세 조건 모두 인도 후4h의21시 조건부 복구 전망을 제시하지 않았다. A의 ‘미예약1개 배정으로 지연을 피할 가능성’은 필요2개 중 미예약1+입고1이라는 수량 구조로 충분히 뒷받침되지 않는다. B는 이 질의에서 Knowledge/KNCCS 도구를 호출하지 않아 문서/예정 인도 시각을 읽지 않았다. C는 검증된 동일성/관계 근거를 실제로 인용했지만 경과 시간 규칙 적용까지 이어지지 않았다.
- 독립 L3 질문에는18시 cutoff가 없지만 gold에는 컷오프 초과가 포함되어 있다. 해당 누락만으로 오답 처리하지 않았고 질문/gold의 한계로 따로 기록했다. 이번 실행 중 gold나 질문을 고치지 않았다.

이번 작은 사전 평가에서는 C 우위가 입증되지 않았다. 현재 C tool loop가 추가 의미 조회 비용을 제어하지 못하는 반례가 확인됐다. 이는 일반적인 온톨로지 무효를 뜻하지 않는다.1회씩이라 반복 일관성·통계적 우열은 평가하지 못하며 단순 대조군도1개다. B/C의 지식 접근 권한과 실제 지식 사용은 다르고, 준비/캐시/순서 효과도 포함된다. 다음 구현이나54 runs 확대는 별도 사용자 지시 범위로 남긴다.

원본과 파생 artifact는 [평가 batch](../artifacts/evaluation-pilot-20261028T065440Z/results.json), [고정 manifest](../artifacts/evaluation-pilot-20261028T065440Z/manifest.json), [잠정 분석](../artifacts/evaluation-pilot-20261028T065440Z/assistant-assessment.json), [CSV](../artifacts/evaluation-pilot-20261028T065440Z/summary.csv)에 보존했다. 같은 경로에 사전 rubric·원천 snapshots·코드/정답 hash·오프라인 metrics·미작성 Human Review 양식·실행 전후 검사가 있다. 별도 Markdown 보고서는 만들지 않았다.

## 업무 UI·공통 의미 메타데이터·관측 연결·평가 도구 — 2026-10-28

최신 REVIEW를 반영한 구현과 무과금 검증을 완료했다. 사용자가 유료 사전 점검 대신 구현·무과금 검증까지만 선택했으므로 실제 모델9/54 runs는 실행하지 않았다. v5 모델 정확도·일관성·성능 우위는 미측정이다.

- C 객체 상세는 현재 원천 상태·소속·제약, 작업별 정비/필요 부품, 창고 재고/예약, 관련 수송, 기록별 기준·갱신·수신/이번 조회 완료 시각을 우선 표시한다. Graph/식별자/메타데이터·수집 진단/원본은 접힌 상세다. LLM을 추가 호출하지 않는다. laborHours는 기존 경과 시간(h)이며 인시로 바꾸지 않았다.
- Fabric DISPLAY-01을 B/C 공통11개 지식 집합에 추가했다. 현재 knowledge-30b1b2ab4f77148a1f1db9c2, DISPLAY-01 v1.1/review-display-2다. 체계/필드·명칭/설명/aliases/단위·수량 성격·원천 schema5.0.0·적용 기간을 보존한다. C API/MCP/업무 view는 같은 버전/hash를 사용하고 B는 같은 문서를 읽는다. 미정의 코드는 미확인, 미지원 revision은 오류다. 이전10개와 초기 표시 문서 archive는 덮어쓰지 않았다.
- 원천 단독 화면과 원천 탐색의 한국어 표시는 로컬 UI 자산이다. A/B Agent 입력이나 공통 가용 판정으로 주입하지 않는다. Fabric 탐색 메뉴를 업무 명칭으로 표시하고 원본 결과는 펼쳐서 확인한다. Agent의 의미 중심 한국어 답변 지침을 보완했지만 실제 모델의 표현 개선을 측정하지는 않았다.
- 지상5/등록 함정2/접촉3의10개 관측 전달과 nativeStatus 보존을 확인했다. C의 명시적 의미 보기에서 검증된 자산별 연결 관측/근거와 관측·고유 자산·미확정 수를 구분한다. 위치가 다르면 모든 관측을 유지한다. 원천·의미 전환과 주기 갱신은 map 인스턴스를 재생성하거나 모델을 호출하지 않는다. A/B는 의미 API·MCP 접근을 차단한다.
- 평가 도구는 무과금 context/manifest, 반복/순서 회전, 전체 pins·지식/모델·예산 고정, 새 artifact 예약/checkpoint, 실제 usage의 중복 제거·coverage, 실패 분모, 서비스별 도구 호출과 검토 양식을 제공한다. loop 시작/종료·모델 응답 시간, 검증 실패/교정 횟수를 run에 저장한다. 미검토 정확도·근거 지지는 null/unreviewed이며 자동 정답 판정하지 않는다.

| 이번 실행의 검증 | 실제 결과 |
| --- | --- |
| 전체 무과금 비UI·비Neo4j 회귀 | 177 passed,52 deselected /318.39초. 이후 계측/메타데이터 변경은 아래 관련 검사로 재검증 |
| 최종 실제 정적 UI 회귀 | 29 passed,205 deselected /171.80초. 원천 단독·Fabric 탐색·상세/문서·지도/대화·키보드/IME·반응형 포함 |
| 실제 세 원천/MCP/Neo4j 상세·비교·UI | 2 passed /264.84초. 결정론적 provider, 실제 모델 비용 없음 |
| 최종 메타데이터1.1·MCP parity·A/B 차단·무과금 CLI manifest | 1 passed /76.36초. 실제 세 원천과 전용 Neo4j 사용,9 planned runs/0 executed runs 확인 |
| 고정 context의 실제 반복 비교 | 1 passed /213.04초. 테스트 원천 tick 후에도 두 비교의 A/B/C가 최초 pins/지식 버전을 재사용하고 loop 시간을 저장 |
| 실제 Fabric→Knowledge MCP→Agent 저장 | 1 passed /37.45초. 결정론적 provider, 계측 변경 후 경로 확인 |
| 최종 Agent·검증·로그·계측·메타데이터 회귀 | 35 passed /9.72초. 실패2회·교정1회 계측 포함. 앞선 Agent/지식 경계 검사44 passed,1 deselected /12.36초 |
| 빌드·계약·정적 검사 | 여섯 UI build/정적 패키징, Pydantic 계약 export, 최종 TypeScript, Ruff check/147파일 format, mypy84 source files 통과 |

캡처는 artifacts/business-ui/c-{너비}-{높이}.png다. 1440×900/1280×800/1024×768/640×900/390×844/1024×500에서 닫기 접근·패널 폭을 검사했고 데스크톱/모바일 이미지를 직접 확인했다. 모바일 도구 모음의 과도한 줄바꿈을 수정했다. 실제 세 체계 UI 캡처는 artifacts/logistics-v5-*를 갱신했다. 검사 중 메뉴명/원본 접기 변경에 따른 기존 selector와 중복 텍스트 selector를 수정한 뒤 재검증했다.

제약: 의미 지도는 자산별 관측 목록/배지·근거이며 검토된 대표 위치 정책이나 임의의 단일 마커 병합을 추가하지 않았다. token 중단은 ABC 사이의 관측 한도라 진행 중인 비교의 하드 비용 상한이 아니다. SDK transport 재시도의 과금까지 응답 수로 추정하지 않는다. 검토 양식은 사람이 채워야 하며 자동 채점된 정답률은 없다. 새 metadata revision의 의미·한국어 용어 검토는 Human Review에서 확인한다. Vite의 기존 큰 chunk 경고는 남는다. 테스트는 임시 원천 DB/포트와 전용 Neo4j17687의 test scope를 사용했고 사용자 서버/DB/Graph/volume을 초기화하지 않았다. REVIEW SHA256 3B0502E38FC29B32E1EB7F3D237B3E1723D9C0987E7153E250D7734715AF0686을 보존했다.

## 주장 분류·문서 규칙 인용 오류 수정 — 2026-10-28

사용자가 제공한 df3ad1410ef2428ea100977f30822a35 로그의 두 오류를 실패 테스트로 재현하고 수정했다. B의 semantic 표기와 문서 규칙 이름 때문에 결과 전체를 버리던 동작을 모델의 주장 종류와 서버의 출처 메타데이터로 분리했다. 새 A/B/C 스키마에는 semantic 종류를 요청하지 않으며 구형 표기는 reportedKind에 남기고 inference로 호환 처리한다. 실제 Semantic/Knowledge 접근 차단과 이번 run에 없는 evidenceId 거부는 유지한다.

문서 본문에 실제 있는 규칙 이름은 documentRuleRefs와 문서 version/hash로 표시한다. C의 구조화된 근거에서 확인한 ruleRefs와 구분한다. 확인 불가 규칙 표기는 한계 경고·partial 답변으로 보존하고 가짜 증명으로 승인하지 않는다. 모델이 서버 provenance를 직접 제출하는 것도 거부한다. 새 서버 계약은 provenanceVersion1이며 로그에는 claim_provenance로 분류·출처·확인/미확인 참조를 남긴다. 본문 진위나 논리적 지지는 이 검사로 평가하지 않는다.

검증: 신규 반례 포함 Agent·기존 지식 경계·로그 회귀46 passed,1 deselected /14.98초. 실제 정적 UI의 출처·문서 규칙 표시와 기존 지도/대화6 passed /33.46초. 캡처 `artifacts/claim-document-provenance.png` 직접 확인. 실제 Fabric→Knowledge MCP→Agent→저장 경로1 passed /40.06초로 B가 문서1회 조회와 최종 응답의2회 모델 호출(결정론적 provider)로 완료됨을 확인했다. 새 모델 스키마의 semantic 제외 assertion까지 포함한 최종 실제 재검증도1 passed /29.13초다. TypeScript·플랫폼 빌드/정적 패키징·mypy80 source files 통과. Ruff check·140파일 format 검사 통과. docs8개·로컬 문서 링크·변경 공백 검사를 확인했다. 작업 중 사용자가 갱신한 최신 REVIEW 원문은 AI가 수정하지 않고 보존했다.

유료 모델은 호출하지 않았다. 원래 실패 run/log/DB는 수정하지 않았으며 서버 재시작 후 새 실행에 적용된다. v3/legacy의 기존 엄격 검증과 과거 실측은 보존한다. 실제 모델 정답률이나 원래 질문의 재실행 성공을 측정했다고 주장하지 않는다. UI·계약·기술/결정 문서를 기존 파일에 정합화하고 REVIEW 원문은 유지했다.

## 세 체계 군수·독립 객체 상세·페이지 구분 — 2026-10-28

2026-10-27 Review 대화의 세 가지 방향을 구현했다. 군수 원천을 독립 Python/DB/UI/시뮬레이터와 읽기 MCP로 추가하고, Semantic의 명시적 연결을 Fabric 상세와 Agent가 재사용하며, A/B/C를 공통 화면의 별도 페이지로 시연한다. 기존 v4 데이터·Graph·fixture/gold·DB를 수정해 새 정답으로 바꾸지 않았다. 설명 문서는 Fabric 소유이며 v5의 B/C는 기존9개+LOG-01의 같은10개 집합을 고정한다.

| 요청 | 실제 구현 |
| --- | --- |
| 군수 Mock과 세 체계 질의 | :4120 원천·:4220 MCP, 자산/정비/부품/재고·예약/보급·화물, KNCCS 수송/인도. 원천마다 별도 SQL·snapshot·제어/읽기 토큰. 군수 정비 상태와 해군6시간 지연 제어 |
| 차량 클릭의 통합 정보·시점·연결 규칙 | C의 L-T02→EQ-781/M-17→P-08/재고→C-12→N-21. ObjectService가 모델 없이 조회하며 기준/변경/수신 시각·Graph/지식/adapter·원천 근거를 표시 |
| Semantic 책임 분리 | Graph는 명시적 동일성/업무 관계·기간·근거, Fabric은 공개 원천 조회/조합, 원천은 live 상태·재고·시각. 군수 현재 미해결 고장 값도 stable export에서 제거. Agent는 실제 원천 MCP를 유지하고 live Fabric 상세로 우회하지 않음 |
| A/B/C 별도 페이지 | `/demo/a`, `/demo/b`, `/demo/c`, `/demo/compare`. composer 전환 제거·조건 고정. 대화/이력/저장·상세/문서·늦은 요청 분리. 세 조건 모두 원천과 원천에 실제 있는 매핑을 읽음 |
| 서버 경계 | opaque demo context의 mode/policy/dataset·만료를 검사. A/B의 직접 구조화 API/간접 helper·모드 변조/다른 대화·run/비교·SSE 우회 차단. 내부 Fabric 토큰은 브라우저에 전달하지 않음 |
| 공정 비교와 호환 | 세 원천 snapshot·동일 질문/기준보고·B/C 지식 hash·C Graph 고정. 새 dataset/DB/policy/독립 fixture·L0~L5 gold. v4/v3 명시적 실행 경로 유지 |

선행 실패와 수정: 군수 모듈/Graph·객체 서비스·별도 진입 부재를 확인하고 구현했다. 실제 통합에서 두 원천으로 제한된 공통 runner와 Builder snapshot 타입을 발견해 v5 계약을 확장했다. 선택 상세가 상태 변경 후 이전 레코드를 보이는 오류, 현재 미해결 고장이 stable Graph에 포함되는 오류도 실패 테스트로 재현해 수정했다. 수송/정비/부품 ID는 이름 추측 없이 명시적 sourceRef에서 graph key를 얻도록 resolver를 확장했다. 브라우저 검사 중 중복 accessible label과 테스트 들여쓰기 오류는 선택자를 role로 지정하고 수정한 후 통과했다.

| 이번 실행 검증 | 결과 |
| --- | --- |
| 최종 계약·독립 wheel·원천/MCP/launcher·기존 v4 경계·지도/채팅·원천/Fabric UI | **47 passed,2 deselected /73.46초**. `test_logistics_v5`, `test_logistics_ui`, `test_workspace_ui`, `test_domain_ui`, `test_knowledge_v4`, `test_domain_sources`, `test_domain_mcp`, `test_dev`, marker not neo4j |
| Fabric Graph 버전/탐색 UI 회귀 | **5 passed /13.64초**. 군수 관계 필터/프리셋 추가 후 기존 탐색 경로 확인 |
| 실제 v5 세 원천·MCP·Neo4j·UI | **1 passed /206.92초**. 공통 pins/hash·비교, C 상세/문서, 모바일 비교 확대·A 원천 탐색, 군수 단독 UI. 결정론적 provider, 실제 GPT 호출 없음 |
| 실제 v5 A/B 서비스 부재 | 초기 통합 실행의 두 parametrized case 모두 통과. Semantic MCP URL을 실제 없는 endpoint로 지정하고 Neo4j/Builder 없이 실행. A는 Knowledge MCP도 없는 상태에서 실행. 같은 실행의 뒤이은 UI selector 실패는 위 최종 v5 실제 검사에서 수정/재검증 |
| 실제 v4 MCP·Neo4j·비교·Fabric 호환 | **1 passed,2 deselected /84.92초**. v5와 다른 기존 입력/정책의 실제 경로 |
| 실제 수송 의미 조회 MCP | **1 passed,3 deselected /41.50초**. 모델 없이 N-21 canonical ID와 CARRIED_BY/FULFILLED_BY 의존 경로를 실제 MCP→Semantic API→Neo4j에서 확인 |
| 최종 수송 resolver·v5/v4 지식 경계 | **20 passed,1 deselected /7.62초**. 명시적 N-21 graph key, 군수 자산/시점·충돌/미연결·오래된 Graph·부분 단절, 원천/문서/Graph 경계 |
| 군수 단독 상태 제어 UI | **2 passed /7.05초**(v5 진입 포함). 선택 상세가 새 snapshot의 DONE을 표시 |
| 정적·배포 | Ruff check·136파일 format, mypy79 source files, 계약 export·TypeScript, 전체6개 UI production build·최종 플랫폼/군수/Fabric 재빌드·정적 패키징 통과. MapLibre 포함 chunk 크기 경고는 남음 |

캡처를 직접 확인했다: `artifacts/logistics-v5-c-desktop.png`, `logistics-v5-c-mobile.png`(고정 근거 문서), `logistics-v5-a-mobile.png`, `logistics-v5-comparison-mobile.png`. 실제 배경 지도와10개 원천 표시 객체, C 상세·근거 문서 본문 우선 배치·모바일 별도 원천 조회/비교를 확인했다. 같은 viewport의 지도/채팅 shell과 v4 상태 복원 회귀도 통과했다. docs는8개만 유지하고 REVIEW 원문은 보존한다.

한계: 이 구현은 합성 PoC다. opaque context는 데모 조건 분리이며 운영 인증/역할 권한이 아니다. 사용자는 명시적으로 C/비교에 들어갈 수 있다. 최초 C 상세는 세 원천과 Graph 준비가 필요하고 실패 시 오류를 보존한다. 이후 기존 Graph의 부분 조회와 기준 불일치를 구분한다. 깊이/개수 상한과 일부 수집 실패는 partial로 표시한다. L0~L5의 자연어 정답률·지연/usage 우열은 실제 GPT로 측정하지 않았다. 복구 전망은 원천/문서에 근거한 조건부 분석이며 현재 운용 상태를 변경하지 않는다. 실기기 키보드/접근성 전체 감사는 미검증이다.

실측 도구는 `scripts/evaluate_knowledge.py --contract-version 5 --live --output <새 경로>`이며 L0~L5를 선택할 수 있다. --live 없이 모델을 실행하지 않고 기존 결과를 덮어쓰지 않는다. 이번에는 비용을 쓰는 효과 측정을 실행하지 않았다. PRD/ARCHITECTURE/UI_GUIDE/ADR·README·환경 예제는 구현과 정합화했다.

## 지도·AI 채팅 통합 화면 — 2026-10-27

REVIEW의 ‘상황판과 챗 UI를 함께’는 상시 MapLibre 지도+대화 타임라인+고정 composer로 반영했다. ‘GOTHAM/LATTICE·ChatGPT 참고’는 지도 중심의 원천/객체 계층과 이어지는 질문/응답·이력·비교 동작, 기존 차콜 토큰으로 반영했다. 실제 브랜드 자산은 사용하지 않았다. `KnowledgeApp.tsx`/CSS 범위이며 backend·MCP·A/B/C 지식/정책 경계는 변경하지 않았다.

- 같은 conversation의 전체 질문/응답, A/B/C 모드 격리·새 대화, F1~F7/R0 옵션과 비교를 제공한다. IME 조합 중 Enter와 중복 전송을 막고 실패 시 초안을 보존한다. 지연 응답이 사용자의 새 모드/초안을 덮어쓰지 않는다.
- 지도 인스턴스·camera·선택 객체를 대화·이력·비교 중 유지한다. sessionStorage에는 UI 식별자·camera/선택·스크롤만 저장한다. 대화/비교 본문은 전용 서버 API에서 복원하고 capped 목록 밖의 비교 run도 추가 조회한다. 삭제된 비교는 안내 후 정리한다.
- 읽는 위치 자동 이동을 막고 새 내용 복귀 버튼을 제공한다. 원천 단절/갱신 실패와 지도 타일 장애를 구분한다. 비교는 채팅 탭·확대 dialog(데스크톱 세 열)로 읽고 닫으면 기존 지도를 유지한다. 원천 객체 선택은 Agent에 자동 전달하지 않는다.
- 1024px 이상 지도와 우측360~460px 채팅, 미만은 지도 상단/채팅 하단이다. 가용 높이가 줄면 지도를 축소한다. UI_GUIDE·PRD·ARCHITECTURE·ADR와 README 사용법을 실제 동작에 맞췄다.

선행 실패: 기존 UI에서 지도 region 부재를 확인했고, 추가 반례로 삭제된 비교의 무한 로딩과390×430에서 composer 하단 가림을 재현한 뒤 수정했다. 최종 정적 빌드를 패키징하고 실제 Chromium으로 확인했다. TypeScript lint·플랫폼 production build·변경 테스트 Ruff 검사 통과. 빌드의500kB chunk 경고는 남으며 새 오류는 아니다.

실제 서비스 검증은 `tests/test_knowledge_integration.py`의 기본2 passed(122.60초)와 `-m neo4j` 1 passed(139.04초)다. 실제 HTTP→MCP·Neo4j에서 A/B/C 공통 snapshot·지식 provenance, 비교 재열람/확대/지도 인스턴스 유지·모바일 C 탭·Fabric 고정 문서 이동을 확인했다. 지식 경계 회귀 `tests/test_knowledge_v4.py`는12 passed,1 deselected다. 결정론적 provider를 사용했고 유료 모델 호출·도메인 정답률 측정을 수행하지 않았다.

최종 `uv run pytest tests/test_workspace_ui.py tests/test_domain_ui.py -m ui -q`는 **10 passed(158.74초)**다. mock API+실제 MapLibre canvas로1440×900/1280×800/1024×768/640×900/390×844/390×430의 지도·composer 동시 가시성, 후속 대화/모드 격리, IME·중복·503·늦은 응답, 긴 답변의 스크롤 유지, 지도 camera/객체·새로고침 복원을 확인했다. 별도 실제 서비스 fixture로 육군/해군 업무 기록·Fabric 독립 화면·v3 OFF/ON 비교·모바일 탭·해군 참조 탭 회귀를 통과했다. 첫 실행에서 기존 Fabric ‘Graph 없음’ 검사가 로컬 `.env`의 활성 Neo4j에 의존해 실패해, 이 테스트만 `NEO4J_PASSWORD=""`로 격리한 뒤 재검증했다. 제품 Graph/데이터는 변경하지 않았다. docs8개·REVIEW SHA256 불변과 변경 파일 공백 검사를 확인했다(REVIEW 원문에 있던 Markdown 줄바꿈 공백은 보존).

캡처를 직접 확인했다: `artifacts/knowledge-platform-v4.png`(실제 원천10객체·배경 지도), `knowledge-comparison-expanded-v4.png`(실제 비교), `battlefield-chat-desktop.png`/`battlefield-chat-mobile.png`(mock 응답·타일 장애), `battlefield-chat-long.png`(긴 답변/선택 객체), `battlefield-chat-source-error.png`(원천 갱신 실패). 정상 지도 외부 타일 표시와 강제 타일 차단 fallback을 구분해 확인했다. 실제 모바일 OS 키보드/실기기, 접근성 전체 대비 감사, 유료 GPT 응답 품질은 미검증이다. 디자인의 최종 가독성/밀도는 Human Review 대상이다.

## 구현 범위

- 독립 육군/해군/군수 native UI·API·SQL·시뮬레이터. 공유 runtime은 ledger/auth/snapshot/event 등 기계 기능이다.
- 원천 MCP3(ATCIS7/KNCCS10/LOGISTICS8도구), Fabric 지식 catalog/API·독립 Knowledge MCP3도구·projection/분석 context, Neo4j Builder, Semantic MCP7도구. 공개 API·실제 MCP 경계를 유지한다.
- 검토 문서 hash/version·adapter·규칙 분리, 명시적 association ER, 안정 Graph와 live 상태 소유권 분리.
- 단일 native tool loop, A 원천/B 문서/C 구조화 지식 경계, C 현재-run 근거 평가·집계·유형×상태 계산, 기준보고/T0·B/C 지식 집합 고정과 비교 대화 격리. v3 문서 허용 OFF/ON은 호환 정책이다.
- v5 L0~L5·별도 조건 진입·구조화 객체 상세, v4 F1~F7 호환·주장/근거·계산 표·비교 조건·방책 선택. 제품5개와 legacy의 정적 UI6개.
- 실행별 UTF-8 파일 로그와 핵심 경계 주석. 로그는 기본 var/logs/agent/<runId>.log이며 전체 근거는 DB/UI trace가 기준이다.

## Fabric 지식 분리·A/B/C 비교 — 2026-10-27

2026-10-26 합의한 계획의 구현을 이어 완료했다. 원천의 업무 보고·전문·활동·조직/식별 관계는 유지하고, v4의 설명 문서 API/MCP/DB/UI 자원을 제거했다. 원래8개 설명 문서는 본문/version/hash를 보존해 Fabric으로 이관했고, C의 기본값·기간·unknown·집계·완료 조건을 B도 읽을 수 있도록 `fabric:POLICY-01`을 보완해 총9개를 관리한다. 새 v4 seed/독립 fixture/gold·전용 DB 경로를 사용하며 v3 파일·이력·Graph·실측 artifact는 원래 의미로 보존한다.

Knowledge catalog는 현재/불변 archive 집합과 문서 hash를 검증한다. 읽기 API와 별도 :4430 Knowledge MCP의 목록/검색/본문 도구를 구현했다. 검색은 literal text이며 Graph/임베딩/LLM 요약을 호출하지 않는다. A는 Knowledge/Graph 클라이언트가 없고 B는 Graph 없이 실행된다. C는 같은 문서 집합을 원천 stable hash와 함께 고정한 READY Graph를 사용한다. Builder는 실제 공개 지식 API에서 manifest와 본문을 읽고 검증한다. Graph provenance의 문서 참조는 Fabric key/집합 버전으로 연결된다.

플랫폼은 `knowledgeMode=native/documents/structured` 개별 실행과 공통 manifest의 세 run 비교를 제공한다. 모드별 대화·도구·근거·계산 helper를 격리하고, C 준비 실패는 C의 실패로 보존하며 A/B를 버리지 않는다. v4에서 모호한 legacy semanticMode 요청은 거부한다. 기존 정책의 run이 있는 DB는 읽기 검사에서 거부하고 별도 v4 DB를 요구한다. 같은 문서 대화는 원래 지식 버전을 유지한다.

UI에는 F1~F7, A/B/C 선택·개별 실행·같은 기준 비교·실행/비교 이력·공통 조건 상세를 추가했다. 세 열/모바일 탭·원천 지도·기존 결과/방책/근거 패널을 유지하고, Fabric의 지식 문서 본문과 Graph의 버전 고정 문서 이동을 연결했다. 기본은 v4이며 `--contract-version 3`으로 기존 정책을 실행한다. A/B는 `--profile off`에서 Knowledge MCP와 함께 Neo4j 없이 사용할 수 있다.

| 이번 검증 | 결과 |
| --- | --- |
| 선행 실패와 수정 | 새 API 부재/원천 문서 잔존, A/B 우회 호출, 이벤트 캡처의 타 체계 누락, 단독 CLI의 legacy DB 재사용을 테스트로 확인 후 수정 |
| 관련 원천·의미·MCP·Agent·평가·Fabric·실행·로그 회귀 | 54 passed, 1 deselected /23.38초. 실제 원천 MCP 경로와 기존 v3 호환 포함 |
| 최종 지식/Graph·호환 검사 | `test_knowledge_v4.py`와 `test_graph_explorer*.py`: 26 passed /30.17초. 실제 Neo4j, 인증/버전/본문 hash·문서 참조, A/B helper 금지, C 실패 보존, DB 보호·이벤트 snapshot 병합, v3 탐색 포함 |
| 최종 실제 스택/UI | `test_knowledge_integration.py`: 3 passed /241.17초. A/B의 실제 MCP·Neo4j 없는 실행, A/B/C 공통 pins·지식 hash·세 대화·Semantic MCP, 데스크톱 세 열/모바일 탭·Graph→고정 Fabric 본문 이동 |
| UI 지연 응답 회귀 | catalog 응답이 늦게 도착해 Graph 탭을 문서 탭으로 되돌리는 문제를 수정. 별도 재현 검사 1 passed /3.19초 후 최종26개 검사에 포함 |
| 정적/빌드 | Ruff check 통과, format125파일 통과, mypy72 source files 통과, 계약 export 실행, TypeScript와 전체 UI build·최종 Fabric/플랫폼 재빌드·정적 패키징 통과 |
| 시각 확인 | `artifacts/knowledge-platform-v4.png`, `knowledge-comparison-v4.png`, `knowledge-fabric-v4-mobile.png`의 실제 테스트 UI 캡처 확인 |

검증 도중 실제 서비스 준비+실행보다 짧았던 테스트 대기(단일20초)를 120초 Agent 예산과 별도 준비 시간을 허용하도록 조정했다. 세 run은 순차 실행하므로 별도 비교 대기 범위를 둔다. 브라우저는 외부 자원 전체 load 대신 DOM 준비 후 실제 컨트롤/결과를 검증한다. 운영 loop/도구/원천 동시 캡처의 기준을 완화한 것은 아니다. 최종 관련 검증은 모두 통과했으며 앞선 실패를 통과 기록으로 대체해 사용하지 않았다.

**측정 한계:** 통합 테스트의 provider는 기능 검증용 deterministic adapter다. 실제 GPT 호출·F1~F7 자연어 정확도·A↔B 지식 제공 효과·B↔C 구조화 효과는 이번에 측정하지 않았다. opt-in 평가 CLI `scripts/evaluate_knowledge.py --live`와 세 모드 경계/근거를 구분하는 grader를 제공하지만 자동 승자/정답률/비용 결론은 내리지 않는다. 사용량이 없는 값은 unknown/None으로 보존하고 원본 run의 usage를 남긴다. C에는 규칙 평가도 있으므로 Graph 저장 형식만의 효과라고 주장하지 않는다.

지식 등록/개정은 검토된 패키지와 archive 배포 방식이며 임의 업로드/OCR/LLM 추출은 없다. 현재 검색은 작은9개 문서 집합용이다. 기존 v2 비교 UI의 snapshot 준비 실패는 과거 절에 남기며 이번에 해당 회귀를 통과했다고 주장하지 않는다. 테스트는 별도 Neo4j/폐기용 test build를 사용했고 사용자 데모 DB·volume 초기화나 실행 중인 사용자 서비스 종료는 하지 않았다. 적용하려면 기존 launcher를 종료한 뒤 full 프로필을 재실행하고 브라우저를 새로고침해야 한다.

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
