# Agentic Battlefield Intelligence Platform

Python 기반 전장의 분석형 AI 플랫폼 PoC. 독립 Mock C4I → MCP Server → 단일 동적 분석 Agent로 연결한다. 두 UI는 React·TypeScript 정적 앱이며 Python 서버가 제공한다.

## 빠른 시작

Python 3.12와 uv가 필요하다. Node 20.19+/22.12+는 UI 빌드 시에만 사용한다.

```powershell
uv sync --all-packages
uv run python scripts/export_contracts.py
npm --prefix frontend ci
npm --prefix frontend run build
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
npm --prefix frontend run lint
npm --prefix frontend audit
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
