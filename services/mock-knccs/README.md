# Mock KNCCS (합성 해상 체계)

실제 체계 내부 구조와 무관한 가상 스키마를 사용한다. 자체 UI/API/SQLite/시뮬레이터를 제공하며 ATCIS·플랫폼·Neo4j·LLM·MCP 없이 실행한다.

저장소 개발 환경: `uv run --package mock-knccs mock-knccs` (http://127.0.0.1:4110).
배포 환경: 정적 UI를 포함해 빌드한 mock-knccs wheel 및 명시된 Python 의존성을 설치한 뒤 `mock-knccs`를 실행한다. Node는 UI 빌드에만 필요하다.

설정: KNCCS_PORT, KNCCS_DB(기본 var/knccs-v2.db), KNCCS_READ_TOKEN, KNCCS_CONTROL_TOKEN. 다른 체계 DB를 공유하지 않는다. 새 seed는 semantic-demo-v2이며 기존 DB는 명시적 reset 전까지 보존한다.

Agent용 목록/집계는 typeCode/statusCode로 native platformCategory/serviceability를 비교한다. 공통 kind/availability를 해석하지 않는다. 공유 UAV는 가용·아군·공통 초기 위치/벡터와 assignmentRole=shared_support를 제공한다. 원천별 조직은 전속 소유가 아닌 명시적 공동지원 관계다.

공개 `/api/v1` 읽기: snapshot, snapshots/{id}, situation, equipment, equipment/{id}, units, unit-relations, assignments, identity-records, stable-export, events, stream, changes, equipment/{id}/history, equipment-summary. 조회는 snapshotId 또는 epoch/throughSequence를 지정한다. 목록 limit 최대100·cursor를 지원한다.
제어: POST simulation/start, simulation/pause, scenario/reset; PATCH equipment/{id}. courseDeg는 북쪽0도·시계방향이며 speedKnots를 사용한다. 제어와 읽기 토큰을 분리한다.

KNCCS MCP는 별도 `uv run --package knccs-mcp knccs-mcp`로 실행한다. KNCCS_BASE_URL, KNCCS_READ_TOKEN, KNCCS_MCP_TOKEN, KNCCS_MCP_PORT를 설정한다. MCP는 제어 기능을 제공하지 않는다.
