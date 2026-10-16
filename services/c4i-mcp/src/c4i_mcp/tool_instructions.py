"""C4I tool descriptions owned by this MCP service and published through tools/list."""

FILTER_HELP = (
    "filter는 kind(tank/naval_vessel/armored_vehicle/support_vehicle/uav/unknown), "
    "affiliation(friendly/hostile/unknown), availability(available/unavailable/unknown), "
    "status(active/inactive/unknown), maintenanceStatus(serviceable/maintenance/unknown), "
    "unitId, zoneId, bbox([서경도,남위도,동경도,북위도])를 조합한다. null은 조건 생략이다. "
    "가용성·정비·운용 상태는 독립적이며 이동 여부로 가용성을 추정하지 않는다. "
)

C4I_TOOL_DESCRIPTIONS = {
    "c4i_get_snapshot": (
        "용도: 모의 C4I 조회의 기준 시점을 확보한다. 입력 snapshotId=null이면 최신, 지정하면 과거 시점이다. "
        "반환: snapshotId, epochId, sequence, sourceTime, previousSnapshotId, entityCount 등 메타데이터이며 객체 목록은 없다. "
        "Agent는 run의 첫 조회에서 시점을 고정하고 이후 같은 snapshotId를 사용한다. 이벤트 실행은 제공된 기준 시점을 유지한다. "
        "오류: 없는 snapshot. 같은 run에서 다른 시점으로 교체하지 않는다."
    ),
    "c4i_list_entities": (
        "용도: 모의 객체 목록·좌표·가용성·속성 조회. 선행: 기준 snapshot 확보. 입력 snapshotId는 고정 시점. "
        + FILTER_HELP
        + "limit=1..100(기본100), cursor=0부터 시작하는 오프셋. 반환 items, matchedCount(모든 페이지 전체 일치 수), "
        "nextCursor, snapshotId, sourceTime. nextCursor가 있으면 필요한 페이지를 추가 조회한다. "
        "거리 비교에는 대상과 후보의 좌표를 같은 목록 근거에 확보한다. 필터가 대상을 제외하지 않도록 주의한다. "
        "오류: 잘못된 필터·snapshot. 미등록 객체를 추정해 채우지 않는다."
    ),
    "c4i_summarize_entities": (
        "용도: 수량 질문·그룹별 집계. 선행: 기준 snapshot 확보. 입력 snapshotId와 filter. "
        + FILTER_HELP
        + "groupBy는 kind/affiliation/availability/status/maintenanceStatus/unitId/zoneId 중 필드 목록, null은 그룹 없음. "
        "반환 matchedCount(전체 일치 수), groups(그룹 키와 count), countUnit=entity, snapshotId, sourceTime. "
        "목록 페이지 길이를 총수로 세지 말고 이 집계를 사용한다. 좌표 목록은 반환하지 않는다. 오류: 잘못된 그룹 필드."
    ),
    "c4i_get_entity": (
        "용도: 특정 모의 객체 상세 확인. 선행: 기준 snapshot 확보. 입력 snapshotId, entityId(정확한 원천 ID). "
        "반환 entity와 snapshotId/sourceTime. 위치는 WGS84 경위도, 속도는 동/북 방향 m/s. "
        "오류: 객체 또는 snapshot 없음. 이 반환 형식은 geo_measure의 items 목록 형식이 아니므로 거리 계산에는 list를 사용한다."
    ),
    "c4i_get_changes": (
        "용도: 두 모의 시점의 객체 상태·위치 변화 비교. 입력 fromSnapshotId는 과거, toSnapshotId는 run의 고정 시점. "
        "두 snapshot은 같은 epoch여야 한다. 이전 시점 ID는 snapshot의 previousSnapshotId 등 원천 근거로 확보한다. "
        "반환 items의 entityId/before/after, snapshotId, sourceTime. 변화 없음은 빈 목록이다. "
        "오류: 없는 snapshot·서로 다른 epoch. 관측 변화와 원인에 관한 추론을 구분한다."
    ),
    "c4i_list_events": (
        "용도: 모의 C4I 원천 이벤트 확인. 입력 epochId는 고정 snapshot의 epoch, after는 제외할 시작 sequence(최초0), "
        "throughSequence는 포함 상한(run의 sequence 이하), limit=1..100. 반환 items의 eventId/type/sequence/시각/payload. "
        "snapshot 본문은 제외된다. 페이지가 limit에 도달하면 마지막 sequence를 after로 사용한다. "
        "오류: 만료 epoch/cursor·run 이후 조회. 단일 객체의 시점별 위치·상태는 이력 도구를 사용한다."
    ),
    "c4i_list_entity_history": (
        "용도: 한 모의 객체의 시점별 위치·상태·정비 이력 확인. 입력 entityId, epochId, after(제외·최초0), "
        "throughSequence(포함·고정 snapshot의 sequence 이하), limit=1..100. 선행: 기준 snapshot 확보. "
        "반환 items(entity, sequence, snapshotId, sourceTime, eventType), nextAfter. "
        "limit은 스캔할 원천 snapshot 수이며 객체 미등장 시 items는 비어도 nextAfter가 있을 수 있다. "
        "nextAfter가 null일 때까지 필요한 페이지를 조회한다. 동일한 상태도 각 관측 시점에 나타난다. "
        "빈 이력은 해당 범위에 객체 기록이 없다는 뜻이다. 오류: 만료 epoch/cursor·역전 범위·미래 조회."
    ),
}
