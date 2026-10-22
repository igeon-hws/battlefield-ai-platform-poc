# Agentic Battlefield Intelligence Platform

## 현재 실행: Native C2 + Data Fabric v3

2026-10-22 구현 기준은 `c2-domain-demo-v3`다. 육군·해군의 독립 native 체계, Data Fabric API/콘솔·Ontology/Neo4j·MCP, 기존 단일 동적 분석 Agent를 연결한다. 아래 S8/v2 설명은 과거 호환 기록이다. 현재 상태·검증 한계는 [STEP](docs/STEP.md)과 [구현 보고서](docs/IMPLEMENTATION_REPORT.md)를 따른다.

최초 설치/빌드 후 실행한다. `.env`에 `OPENAI_API_KEY`, `OPENAI_MODEL`, `NEO4J_PASSWORD`를 설정하며 기존 Neo4j volume의 비밀번호는 유지한다.

```powershell
uv sync
uv run python scripts/export_contracts.py
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run python scripts/build_ui.py
docker compose up -d neo4j
uv run python scripts/dev.py --profile full
```

육군 UI :4100, 해군 UI :4110, Fabric 콘솔 :4400, 분석 플랫폼 :4300이다. 원천 MCP :4200/mcp·:4210/mcp, Semantic MCP :4410/mcp, Builder 관리 API :4420을 사용한다. 원천은 처음에 일시 정지다. UI의 1초 진행/시작/정지 및 상태 변경으로 재현한다. Agent 도구는 읽기 전용이다.

| 프로필 | 실행 범위 |
| --- | --- |
| sources | 두 원천만; MCP/Graph/LLM 없이 실행 |
| fabric | 원천 MCP2 + Fabric API + Builder + Semantic MCP; 원천은 별도 실행 |
| platform | 분석 플랫폼만; 외부 Fabric/MCP 주소 설정 필요 |
| off | 두 원천 + 원천 MCP2 + Fabric core + 플랫폼; Neo4j 불필요 |
| full | 전체 Python 서비스 + 별도 Docker Neo4j |
| legacy | 기존 단일 C4I; 프로필 생략 시 기본값 |

v3는 기본 `var/atcis-v3.db`, `var/knccs-v3.db`, `var/platform-v3.db`를 사용한다. `ATCIS_V3_DB`, `KNCCS_V3_DB`, `PLATFORM_V3_DB`로 변경할 수 있다. 기존 DB/Graph/대화를 자동 reset하지 않는다. `--contract-version 2`는 호환 경로다. 포트가 겹치면 기존 실행을 사용하거나 `--port-offset 1000`을 사용한다. Ctrl+C는 해당 launcher가 시작한 프로세스만 종료한다.

단독 원천 CLI는 `uv run --package mock-atcis mock-atcis`, `uv run --package mock-knccs mock-knccs`이며 기본 native v3다. 기존 v2 handler는 source-runtime의 `legacy` extra가 필요하다. UI는 배포 전에 빌드·포함하므로 실행에 Node는 필요 없다.

플랫폼 F1~F7 예시와 기준보고 선택 후 `동일 기준으로 비교`를 사용한다. OFF도 원천 문서/코드표를 읽을 수 있고, ON에만 구조화된 의미 근거/평가가 추가된다. F7 기대값은 고유 7개, available 4·limited 1·unavailable 1·unknown 1이다.

```powershell
docker compose --profile test up -d neo4j-test
uv run pytest -q
uv run pytest -m "neo4j and not live" -q
# 실제 모델 호출·비용 발생, 명시적 실행:
uv run pytest tests/test_domain_live.py -m "live and neo4j" -q -s
uv run python scripts/grade_domain.py artifacts/<생성된-domain-live>.json --output artifacts/<새-평가>.json
```

현재 작업 환경에서는 원래 `.venv`의 Python 경로가 깨져 저장소 내부 `var/implementation-venv`로 검증했다. 같은 문제가 있으면 기존 환경을 지우지 말고 유효한 Python 3.12로 별도 환경을 지정한다. 정상 `.venv`에서는 위 `uv run` 명령을 사용하면 된다.

## 이전 S8/v2 실행·검증 기록

Python 기반 전장의 분석형 AI 플랫폼 PoC. 독립 Mock C4I → MCP Server → 단일 동적 분석 Agent로 연결한다. UI는 React·TypeScript 정적 앱이며 각 Python 서버가 제공한다.

