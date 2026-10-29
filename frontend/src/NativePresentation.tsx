// Source-local presentation only. This dictionary never enters Agent requests.
export const resourceNames: Record<string, string> = {
  assets: '군수 자산',
  'work-orders': '정비 작업',
  parts: '부품',
  inventory: '창고 재고',
  reservations: '예약 재고',
  'supply-requests': '보급 요청',
  cargo: '화물',
  equipment: '장비',
  units: '편제',
  reports: '보고',
  activities: '업무 활동',
  relations: '명시적 참조',
  'own-forces': '등록 함정',
  transports: '수송',
  contacts: '접촉 관측',
  messages: '전문',
  associations: '연관 기록',
};
const fields: Record<string, string> = {
  assetId: '군수 자산',
  equipmentId: '장비',
  workOrderId: '정비 작업',
  partId: '부품',
  warehouseId: '창고',
  inventoryId: '재고 기록',
  status: '원천 상태',
  name: '명칭',
  designation: '명칭',
  classCode: '원천 유형',
  maintenanceCode: '정비 상태',
  limitation: '제약 사항',
  ownerCode: '소속',
  formationRef: '편제 참조',
  pennant: '함정 번호',
  engineering: '기관 상태',
  mission: '임무 상태',
  onHand: '보유 수량',
  reserved: '예약 수량',
  laborHours: '정비 소요 시간(h)',
  otherFaults: '추가 고장',
  quantity: '수량',
  unit: '단위',
  arrivalAt: '입항 예정(UTC)',
  deliveryAt: '인도 예정(UTC)',
  updatedAt: '기록 갱신(UTC)',
  transportId: '수송편',
  cargoId: '화물',
  requestId: '보급 요청',
  externalSystem: '외부 체계',
  externalId: '외부 식별자',
  text: '내용',
  domain: '관측 영역',
  hullClass: '선체 유형',
};
const codes: Record<string, Record<string, string>> = {
  maintenanceCode: { FMC: '가용', PMC: '운용 제한', NMC: '운용 불가', UNK: '미확인' },
  mission: { GO: '임무 가능', HOLD: '임무 보류', UNKNOWN: '미확인' },
  engineering: { UP: '기관 정상', DOWN: '기관 고장', UNKNOWN: '미확인' },
  classCode: { TK: '전차', AAV: '장갑차', LOG: '지원 차량', UAS: '무인기' },
  status: {
    WAIT_PART: '부품 대기',
    IN_PROGRESS: '정비 중',
    DONE: '정비 완료',
    IN_TRANSIT: '수송 중',
    DELIVERED: '인도 완료',
    EN_ROUTE: '항해 중',
    ARRIVED: '입항',
    UNKNOWN: '미확인',
  },
};
export function nativeValue(field: string, value: unknown): string {
  if (value == null) return '정보 없음';
  if (codes[field]) return codes[field][String(value)] || '미확인';
  return typeof value === 'boolean' ? (value ? '있음' : '없음') : String(value);
}
export function NativeRecord({ record }: { record: Record<string, unknown> }) {
  return (
    <>
      <dl>
        {Object.entries(record)
          .filter(([k, v]) => fields[k] && (v == null || typeof v !== 'object'))
          .map(([k, v]) => (
            <div key={k}>
              <dt>{fields[k]}</dt>
              <dd>{nativeValue(k, v)}</dd>
            </div>
          ))}
      </dl>
      <details>
        <summary>전체 원본 기록·식별자</summary>
        <pre>{JSON.stringify(record, null, 2)}</pre>
      </details>
    </>
  );
}
