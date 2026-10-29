# REVIEW

### 역할 

사용자의 Review를 관리하고, 
이를 기반으로 문서에 다음 구현 plan을 IMPLEMENTATION.PLAN.md에 기록한다.

### 내용 

Semantic 도구 호출 및 조회 효율 개선

실제 C 모드 복합 질의에서 총 20회 도구 호출이 발생했으며, 다음 문제를 확인함.

interpret_concept("availability")가 질문과 무관한 해상 장비·보고·절차 규칙까지 포함한 전체 규칙 12개를 반환함. 질의 목적에 맞는 선택적 규칙 검색 및 의존 규칙 확장 방식 검토.

동일한 스냅샷과 인자로 list_cargo, list_supply_requests를 각각 3회 반복 호출함. Run 단위 도구 응답 캐싱 및 Evidence 재사용 개선.

query_relations()에서 L-T02의 군수 관계 조회 결과가 0건으로 반환됨. SAME_AS 누락, 관계 방향, 탐색 범위 및 Agent의 도구 호출 인자를 점검.

복구 가능성 질의와 관련이 낮은 get_procedure_definition(SOP-01) 호출 발생. 불필요한 규칙 노출과 도구 선택 문제를 함께 검토.

변경 전후 도구 호출 횟수, 중복 호출률, 반환 토큰량, 관계 조회 정확도 및 응답 시간을 측정하여 개선 효과 검증.

기존 Semantic MCP와 Agent 아키텍처를 유지하면서, 정확한 관계 탐색과 최소한의 도구 호출로 필요한 근거를 확보하도록 개선할 것.