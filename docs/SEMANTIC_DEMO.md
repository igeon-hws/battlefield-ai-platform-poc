# Semantic Layer ON/OFF 시연·평가

상태: v0.6 / S8, 2026-10-16. 실행 경계는 `2-native-off`, 원천 도구 계약은 v2다. [PRD](./PRD.md), [Semantic 아키텍처](./SEMANTIC_ARCHITECTURE.md), [Ontology](./ONTOLOGY_DESIGN.md)를 따르며 실측은 [구현 보고서](./IMPLEMENTATION_REPORT.md)에 별도로 기록한다.

## 비교 조건

OFF는 원천 C4I MCP와 일반 계산만 사용한다. Semantic MCP/Graph/개념·상태 해석/조직 해소/동일성 판정 helper를 직접 또는 간접 호출하지 않는다. 원천 목록·집계는 native 필드/코드만 반환한다. `aggregate_evidence`는 OFF에서 원천 레코드 수·명시적 필드값의 빈도/필터만 계산하고 canonical ID·공통 가용 상태를 만들지 않는다.

ON은 같은 원천에 Semantic MCP를 추가한다. SemanticService가 개념·조직 범위·동일성·버전 있는 원천 코드 대응을 제공하고, 플랫폼 집계는 해당 근거를 적용한다. 가용 상태/위치는 Graph가 아닌 고정 원천 snapshot에서 읽는다. Semantic 장애 시 공유 helper로 우회하지 않는다.

원천의 native 조직/배속/공통 식별참조를 OFF에서 감추지 않는다. Agent가 원천 사실로 같은 정답을 스스로 추론할 수 있으며 이를 실패로 만들지 않는다. OFF의 모델 추론과 서버가 검증한 Semantic 해석을 구분한다. ON의 성공·호출 수/비용 우위를 미리 보장하지 않는다.

## 충돌 없는 기본 fixture

새 기본 dataset은 `semantic-demo-v2`다. D1→B11→C111, F1→S11이며 D2는 질문 범위 밖이다. production 원천 seed는 각각 독립 JSON, 테스트 입력과 gold는 `tests/fixtures/semantic-demo-v2/`로 분리한다. production은 gold를 import하지 않는다.

| 자산 | ATCIS | KNCCS | 상태/관계 |
| --- | --- | --- | --- |
| EX-T01 | T-A01 / B11 | 없음 | tank, 가용 |
| EX-T02 | T-A02 / C111 | 없음 | tank, 가용 |
| EX-T03 | T-A03 / C111 | 없음 | tank, 불가 |
| EX-T04 | T-A04 / B11 | 없음 | tank, 미확인 |
| EX-T05 | T-A05 / D2 | 없음 | 질문 범위 밖 |
| EX-S01 | 없음 | V-K01 / S11 | naval_vessel, 가용 |
| EX-S02 | 없음 | V-K02 / S11 | naval_vessel, 불가 |
| EX-U01 | U-A01 / B11 | C-K77 / S11 | 같은 UAV, 양쪽 가용, assignmentRole=shared_support |

공유 UAV는 초기 위치와 이동 벡터·유형·아군 구분도 일치한다. 서로 다른 B11/S11 기록은 명시적인 비전속 공동지원 배속이며, 서로 다른 전속 소유 주장으로 해석하지 않는다. ownerUnitCode는 기존 native 필드 이름이며 실제 관계의 역할은 assignmentRole을 함께 읽는다. 관측 시각은 각 체계가 기록한다. 두 독립 시뮬레이터의 운용 시점 차이는 출처와 시각으로 밝힌다.

## 세 시나리오

