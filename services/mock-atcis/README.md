# Mock ATCIS (합성 지상 체계)

실제 체계 내부 구조와 무관한 가상 스키마를 사용한다. 자체 UI/API/SQLite/시뮬레이터를 제공하며 KNCCS·플랫폼·Neo4j·LLM·MCP 없이 실행한다.

저장소 개발 환경: `uv run --package mock-atcis mock-atcis` (http://127.0.0.1:4100).
배포 환경: 정적 UI를 포함해 빌드한 mock-atcis wheel 및 명시된 Python 의존성을 설치한 뒤 `mock-atcis`를 실행한다. Node는 UI 빌드에만 필요하다.

설정: ATCIS_PORT, ATCIS_DB(기본 var/atcis-v2.db), ATCIS_READ_TOKEN, ATCIS_CONTROL_TOKEN. 기존 DB를 덮어쓰지 않는다. 새 seed는 semantic-demo-v2이며 기존 DB는 운영자가 reset을 명시적으로 선택하기 전까지 보존한다.

Agent용 목록/집계는 typeCode/statusCode로 native classCode/readyCode를 비교한다. common kind/availability로 필터하지 않는다. ownerUnitCode는 기존 native 이름이며 assignmentRole=shared_support는 전속 소유가 아닌 공동지원 배속이다. UI 표시 변환과 안정 Graph export는 Agent 조회 경로와 구분한다.

공개 `/api/v1` 읽기: snapshot, snapshots/{id}, situation, equipment, equipment/{id}, units, unit-relations, assignments, identity-records, stable-export, events, stream, changes, equipment/{id}/history, equipment-summary. 조회는 snapshotId 또는 epoch/throughSequence를 지정한다. 목록 limit 최대100·cursor를 지원한다.
제어: POST simulation/start, simulation/pause, scenario/reset; PATCH equipment/{id}. 제어 토큰은 읽기 토큰과 구분한다. reset은 명시적 운영자 조작이다.

ATCIS MCP는 별도 `uv run --package atcis-mcp atcis-mcp`로 실행한다. ATCIS_BASE_URL, ATCIS_READ_TOKEN, ATCIS_MCP_TOKEN, ATCIS_MCP_PORT를 설정한다. MCP는 제어 기능을 제공하지 않는다.
