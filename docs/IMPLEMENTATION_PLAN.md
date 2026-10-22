# 구현 계획 — Agent 실행 로그와 핵심 로직 주석

상태: **Reflect 반영 완료 · 다음 Implement 지시 대기** (2026-10-22).
입력은 [REVIEW](./REVIEW.md)의 최신 두 항목인 “에이전트 실행 기록 로그 파일 남기게 하기(알아보기 쉽게)”, “코드 중요한 부분은 주석(핵심 로직)”이다. 이번 Reflect에서는 이 PLAN만 수정한다. STEP/AGENTS와 다른 spec·코드·테스트·REVIEW는 수정하지 않는다. 단계 표시는 docs/STEP.md를 기준으로 읽되 이번 Reflect 수행 근거는 사용자의 명시적 지시다.

완료한 C0~C7과 Review 중 EX-01 반복 표시 수정은 [구현 보고서](./IMPLEMENTATION_REPORT.md)에 보존한다. 기존 완료 계획을 새 작업 목록에 누적하지 않는다.

## 1. 목표와 현재 구현

사용자가 파일 하나를 열어 한 Agent 실행의 흐름과 결과를 이해할 수 있게 하고, 개발자가 핵심 코드의 설계 이유와 지켜야 할 경계를 파악할 수 있게 한다.

| 확인한 현재 코드 | 다음 변경 |
| --- | --- |
| agent/loop.py는 iterations/toolCalls/evidence/result를 만들고 on_progress로 상태를 전달 | 모델·도구의 시작/종료를 구분한 실행 이벤트를 파일 로그로 전달 |
| runtime.py와 multi_runtime.py는 loop 상태를 SQLite에 저장; DomainRuntime은 MultiRuntime을 재사용 | 기존 DB/UI trace를 유지하며 실행 시작부터 준비 실패·종료까지 파일 기록을 연결 |
| 현재 실행 파일 로그의 경로·형식·출력 제한이 정의되어 있지 않음 | 실행별 UTF-8 로그와 최소 설정·요약 형식 정의 |
| ON/OFF, snapshot, evidence, Graph 불변성에 중요한 방어 코드가 있음 | 해당 경계를 둔 이유와 실패 시 동작을 가까운 주석으로 설명 |

기존 Python 단일 동적 Agent와 native tool calling/MCP discovery를 유지한다. 로그를 위해 별도 Agent·workflow·관측 플랫폼을 추가하지 않는다. 기록 대상은 공개 가능한 요청·응답과 실행 메타데이터이며 모델의 비공개 사고 과정은 아니다.

## 2. 실행 로그 계약

### 파일·설정

- 기본 경로: `var/logs/agent/<runId>.log`. `AGENT_LOG_DIR`로 루트 경로를 설정할 수 있게 한다. 비활성화 설정 `AGENT_LOG_ENABLED=false`도 제공하고 기본은 활성화한다.
- Python 표준 라이브러리로 구현한다. 실행별 파일을 사용해 OFF/ON·여러 대화의 로그가 섞이지 않게 하고 UTF-8로 한글을 보존한다.
- 파일명은 서버가 발급한 runId로 제한한다. 질문·도구 인자·외부 입력을 파일 경로로 사용하지 않는다.
- 동일 run의 기존 파일을 덮어쓰지 않는다. 재시작/복구 이력은 구분되는 이벤트로 추가하며 새 모델 실행처럼 표시하지 않는다.
- 중요한 이벤트마다 기록을 flush하여 실행 중에도 읽을 수 있게 한다. 자동 삭제/retention 서비스는 추가하지 않고 로컬 생성 로그는 Git 추적 대상에서 제외한다.

### 기록 내용

| 이벤트 | 기록할 정보 |
| --- | --- |
| 실행 시작 | UTC 시각, runId, conversationId, comparisonId(있을 때), 질문, trigger, ON/OFF, 요청 모델·예산 |
| 분석 준비 | source snapshot/epoch/기준 시각, 기준보고·T0 참조, ON Graph 버전, 준비 시간·실패 |
| MCP discovery | 서버별 도구 이름·개수, registry hash, 연결/발견 오류 |
| 모델 요청/응답 | 반복 번호, 시작/종료·소요 시간, 반환 상태·responseId·실제 모델·제공된 token usage, 선택한 도구 또는 최종 응답 여부 |
| 도구 호출/결과 | 반복 번호·callId·도구명, 인자, 시작/종료·시간, 성공/실패, evidenceId와 결과 요약 |
| 최종 결과 | 답변·핵심 claims/근거 참조, 한계, 최종 status, 모델/도구 횟수, usage 합계·집계 가능 여부, 전체 실행 시간 |
| 비정상 종료 | 준비 실패, provider 오류, 도구 실패, 출력 검증 실패, deadline/예산/반복 중단, 취소·재시작 중단의 구별 |