| 질문 | ON의 검증된 기대값 | OFF 검증 |
| --- | --- | --- |
| 모의 1사단의 가용한 탱크를 보여줘 | 탱크 4건, 가용 T-A01/T-A02 2·불가 1·미확인 1 | 원천 근거/필드값 집계, 공통 해석은 모델 추론과 구분 |
| 모의 1사단과 모의 1함대의 가용 전력을 통합해서 보여줘 | 원천 8건/고유 7개, 가용 4·불가 2·미확인 1·충돌 0. 가용은 탱크 2·함정 1·UAV 1 | 원천 범위 8건 확보·일반 계산만 실행. 서버가 cross-system canonical 집계를 생성하면 격리 실패 |
| U-A01과 C-K77은 같은 객체야? | EX-U01 연결·양쪽 가용·공동지원 관계·서로 다른 ID와 출처/규칙 근거 제시 | raw 식별참조와 관측 조회. 동일성 결론은 모델 추론임을 밝히고 확정 helper를 사용하지 않음 |

기본 데모는 원천 데이터 불일치를 시연하지 않는다. 잘못된 ID/상태 충돌/동명/누락/미완결 페이지는 별도 negative fixture에서 방어 동작만 검증한다. 실제 충돌이 생겼을 때 UI나 집계가 이를 0으로 숨기지는 않는다.

## 운영자 진행 순서

1. README의 v2 DB 실행 설정을 사용한다. 기존 v1 DB는 보존하며 자동 reset하지 않는다. 기존 DB를 계속 쓸 때는 원천 UI의 명시적 초기화로 새 seed/epoch를 적용할 수 있다.
2. 양쪽 원천 UI에 `semantic-demo-v2`가 표시되는지 확인하고 비교 중 시뮬레이션은 정지 상태로 둔다.
3. 같은 질문으로 `동일 기준으로 비교`를 실행한다. 두 run의 source snapshot 집합·질문·모델/예산은 같고 대화/근거는 분리된다.
4. OFF에서 Semantic 호출/해석 집계가 없는지, ON에서 조직 경로·연결/코드 대응 근거가 실제 조회됐는지 trace를 연다. UI는 native 집계에 가용/고유 수량을 만들어 표시하지 않는다.
5. manifest의 데이터셋·snapshot·Graph·Ontology/매핑·정책 버전을 확인한다. 과거 비교는 `이전 정책`으로 표시하며 현재 격리 검증 결과로 재사용하지 않는다.

원천 이동·상태 변경의 지도/SSE 반영과 이벤트 분석, 대화/세 방책 선택은 유지 기능으로 별도 확인한다. Graph 중단 시 OFF는 계속 동작하고 ON은 오류/한계를 기록한다. 원천 하나 단절 시 coverage 부족을 전체 0으로 표시하지 않는다.

## 평가와 수용

- 핵심 수용: OFF Semantic 코드 실행/주입 0건, ON 해석 근거 추적 가능, 정상 v2 seed 충돌 0건.
- 실제 source MCP 테스트는 원천 정규화 helper를 예외로 차단한 상태에서 11개 읽기 도구를 호출한다. OFF 계산/좌표·과거 정책 대화 유출도 행동 테스트로 검사한다.
- native/semantic 페이지의 완결성, 동일 객체의 모든 원천 관측 확보, 버전/시점 고정, 근거 없는 canonical 그룹 거부를 검증한다.
- 자동 채점은 모드별 도구 근거/수량 검사다. OFF raw coverage 성공은 답변의 Semantic 결론이 검증됐다는 뜻이 아니며 자연어 품질·추론 표기는 Human Review 대상이다. 결정론적 model adapter를 실제 GPT 효용 결과로 보고하지 않는다.
- S8의 실제 GPT 기본 검증은 S1~S3 각 1쌍, 총 3쌍/6 run이다. 시간·도구/모델 호출·토큰·오류·순서를 별도 artifact에 기록한다. 문제 해결 후 추가 호출은 원본과 분리한다.
- 기존 v1의 15쌍은 이전 공유 Semantic helper 정책의 역사적 결과다. v2의 격리·무충돌 효과를 입증하는 자료로 재해석하지 않는다. 소수 실행의 비용/속도 차이를 일반화하지 않는다.
