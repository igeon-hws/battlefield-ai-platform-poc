# Agentic Battlefield Intelligence Platform

독립 Mock ATCIS·Mock KNCCS·Mock LOGISTICS → Data Fabric(Ontology·Semantic Layer·MCP) → 단일 분석 Agent를 연결하는 Python PoC.

처음에는 [PRD](docs/PRD.md) → [ARCHITECTURE](docs/ARCHITECTURE.md) → [UI_GUIDE](docs/UI_GUIDE.md) 순서로 읽는다. 빠른 실행은 아래를, 상세 설정과 검증은 [ARCHITECTURE의 설치와 실행](docs/ARCHITECTURE.md#8-설치와-실행)을 참고한다.

## 실행 방법

Python 3.12, uv, Node.js 20.19+ 또는 22.12+, Docker Desktop을 준비하고 Docker Desktop을 실행한다. 아래 명령은 저장소 루트의 PowerShell에서 실행한다.

### 최초 설정과 빌드

`.env`가 없으면 예제 파일을 복사한다. 기존 `.env`가 있으면 그대로 사용한다.

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

`.env`에 `OPENAI_API_KEY`, 사용할 `OPENAI_MODEL`, `NEO4J_PASSWORD`를 입력한다. 읽기·제어·MCP 토큰은 `.env.example`을 참고해 설정하고 연결 서비스 간 값을 일치시킨다. 기존 Neo4j 볼륨이 있으면 해당 비밀번호를 유지한다. 실제 Agent 분석은 OpenAI API를 호출하므로 비용이 발생한다.

```powershell
uv sync --all-packages
uv run python scripts/export_contracts.py
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run python scripts/build_ui.py
```

### 전체 데모 실행

```powershell
docker compose up -d neo4j
uv run python scripts/dev.py --profile full --contract-version 5
```

현재 v5 데모는 `--profile full`을 명시한다. 프로필을 생략하면 legacy가 실행된다. 실행 터미널을 열어 둔 채 다음 주소로 접속한다. 아래 주소는 기본 포트 기준이다.

| 화면 | 주소 | 사용 방법 |
| --- | --- | --- |
| 분석 플랫폼 | [localhost:4300](http://localhost:4300) | A/B/C 별도 진입·원천 탐색·분석·동일 기준 비교 |
| Mock ATCIS | [localhost:4100](http://localhost:4100) | 지상 원천 조회·시뮬레이션 제어 |
| Mock KNCCS | [localhost:4110](http://localhost:4110) | 해상 원천·수송/입항 조회·시뮬레이션 제어 |
| Mock LOGISTICS | [localhost:4120](http://localhost:4120) | 군수 자산·정비·부품·재고/예약·화물 조회·정비 상태 제어 |
| Data Fabric | [localhost:4400](http://localhost:4400) | 지식 문서·Graph·규칙·근거 확인 |
| Neo4j Browser | [localhost:7474](http://localhost:7474) | Graph 확인 (`neo4j` / 설정한 비밀번호) |

원천 시뮬레이터는 처음에 정지 상태다. ATCIS·KNCCS·LOGISTICS 화면에서 `1초 진행` 또는 `시작`으로 진행한다. 재실행해도 기존 DB·Graph·대화는 자동 초기화되지 않는다.

종료할 때는 실행 터미널에서 `Ctrl+C`를 누른 뒤 Neo4j를 중지한다.

```powershell
docker compose stop neo4j
```

원천 세 개만 실행하려면 `uv run python scripts/dev.py --profile sources`를 사용한다(MCP·Graph·LLM 불필요). 포트 충돌 시 기존 실행을 확인하거나 launcher에 `--port-offset 1000`을 추가한다. 이 경우 Python 서비스 접속 포트에 1000을 더하며 Neo4j 포트는 그대로다.

기본은 세 체계 v5입니다. 플랫폼 진입 화면에서 A(원천만), B(원천+Fabric 문서), C(같은 문서+구조화 지식)를 선택합니다. 채팅 안의 모드 변경 대신 별도 페이지로 들어가며, 지도와 고정 입력창은 함께 유지됩니다. `Enter` 전송, `Shift+Enter` 줄바꿈이고 `옵션`에서 L0~L5 예시 질문을 선택합니다.

- A/B/C 모두 `원천 탐색`으로 세 체계의 기록을 직접 조회합니다. B/C는 `문서`에서 같은 지식 집합의 설명·판정 기준을 읽습니다.
- C에서 `객체` 목록의 **L-T02**를 선택하면 정비 M-17·부품/재고·화물 C-12·수송 N-21과 출처별 시점·연결 근거를 봅니다. 클릭만으로 모델을 호출하지 않습니다. `이 객체에 질문 작성`은 초안이며 전송 시 실제 Agent가 실행됩니다.
- 진입 화면의 `동일 기준 A/B/C 비교`는 같은 세 원천 snapshot·B/C 지식 집합을 고정합니다. 개별 페이지에서 서로 다르게 탐색한 결과와 구분해 검토합니다. 비교 탭/확대 보기와 이력에서 다시 열 수 있습니다.
- 군수 :4120의 `정비 작업`→M-17에서 정비 상태를, 해군 :4110의 `수송·입항`→N-21에서 입항·인도6시간 지연을 적용할 수 있습니다. 원천 업무 변경과 AI의 가정 분석은 별개입니다.
- C 상세는 현재 상태·소속·제약, 정비·부품·재고·수송, 정보 시점을 먼저 보여 줍니다. 원본·연결 근거·버전은 펼쳐서 확인합니다. 정비 소요 시간은 h이며 인시가 아닙니다.
- 지도 상단에서 지상/해상 관측을 필터링하고 C의 `의미 객체 보기`에서 검증된 자산별 연결 관측을 확인합니다. 위치가 다른 관측은 모두 유지합니다.
- 반복 평가의 무과금 준비(`--dry-run`)와 고정 조건/검토 양식 사용법은 [평가 도구](docs/ARCHITECTURE.md)를 참고하세요. 이번 구현에서는 유료 모델 성능을 측정하지 않았습니다.

A/B만 실행하려면 `uv run python scripts/dev.py --profile off --contract-version 5`를 사용합니다(Knowledge MCP 포함, Neo4j 불필요). C/전체 비교에는 full이 필요합니다. 군수만 실행하려면 `uv run --package mock-logistics mock-logistics`입니다. `.env.example`의 LOGISTICS 읽기/제어/MCP 토큰과 연결 서비스 값을 맞춥니다. 페이지 분리는 로컬 시연 조건이며 운영 사용자 인증은 아닙니다.

v5는 별도 `var/*-v5.db`를 사용합니다. 기존 두 체계 A/B/C 화면은 `--profile full --contract-version 4`, 문서 허용 OFF/ON은 `--contract-version 3`으로 기존 DB·정책을 유지합니다. 기존 데이터·Graph를 초기화하지 않습니다. 이미 서버가 실행 중이면 해당 실행 터미널에서 Ctrl+C 후 재실행하고 브라우저를 새로고침합니다. 상세 API·설정·검증은 [ARCHITECTURE](docs/ARCHITECTURE.md)를 따릅니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [STEP](docs/STEP.md) | 현재 단계와 수행 주체 |
| [PRD](docs/PRD.md) | 목표·범위·데모·평가 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 기술 설계와 실행 안내 |
| [UI_GUIDE](docs/UI_GUIDE.md) | 화면·상호작용 기준 |
| [ADR](docs/ADR.md) | 기술 결정 이유 |
| [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) | 다음 유효 구현 작업 |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | 실제 구현·검증·한계 |
| [REVIEW](docs/REVIEW.md) | 사용자 검토 |

에이전트 작업 지침은 [AGENTS](AGENTS.md)와 [battlefield-sdd SKILL](.agents/skills/battlefield-sdd/SKILL.md)을 따른다.
## 서비스 구성

| 모듈 | 기본 주소 | 책임 |
| --- | --- | --- |
| mock_atcis.app | :4100 | 지상 native API/UI/시뮬레이터/DB |
| mock_knccs.app | :4110 | 해상 native API/UI/시뮬레이터/DB |
| mock_logistics.app | :4120 | 군수 native API/UI/시뮬레이터/DB |
| mock_logistics.mcp | :4220/mcp | 군수 공개 API 읽기 어댑터 |
| atcis_mcp.server | :4200/mcp | ATCIS 공개 API 읽기 어댑터 |
| knccs_mcp.server | :4210/mcp | KNCCS 공개 API 읽기 어댑터 |
| platform_api.app | :4300 | 분석 UI·대화·큐·Agent·비교 |
| semantic_api.app | :4400 | Fabric API/읽기 콘솔·Semantic API |
| semantic_mcp.server | :4410/mcp | Semantic API의 읽기 도구 |
| graph_builder.app | :4420 | 내부 Graph build 관리 API |
| semantic_mcp.knowledge | :4430/mcp | Fabric 지식 문서 읽기 도구 |
| Neo4j Docker | Bolt :7687 / Browser :7474 | 안정 의미·관계·근거 저장 |
