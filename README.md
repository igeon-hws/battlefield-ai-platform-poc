# Agentic Battlefield Intelligence Platform

독립 Mock ATCIS·Mock KNCCS → Data Fabric(Ontology·Semantic Layer·MCP) → 단일 분석 Agent를 연결하는 Python PoC.

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
uv run python scripts/dev.py --profile full
```

현재 v3 데모는 `--profile full`을 명시한다. 프로필을 생략하면 legacy가 실행된다. 실행 터미널을 열어 둔 채 다음 주소로 접속한다. 아래 주소는 기본 포트 기준이다.

| 화면 | 주소 | 사용 방법 |
| --- | --- | --- |
| 분석 플랫폼 | [localhost:4300](http://localhost:4300) | 질문·분석 및 ON/OFF 비교 |
| Mock ATCIS | [localhost:4100](http://localhost:4100) | 지상 원천 조회·시뮬레이션 제어 |
| Mock KNCCS | [localhost:4110](http://localhost:4110) | 해상 원천 조회·시뮬레이션 제어 |
| Data Fabric | [localhost:4400](http://localhost:4400) | 의미·관계·근거 확인 |
| Neo4j Browser | [localhost:7474](http://localhost:7474) | Graph 확인 (`neo4j` / 설정한 비밀번호) |

원천 시뮬레이터는 처음에 정지 상태다. ATCIS·KNCCS 화면에서 `1초 진행` 또는 `시작`으로 진행한다. 재실행해도 기존 DB·Graph·대화는 자동 초기화되지 않는다.

종료할 때는 실행 터미널에서 `Ctrl+C`를 누른 뒤 Neo4j를 중지한다.

```powershell
docker compose stop neo4j
```

원천 두 개만 실행하려면 `uv run python scripts/dev.py --profile sources`를 사용한다(MCP·Graph·LLM 불필요). 포트 충돌 시 기존 실행을 확인하거나 launcher에 `--port-offset 1000`을 추가한다. 이 경우 Python 서비스 접속 포트에 1000을 더하며 Neo4j 포트는 그대로다.

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
| atcis_mcp.server | :4200/mcp | ATCIS 공개 API 읽기 어댑터 |
| knccs_mcp.server | :4210/mcp | KNCCS 공개 API 읽기 어댑터 |
| platform_api.app | :4300 | 분석 UI·대화·큐·Agent·비교 |
| semantic_api.app | :4400 | Fabric API/읽기 콘솔·Semantic API |
| semantic_mcp.server | :4410/mcp | Semantic API의 읽기 도구 |
| graph_builder.app | :4420 | 내부 Graph build 관리 API |
| Neo4j Docker | Bolt :7687 / Browser :7474 | 안정 의미·관계·근거 저장 |