- 각 이벤트는 짧은 한글 설명과 일정한 필드 순서를 사용한다. 객체/배열은 들여쓰기하고, 긴 인자·결과·질문·답변 블록은 기본 8,000자 이내로 제한하며 생략 여부와 원래 길이를 표시한다.
- 도구 결과 요약에는 가능한 경우 건수·완결성·상태·오류와 evidenceId를 남긴다. 전체 원천 레코드와 같은 누적 state를 매 이벤트마다 반복 출력하지 않는다. 전체 상세의 기준 저장소는 기존 DB/UI trace다.
- 실행에서 실제 관측한 값만 기록한다. 모델 시작 전 “선택 이유”를 생성하거나 provider가 주지 않은 토큰/종료 정보를 추정하지 않는다. usage가 없으면 미제공/부분 합계로 구분하고 비용을 임의 산출하지 않는다.
- API 키·Authorization·비밀번호·토큰·환경변수 전체와 SDK 원본 요청/비공개 reasoning은 출력하지 않는다. 중첩 인자·결과·오류도 민감 필드 및 설정된 비밀값을 마스킹한 뒤 길이를 제한한다.

### 기존 실행과 연결

- AgentLoop에는 필요한 최소 실행 이벤트 callback을 선택 인자로 추가하는 방식을 우선 검토한다. 기존 on_progress의 DB/SSE 동작을 파일 쓰기로 대체하지 않는다.
- Runtime이 writer 생명주기를 소유한다. loop에 들어가기 전의 snapshot/Graph/MCP 준비 오류도 남기고, 정상·실패·취소 시 파일을 정리한다. legacy와 heterogeneous/v3가 같은 이벤트 계약을 사용한다.
- 누적 상태의 on_progress 호출을 그대로 덤프하지 않는다. 도구 시작·완료와 모델 반복 이벤트를 식별해 중복을 방지하고, terminal summary는 실행당 한 번 기록한다.
- 로그 I/O 실패는 Agent 결과·DB 상태를 바꾸지 않게 처리한다. 대신 runId와 실패 종류를 stderr에 경고하고 해당 실행의 파일 기록 실패를 숨기지 않는다. 오류 경고에 비밀값이나 원본 payload를 넣지 않는다.
- 비동기 loop에서 파일 쓰기 때문에 응답을 장시간 막지 않도록 단순한 executor/thread offload 등을 사용하고, 재귀 로깅이나 무제한 task/queue를 만들지 않는다.

## 3. 핵심 로직 주석 범위

주석은 “무슨 코드를 쓰는가”보다 “왜 이 조건과 경계가 필요한가”를 설명한다. 중요한 함수에는 입력·출력·불변 조건을 짧은 docstring으로 보완한다.

| 대상 | 설명할 핵심 |
| --- | --- |
| agent/loop.py | assistant call/output의 컨텍스트 누적, 현재-run 근거 검증, 한 번의 출력 교정, 반복·예산·deadline 종료, progress/terminal 상태 책임 |
| agent/domain_tools.py 및 multi_tools.py | OFF capability 차단, 원천 snapshot 주입, 다른 run 근거 거부, 원천/참조 페이지 완결성, scope 전체 조회, 지원 자산 중복 제거·분류/정책 분리 |
| domain_runtime.py / multi_runtime.py / multi_repository.py | 표시 데이터와 Agent evidence의 구별, 동일 조건 비교와 대화 격리, 기준보고/T0, 정책이 다른 과거 대화 거부, tick과 분석 사건의 구분 |
| semantic_api/fabric.py | core와 의미 준비의 분리, 부분 원천 coverage, 정지/이동 중 capture 기준과 준비 시간의 차이 |
| ontology/domain.py / semantic_core/domain.py / graph_builder/worker.py | 명시적 매핑·동일성 근거, 문서 version/hash 검증, live 상태 제외, 안정 hash·catalog hash, 검증 후 READY 공개·sourceScope 격리 |
| NativeSourceApp.tsx | 원천 자체 ID와 근거 문서 ID의 차이, system/resource별 React key로 항목 충돌을 방지하는 이유 |
| 새 로그 writer와 연결부 | 마스킹→출력 제한 순서, 실행별 격리, I/O 실패 격리·종료 처리 |

단순 대입·반복문마다 주석을 달거나 주석 작업을 이유로 광범위한 구조 변경을 하지 않는다. 실행과 맞지 않는 과거 설명은 수정하고, 문서화 과정에서 발견한 별도 기능 결함은 구현 보고서에 구분해 기록한다.

