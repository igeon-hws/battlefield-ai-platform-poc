# 독립 Mock C4I

자체 Python API·시뮬레이터·SQLite와 React 정적 UI를 포함한다. 다른 서비스나 LLM 없이 실행한다.

## 저장소에서 실행

루트에서 `uv sync --all-packages` 후 `uv run --package mock-c4i mock-c4i`를 실행한다. UI는 먼저 프론트엔드 빌드와 scripts/build_ui.py로 포함한다.

## wheel 배포

루트에서 `uv build --package c4i-contracts`, `uv build --package battlefield-geo`, `uv build --package mock-c4i`를 실행한다. 생성된 세 wheel을 별도 Python 3.12 환경에 전달하고 설치한다.

```powershell
python -m pip install c4i_contracts-0.1.0-py3-none-any.whl battlefield_geo-0.1.0-py3-none-any.whl mock_c4i-0.1.0-py3-none-any.whl
mock-c4i
```

공개 Python 의존성 설치에는 네트워크 또는 준비된 wheelhouse가 필요하다. 실행 시 Node·npm·platform-api·MCP Server·OpenAI API가 필요하지 않다. 배경 지도는 온라인 타일을 사용한다.

## 설정과 API

C4I_PORT 기본 4100, C4I_DB 기본 var/c4i.db. 선택적 C4I_READ_TOKEN·C4I_CONTROL_TOKEN은 Authorization: Bearer 헤더로 전달하며 자체 UI의 연결 설정에서도 입력할 수 있다.

- `/health`, `/api/v1/snapshot`, `/api/v1/snapshots/{snapshotId}`
- `/api/v1/entities`, `/api/v1/entities/summary`, `/api/v1/entities/{entityId}`
- `/api/v1/entities/{entityId}/history`: epochId·after(제외)·throughSequence(포함)·limit, items 및 nextAfter 반환
- `/api/v1/changes`, `/api/v1/events`, `/api/v1/stream`
- 자체 운영 UI: `POST /api/v1/simulation/{start|pause|reset}`, `PATCH /api/v1/entities/{entityId}`

FastAPI `/docs`에서 계약을 확인한다. 목록·집계는 atSnapshot, kind, affiliation, availability, status, maintenanceStatus, unitId, zoneId, bbox=west,south,east,north를 지원한다. SSE는 epochId·after 또는 Last-Event-ID를 사용한다. 기본 C4I_SCENARIO=border-demo는 접경 전역의 합성 객체 120개이며 west-coast-demo는 기존 11개 시나리오다. 기존 DB의 시나리오·경계는 유지되며 새 설정 적용은 UI 초기화로 수행한다. 가용성과 정비 상태는 독립적으로 변경한다.

snapshot의 scenario metadata는 표시명·버전·bounds·initialBounds·zones를 포함한다. UI는 이를 읽어 전체 보기와 구역 이동을 제공한다. 이동은 zoneId 구역 또는 시나리오 경계에서 정지한다. 시연 구역은 실제 작전 구역이 아니며 지형·도로·항로 추종은 포함하지 않는다.

초기 시뮬레이션은 일시 정지다. WGS84 위치를 1초 단위로 갱신하며 시나리오 경계에서 정지한다. 지형·해상 이동 경로 제약은 모사하지 않는다. snapshot과 이벤트는 reset 이후에도 보관되며 자동 정리 정책은 별도로 두지 않았다.
