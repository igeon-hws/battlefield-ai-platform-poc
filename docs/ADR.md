# ADR — Architecture Decision Records

현재 기술 계약은 [ARCHITECTURE](ARCHITECTURE.md), 실제 검증은 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)가 기준이다. 이 문서는 결정 이유·영향만 남긴다. 아래 기존 번호를 보존하며 중복됐던 ADR-023은 v3 결정과 S8 역사 항목으로 구분한다.

## 현행 핵심 결정

| ID | 결정과 이유 | 영향/대가 |
| --- | --- | --- |
| 001·017 | 두 원천을 각각 UI/API/DB/시뮬레이터로 독립 제공. 실제 외부 체계 경계와 이종성 시연 | 배포/설정 증가; 합성 schema 사용 |
| 002·015 | 실제 MCP Client→Server→공개 API, 서버 소유 tools/list 정의를 run별 발견 | 내부 결합/가짜 MCP 방지; schema/연결 실패 처리 필요 |
| 003·004 | 상황판 수집과 Agent 조회 분리, 서버 소유 큐/실행 | 지도 주기와 LLM 주기 분리; 연결/시점 관리 |
| 005·020 | 원천 snapshot 집합과 대응하는 불변 READY Graph에 run 고정 | 재현성/미래 정보 혼입 방지; 보관량 증가 |
| 006·009·010·011 | Python 단일 Agent·OpenAI native tool loop·얇은 하네스, 프론트만 TS | 다중 Agent/DAG 폐기; 앱이 loop/예산/맥락 관리 |
| 007·018 | 원천/플랫폼 SQLite 유지, 안정 관계는 Neo4j. Ontology→Builder→Graph→API→MCP 분리 | 의미의 서비스 재사용; Docker/버전 운영 추가 |
| 019 | 명시적 원천 관계·association으로만 ER, LLM 관계 생성 금지 | 설명 가능성 확보; 모호하면 미해결로 남김 |
| 021·022 | 같은 원시 정보/시점/예산의 격리 OFF/ON 비교 | 의미 구조화 효과와 추가 정보 효과 구분; OFF 성공 허용 |
| 024 | 표준 라이브러리 실행별 UTF-8 로그와 선택적 loop 이벤트 callback | 별도 관측 서버 없이 추적; 마스킹/생략/I/O 격리, 자동 retention 없음 |

## ADR-023 — Native C2 + Data Fabric v3 (2026-10-22)

원천별 native SQL/API/UI를 분리하고 공유 runtime을 기계 기능으로 한정한다. 기존 semantic-api를 Fabric API/콘솔로 확장해 gateway/브로커를 추가하지 않는다. 검토 문서 hash/version·명시적 adapter·JSON 규칙·Neo4j 저장을 분리한다. 범용 추론 엔진 도입은 유보한다.

OFF는 native 문서/일반 계산이며 ON만 Semantic 해석·조건 평가를 추가한다. 원천 지식을 숨겨 인위적인 차이를 만들지 않는다. 집계는 current-run 페이지·범위·동일성·상태·정책 근거를 요구한다. 일부 빈 조회를0으로 확정하지 않으며 유형×상태 계산을 제공한다. 모델의 수동 표 작성 사례 때문에 실행 완료와 검증된 정답을 분리한다. v2 호환 분기·명시적 규칙 검토가 유지 비용이다.

## S8 결정 — 과거 중복 ADR-023 (2026-10-16)

초기 ADR-021의 공유 로컬 계산에서 Semantic helper가 실행될 여지를 대체했다. OFF는 간접 의미 해석/ER까지 차단하고 ON은 실제 Semantic 근거를 계산에 적용한다. 지도/Builder 변환을 OFF 근거로 주입하지 않는다. 정책이 다른 대화를 이어 쓰지 않는다. 기본 v2 데이터에서 의도적 동일 자산 상태 충돌을 제거했다. 이전 격리 정책의 비교 결과를 새 정책 평가에 재사용하지 않는다.

## 기타 결정의 유지 범위

| ID | 유지하는 내용 |
| --- | --- |
| 008 | 실제 지리 지도·WGS84·적아 벡터 객체, 배경 장애와 원천 장애 분리 |
| 012 | 객체 유형/가용/운용 상태 분리. 현재 공통 분류는 ON 의미 근거 적용, OFF native 계산 |
| 013 | conversation 타임라인·응답별 방책 선택, 선택은 명령 실행 아님 |
| 014 | 시스템 역할과 도구 계약 분리. 도구 정의 소유권은015에서 서버 discovery로 구체화 |
| 016 | 원천 scenario metadata·접경120개 시연은 legacy에서 유지, v3 기대값과 혼용하지 않음 |

고도화 후 loop 예산은 model24/tool20/120초, legacy model12다. 준비 시간은 별도다. 두 원천·Neo4j 도입은 단일 원천/전체 SQLite 한정 전제를 대체하지만 단일 Agent/Python/MCP 경계는 유지한다.

2026-10-26 문서 통합은 기술 결정 변경이 아니다. 세부 설계 중복을 ARCHITECTURE로 옮기고 과거 실측을 STATUS로 구분했다. 새 결정은 승인된 Implement의 실제 변경 이유가 있을 때만 여기에 기록한다.