## 4. 구현 순서와 테스트

### R1. 로그 계약의 실패 테스트 작성

- [ ] fake provider/runner를 사용해 한글 질문→discovery→모델→도구→결과 순서와 필수 식별자가 실제 로그 파일에 남는 실패 테스트를 작성한다.
- [ ] OFF/ON 두 run과 여러 대화에서 파일/이벤트가 섞이지 않고, 다른 run의 evidence를 자기 실행의 근거로 기록하지 않는지 검증한다.
- [ ] 도구 실패, provider 실패, 출력 검증 실패, deadline/예산 종료, loop 전 준비 실패와 취소 시 종료 기록·정리가 남는지 검증한다.
- [ ] 중첩 비밀 필드·오류 문자열의 마스킹, 긴 payload의 생략 표기, usage 미제공, writer I/O 실패에도 분석/DB 상태가 유지되는 반례를 작성한다.
- [ ] 파일명/디렉터리 정책·설정 비활성화·기존 파일 보존·terminal 중복 방지를 검사한다. 테스트는 tmp_path를 사용하며 사용자 실행 로그를 덮어쓰지 않는다.

### R2. 파일 기록과 Runtime 연결

- [ ] 최소 writer/formatter와 설정을 구현하고 R1을 통과시킨다.
- [ ] 공통 loop와 legacy/heterogeneous Runtime에 연결한다. 실제 MCP discovery/call을 포함하는 기존 v3 통합 테스트 한 곳에서 파일의 도구·근거 ID와 DB trace의 일치를 검증한다.
- [ ] 도구별 이벤트가 기존 모델 입력, tool schema, ON/OFF 허용 도구, 최종 결과와 대화 저장을 바꾸지 않는지 확인한다.

### R3. 핵심 주석 보완

- [ ] 3절 대상 파일의 실제 흐름을 읽고 필요한 지점에 주석/docstring을 추가한다.
- [ ] 주석의 조건·설정·상태명이 실제 구현과 일치하는지 diff로 검토한다. 주석 개수를 세는 테스트는 작성하지 않는다.

### R4. 회귀·문서·인계

- [ ] 관련 loop/Agent·대화/정책·ON/OFF·snapshot/evidence/비교 회귀와 새 로그 테스트를 실행한다.
- [ ] 실제 MCP/Neo4j 통합에서 로그의 식별자·최종 상태를 확인한다. 구조 변경 없이 로그만 추가하는 범위라면 실제 GPT 유료 호출의 반복을 필수로 삼지 않는다. 필요해 실행한 경우 횟수·usage·결과를 별도 기록한다.
- [ ] Ruff check/format·mypy를 확인한다. 프론트 변경이 주석뿐이면 기존 빌드/브라우저 검증을 불필요하게 반복하지 않고, 실행 코드 변경이 있으면 해당 TypeScript/UI 검증을 수행한다.
- [ ] UTF-8 로그 파일을 직접 열어 호출 순서·오류·근거·최종 답변이 읽기 쉬운지 확인한다. stdout 요약만으로 가독성 확인을 대체하지 않는다.
- [ ] Implement에서 README에 경로/설정/예시/생략·실패 처리 안내를 추가하고, 영향받은 AGENT_DESIGN/ARCHITECTURE/ADR 등을 필요한 범위에서 정합화한다.
- [ ] 실제 명령·결과·제약과 샘플 로그 경로를 IMPLEMENTATION_REPORT에 남긴다. 샘플은 합성 fixture로 만들고 비밀값이 없는지 확인한다.
- [ ] 구현 완료 시에만 STEP.md와 AGENTS.md를 함께 갱신해 Human Review로 인계한다. 사용자 REVIEW 작성·완료 처리나 다음 Reflect는 대신 수행하지 않는다.

## 5. 완료 기준

1. 사용자가 runId로 파일을 찾아 질문→조회·계산→답변/실패 흐름을 따라갈 수 있다.
2. 현재 모드·고정 시점·Graph·도구·근거와 로그가 일치하며 기존 DB/UI trace도 유지된다.
3. 정상·오류·취소 실행의 이벤트가 실행별로 분리되고 한글·긴 데이터·민감 정보·로그 I/O 실패를 처리한다.
4. 핵심 주석이 실제 코드의 판단 이유와 불변 조건을 설명하며 현재 실행 동작과 일치한다.
5. 새 테스트와 관련 회귀가 통과하고 실제 결과/사용법을 보고서·관련 spec에 기록한 뒤 사용자 검토를 기다린다.