**Mock ATCIS + Mock KNCCS + Neo4j/Ontology 기반 Semantic Layer** 고도화를 구현·검증했고 현재 사용자 Review 단계다. [구현 계획](docs/IMPLEMENTATION_PLAN.md), [검증 보고서](docs/IMPLEMENTATION_REPORT.md), [Ontology·매핑](docs/ONTOLOGY_DESIGN.md), [현재 STEP](docs/STEP.md)을 참고한다. 기존 단일 C4I는 legacy 프로필로 유지한다.

## 이종 C4I·Semantic 데모 실행

S8 정책은 OFF의 Semantic helper 간접 호출까지 차단한다. OFF는 native 필드/코드와 일반 수량 계산만 사용하고, ON은 Semantic 도구의 개념·조직·동일성·코드 대응 근거를 추가 사용한다. 기본 dataset은 충돌 없는 `semantic-demo-v2`이며 통합 기대값은 원천 8건/고유 7개/가용 4·불가 2·미확인 1이다. OFF의 모델 추론은 서버가 검증한 공통 집계와 구분한다.

기존 `.env`가 v1 DB 경로를 지정했다면 기존 개발 서버를 Ctrl+C로 종료하고 다음처럼 **새 DB**를 지정해 실행한다. 과거 DB를 지우거나 자동 reset하지 않는다. 원천 UI와 비교 manifest에서 dataset이 v2인지 확인한다.

```powershell
$env:ATCIS_DB='var/atcis-v2.db'
$env:KNCCS_DB='var/knccs-v2.db'
$env:PLATFORM_VNEXT_DB='var/platform-vnext-v2.db'
docker compose up -d neo4j
uv run python scripts/dev.py --profile full
```

기존 DB를 명시적으로 계속 사용할 수도 있지만 새 정책과 다른 대화는 이어 쓰지 않으며, v1 원천 데이터가 자동으로 v2가 되는 것은 아니다. 이전 비교는 UI에 `이전 정책`으로 표시한다. 원천 API/MCP 목록·집계 필터는 공통 kind/availability 대신 **native typeCode/statusCode**를 사용한다. 기존 통합 Client도 해당 인자를 갱신해야 한다.

아래 빠른 시작의 의존성 설치·계약 export·UI 빌드를 먼저 수행한다. `.env`에 `OPENAI_API_KEY`, `OPENAI_MODEL`, `NEO4J_PASSWORD`를 설정한다. API 키/비밀번호를 Git에 추가하지 않는다. Neo4j 전용 비밀번호는 비어 있으면 안 되며 최초 volume 생성에 사용한 값을 유지한다.

```powershell
docker compose up -d neo4j
uv run python scripts/dev.py --profile full
```

- Mock ATCIS: http://127.0.0.1:4100 / MCP :4200/mcp
- Mock KNCCS: http://127.0.0.1:4110 / MCP :4210/mcp
- 분석 플랫폼: http://127.0.0.1:4300
- Semantic API: :4400 / MCP :4410/mcp / Builder 내부 관리 :4420
- Neo4j Browser: http://127.0.0.1:7474

기존 데모가 실행 중이면 `--port-offset 1000`을 추가해 Python 서비스만 5100/5110/5300 등의 포트로 실행할 수 있다. 시작 스크립트는 이미 실행 중인 프로세스를 종료하지 않는다. Ctrl+C는 해당 스크립트가 시작한 child만 종료하며 Neo4j volume/기존 DB를 삭제하지 않는다. Docker 중지는 `docker compose stop neo4j`로 별도 수행한다.

Graph 없이 두 원천과 플랫폼 OFF만 실행하려면 `uv run python scripts/dev.py --profile off`를 사용한다. 단독 원천은 `uv run --package mock-atcis mock-atcis`, `uv run --package mock-knccs mock-knccs`로 실행한다. 각 서비스의 README에 공개 API와 설정을 설명했다.

원천 두 개는 처음에 일시 정지다. 플랫폼에서 질문을 입력하고 `동일 기준으로 비교`를 누르면 같은 질문·원천 snapshot 집합과 대응 Graph 버전으로 OFF/ON을 실행한다. 두 모드의 도구·근거는 분리한다. ON/OFF 비교 두 열과 한 run의 세 방책 비교·선택은 별도 기능이다. 모드 변경은 새 대화를 시작한다.

질문 예시:

- 모의 1사단의 가용한 탱크를 보여줘.
- 모의 1사단과 모의 1함대의 가용 전력을 통합해서 보여줘.
- U-A01과 C-K77은 같은 객체야? 상태·배속 차이와 출처를 설명해줘.

