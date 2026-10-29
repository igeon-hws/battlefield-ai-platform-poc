# IMPLEMENTATION_PLAN

## 현재: 승인된 다음 Implement 없음

Semantic 조회 정확도와 Agent 도구 사용 효율 계획의 구현·무과금 검증은 2026-10-28 완료했고 결과는 [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md)에 있다. 다음 Human Review 이후 사용자의 Reflect 지시로 새 계획을 둔다.

검토 시 결정이 필요한 남은 항목(승인 전 착수하지 않음):

- 실제 모델 전후 측정: 동일 질문·스냅샷·예산에서 호출 수·중복률·반환 토큰·관계 조회 정답·최종 답변 유무·응답 시간. 유료 실행이므로 별도 승인 필요. 프롬프트 digest와 L3 gold가 바뀌어 이전 9-run과 같은 기준의 반복 비교가 아님을 함께 기록한다.
- 기존 실패 `test_graph_sync.py::test_builder_queues_and_restart_recovery_are_scoped_to_source_endpoints`: 테스트 대체 함수와 `ensure_build(body, knowledge)` 시그니처 불일치. 이번 범위 밖으로 남겼다.