새 기본 DB는 var/atcis-v2.db·var/knccs-v2.db 및 var/platform-vnext-v2.db다. 개별 Builder/Platform 실행에는 같은 `BUILDER_ADMIN_TOKEN`을 설정해야 한다. full 스크립트는 비어 있을 때 child 사이에 공유할 임시 토큰을 생성하고 출력하지 않는다. 자동 이벤트 분석은 기본 OFF이며 `AUTO_SEMANTIC_MODE=on`으로 바꿀 수 있다.

고도화 Agent 기본 예산은 model 24회·tool 20회·120초다. AGENT_MAX_ITERATIONS, AGENT_MAX_TOOLS, AGENT_DEADLINE_SECONDS로 변경하며 양 모드에 동일하게 적용한다. 초기 12회 예산의 반복 측정과 조정 후 검증을 보고서에서 구분한다.

검증/반복 평가(실제 GPT 호출에는 API 비용 발생):

```powershell
docker compose --profile test up -d neo4j-test
uv run pytest
uv run pytest -m "neo4j and not live" -q
uv run pytest -m "live and neo4j" tests/test_semantic_live.py -q
uv run python scripts/evaluate_semantic.py --base-url http://127.0.0.1:4300 --repetitions 1 --output artifacts/semantic-evaluation-v2.json
```

실제 Neo4j 테스트는 데모와 다른 17687/17474 포트 및 volume을 사용한다. S8 기본 검증은 v2 원천을 연결·일시 정지한 상태의 S1~S3 각 1쌍이며 결과·trace·manifest·usage는 새 v2 출력 경로에 저장한다. 같은 출력 파일의 기존 repetition은 재호출하지 않는다. 새 평가에는 새 `--output` 경로를 사용하고 과거 v1 파일을 재사용하지 않는다. 자동 점수는 모드별 근거·수량 검사이며 자연어 설명·모델 추론 품질은 사용자 검토가 필요하다.

## 빠른 시작

Python 3.12와 uv가 필요하다. Node 20.19+/22.12+는 UI 빌드 시에만 사용한다.

```powershell
uv sync --all-packages
uv run python scripts/export_contracts.py
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run python scripts/build_ui.py
```

`.env.example`을 참고해 루트에 `.env`를 만든다. 실제 GPT 사용에는 `OPENAI_API_KEY`와 현재 프로젝트에서 접근 가능한 `OPENAI_MODEL`이 필요하다. 키를 Git에 추가하지 않는다.

```powershell
uv run python scripts/dev.py
```

- Mock C4I: http://127.0.0.1:4100
- 분석 플랫폼: http://127.0.0.1:4300
- MCP endpoint: http://127.0.0.1:4200/mcp
- 종료: 실행 터미널에서 Ctrl+C

개별 실행도 가능하다: `uv run --package mock-c4i mock-c4i`, `uv run --package c4i-mcp c4i-mcp`, `uv run --package platform-api platform-api`.

## 데모 흐름

1. 두 UI에서 동일한 적아 객체·유형·위치를 확인한다. C4I는 처음에 일시 정지다.
2. C4I에서 이동을 시작하거나 가용 상태·동/북 속도를 바꾸고 플랫폼 반영을 확인한다.
3. `가용 아군 탱크 보여줘`, `적 탱크는 몇 대야?`를 질의한다.
4. 실행 상세에서 native 호출·실제 MCP 입력/응답·근거를 확인한다.
5. 세 방책을 요청하고 비교 화면에서 하나를 선택한다.
6. 후속 질문의 맥락 유지와 새 snapshot 조회를 확인한다.

기본 시나리오는 실제 남북 접경의 서부·중부·동부와 양쪽 연안을 배경으로 한 **합성 모의 객체 120개(탱크 40·장갑차 24·지원 차량 20·무인기 12·함정 24)**다. 실전 배치 자료를 사용하지 않으며 시연 구역은 실제 접경선·작전 구역이 아니다. 부대·구역·세부 유형·정비 상태·관측 시각·출처를 제공한다. 가용·정비·운용 상태는 독립적이다. 상태·속도 변경은 자동 분석을 생성하고 매초 위치 이벤트는 LLM을 실행하지 않는다.

기존 C4I DB는 재시작 시 현재 시나리오와 경계를 유지한다. 새 접경 시나리오를 적용하려면 서버 재시작 후 C4I UI의 **초기화**를 누른다. 기존 snapshot 이력은 보존하며 새 epoch로 시작한다. `C4I_SCENARIO=border-demo`가 기본이고 `west-coast-demo`는 11개 객체의 이전 데모다. 두 지도는 원천 시나리오 이름·범위를 사용하고 **전체 보기**와 **시연 구역 이동**을 제공한다. 매초 갱신이 사용자의 지도 위치를 초기화하지 않는다.

사용자 질의는 같은 대화의 타임라인에 누적되며 각 응답의 방책을 독립적으로 선택한다. 선택한 방책은 원래 응답에 표시되고 후속 질문의 맥락에 포함된다. 같은 브라우저 탭의 새로고침은 현재 대화를 복원하며 **새 대화**는 별도 conversation으로 시작한다.

현재 MCP 조회 도구는 7개다: `c4i_get_snapshot`, `c4i_list_entities`, `c4i_summarize_entities`, `c4i_get_entity`, `c4i_get_changes`, `c4i_list_events`, `c4i_list_entity_history`. Agent 내부의 `read_evidence`, `geo_measure`를 합쳐 9개다. 객체 이력은 고정 epoch·sequence 상한 내 snapshot 관측을 페이지 단위로 반환한다.

C4I 도구 설명과 입력 schema는 MCP 서버가 소유한다. 플랫폼은 run 시작 시 `tools/list`의 전체 페이지를 받아 허용된 정의를 native 함수 형식으로 변환하고 해당 run 동안 고정한다. 플랫폼에 C4I 도구 정의를 별도 복사하지 않는다. 발견 실패 시 조회 도구를 노출하지 않고 한계를 전달하며 일반 설명은 계속 답할 수 있다.

배경 지도는 OpenFreeMap/OpenStreetMap 온라인 타일이다. 장애 시 연결 상태를 표시하고 로컬 객체·좌표·목록을 유지한다. OpenAI 설정 부재나 호출 실패는 명시적으로 표시하며 가짜 분석을 반환하지 않는다.

## 검증

```powershell
uv run python -m playwright install chromium
uv run pytest
uv run ruff check services packages scripts tests
uv run ruff format --check services packages scripts tests
uv run mypy services packages
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend audit
```

일반 테스트는 실제 OpenAI를 호출하지 않는다. 실제 MCP HTTP 서버·브라우저를 사용하고 모델만 테스트 어댑터로 주입한다. UI 테스트에는 선행 빌드와 온라인 지도 접속이 필요하다.

실제 GPT 검증은 `uv run pytest -m live tests/test_openai_live.py -q`로 명시적으로 실행한다. 설정된 모델의 OpenAI API 요금이 발생한다.

60초 규모 검증은 `uv run pytest -m performance tests/test_scale.py -s -q`로 실행한다. 120개 객체의 원천→플랫폼 전달 지연과 tick의 LLM 미호출을 확인한다. 일반 실행에서는 live·performance 테스트를 제외한다. 기존 집계·거리 회귀는 명시적인 11개 fixture, 접경 지도·페이지/규모 검증은 120개 시나리오를 사용한다.

## 독립 C4I 배포

UI 빌드·복사 후 `uv build --package c4i-contracts`, `uv build --package battlefield-geo`, `uv build --package mock-c4i`로 wheel 세 개를 생성한다. 별도 Python 환경에 이 wheel과 공개 의존성을 설치한 뒤 `mock-c4i`를 실행한다. 최종 실행에는 Node·플랫폼·MCP·OpenAI가 필요 없다. [C4I 안내](./services/mock-c4i/README.md)를 참고한다.

선택적 `C4I_READ_TOKEN`, `C4I_CONTROL_TOKEN`, `MCP_TOKEN`은 `.env.example`에 설명되어 있다. C4I UI의 우측 연결 설정에서 조회·제어 토큰을 입력할 수 있고 해당 탭의 sessionStorage에만 보관한다. 서버 간 조회 토큰을 일치시킨다. 모든 서버는 기본 localhost 바인딩이다.

## 문서와 SDD

[PRD](./docs/PRD.md) · [아키텍처](./docs/ARCHITECTURE.md) · [Agent 설계](./docs/AGENT_DESIGN.md) · [UI 가이드](./docs/UI_GUIDE.md) · [구현 계획](./docs/IMPLEMENTATION_PLAN.md) · [검증 보고서](./docs/IMPLEMENTATION_REPORT.md) · [진행 단계](./docs/STEP.md)

Review는 사용자가 수행하며 Review 완료 후 확정된 내용을 명세에 Reflect한다.
