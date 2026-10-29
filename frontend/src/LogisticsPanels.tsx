import { useEffect, useRef, useState } from 'react';
import KnowledgeDocuments from './KnowledgeDocuments';
import { formatTime } from './time';
import { NativeRecord, resourceNames } from './NativePresentation';
export type DemoAPI = (path: string, body?: unknown) => Promise<any>;
const resources: Record<string, string[]> = {
  atcis: ['equipment', 'units', 'reports', 'activities', 'relations'],
  knccs: ['own-forces', 'transports', 'contacts', 'messages', 'associations'],
  logistics: [
    'assets',
    'work-orders',
    'parts',
    'inventory',
    'reservations',
    'supply-requests',
    'cargo',
  ],
};
export const logisticsScenarios = [
  ['L0', '부품 P-08의 창고별 재고와 예약 수량을 보여줘.'],
  [
    'L1',
    'L-T02의 기본 정보·정비 작업·필요 부품·수송 현황과 각각의 기준 시각 및 연결 근거를 보여줘.',
  ],
  [
    'L2',
    'B11 예하 운용 제한 전차 중 재고와 해상 입고 예정 부품을 고려하면 2026-10-21 18:00 UTC까지 복구 조건을 충족하는 장비는?',
  ],
  [
    'L3',
    '수송편 N-21의 입항과 인도가 6시간 지연되면 어떤 부대의 장비 복구 일정이 영향을 받는가? 원천을 변경하지 않고 가정으로 분석해줘.',
  ],
  [
    'L4',
    '수송 중 부품과 관련된 정비 작업 중 이미 재고가 확보된 것과 해당 입고에 의존하는 것을 구분해줘.',
  ],
  ['L5', '복구 전망을 확정할 수 없는 장비와 추가로 필요한 원천 기록은 무엇인가?'],
];
export function DemoEntry() {
  return (
    <main className="demo-entry">
      <span>합성 연습 · 세 체계 · v5</span>
      <h1>지식 제공 조건을 선택하세요</h1>
      <p>같은 원천을 탐색하며 지식 제공과 구조화의 차이를 확인합니다.</p>
      <div>
        {[
          ['a', 'A · 원천 데이터', '세 원천의 기록을 직접 조회합니다.'],
          [
            'b',
            'B · 문서 지식',
            '같은 원천과 Fabric 설명 문서(온톨로지 선언 문서 포함)를 조회합니다.',
          ],
          [
            'c',
            'C · 구조화 지식',
            '같은 문서를 온톨로지와 지식그래프로 구조화해, 검증된 연결·규칙·근거를 업무 질의로 활용합니다.',
          ],
        ].map(([path, name, description]) => (
          <a
            key={path}
            href={'/demo/' + path}
            aria-label={name + (path === 'a' ? '로' : '으로') + ' 진입'}
          >
            <h2>{name}</h2>
            <p>{description}</p>
            <b>진입 →</b>
          </a>
        ))}
      </div>
      <a href="/demo/compare">동일 기준 A/B/C 비교로 진입 →</a>
      <small>개별 체험과 고정 snapshot의 공식 비교는 별개입니다.</small>
    </main>
  );
}
export function NativeBrowser({ api, onClose }: { api: DemoAPI; onClose: () => void }) {
  const [system, setSystem] = useState('logistics'),
    [resource, setResource] = useState('assets'),
    [data, setData] = useState<any>(null),
    [error, setError] = useState(''),
    [q, setQ] = useState('');
  useEffect(() => {
    setData(null);
    setError('');
  }, [system, resource]);
  const load = async (next?: string) => {
    try {
      setError('');
      const params = new URLSearchParams();
      if (next) {
        params.set(system === 'knccs' ? 'continuation' : 'offset', next);
        params.set('snapshotId', data.snapshotId);
      }
      setData(await api(`native-records/${system}/${resource}?${params}`));
    } catch (e) {
      setError(String(e));
    }
  };
  const rows = data?.page?.items || data?.page?.payload || [];
  const next = data?.page?.nextOffset ?? data?.page?.header?.continuation;
  return (
    <aside className="demo-overlay" aria-label="원천 기록 탐색">
      <header>
        <h2>원천 기록 탐색</h2>
        <button onClick={onClose} aria-label="원천 탐색 닫기">
          닫기
        </button>
      </header>
      <p>원천 필드와 명시적 참조를 그대로 조회합니다.</p>
      <label>
        체계
        <select
          aria-label="조회 체계"
          value={system}
          onChange={(e) => {
            setSystem(e.target.value);
            setResource(resources[e.target.value][0]);
          }}
        >
          {Object.keys(resources).map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        자원
        <select
          aria-label="원천 자원"
          value={resource}
          onChange={(e) => setResource(e.target.value)}
        >
          {resources[system].map((r) => (
            <option key={r} value={r}>
              {resourceNames[r] || r}
            </option>
          ))}
        </select>
      </label>
      <button onClick={() => void load()}>원천 조회</button>
      <input
        aria-label="현재 페이지 기록 검색"
        placeholder="현재 페이지 검색"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {error && <p role="alert">{error}</p>}
      {data && (
        <p>
          기준 {data.sourceTime || '정보 없음'} · 수신 {data.lastReceivedAt || '정보 없음'} ·
          snapshot {data.snapshotId}
        </p>
      )}
      {rows
        .filter((r: any) => JSON.stringify(r).includes(q))
        .map((r: any, i: number) => (
          <details key={i}>
            <summary>
              {(Object.entries(r).find(([k]) => /Id$|Code$|pennant/.test(k))?.[1] as string) ||
                '기록 ' + i}
            </summary>
            <NativeRecord record={r} />
          </details>
        ))}
      {next != null && <button onClick={() => void load(String(next))}>다음 원천 페이지</button>}
    </aside>
  );
}
export function DocumentsPanel({
  api,
  onClose,
  target = null,
}: {
  api: DemoAPI;
  onClose: () => void;
  target?: { key: string; version: string } | null;
}) {
  return (
    <aside className="demo-overlay" aria-label="Fabric 문서">
      <header>
        <h2>Fabric 문서 지식</h2>
        <button onClick={onClose}>문서 닫기</button>
      </header>
      <KnowledgeDocuments get={api} target={target} />
    </aside>
  );
}
export function ObjectContext({
  api,
  source,
  nativeId,
  recordType,
  onClose,
  onQuestion,
  onDocument,
}: {
  api: DemoAPI;
  source: string;
  nativeId: string;
  recordType: string;
  onClose: () => void;
  onQuestion: () => void;
  onDocument: (key: string, version: string) => void;
}) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  const lastGraph = useRef<{ key: string; version: string } | null>(null);
  useEffect(() => {
    let active = true;
    setData(null);
    setError('');
    const key = source + '/' + recordType + '/' + nativeId;
    void api('objects/detail', {
      systemId: source,
      nativeId,
      recordType,
      ...(lastGraph.current?.key === key ? { graphVersion: lastGraph.current.version } : {}),
    })
      .then((r) => {
        if (active) {
          setData(r);
          lastGraph.current = { key, version: r.graphVersion };
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [api, source, nativeId, recordType, retry]);
  return (
    <aside className="demo-overlay" aria-label="구조화 객체 상세">
      <header>
        <h2>{nativeId} · 연결된 정보</h2>
        <button onClick={onClose}>통합 상세 닫기</button>
      </header>
      <p>검증된 연결과 원천별 현재 정보 · AI 호출 없음</p>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">객체·관계·원천 정보를 조회하는 중…</p>}
      <button onClick={() => setRetry((n) => n + 1)}>상세 새로고침</button>
      {data && (
        <>
          <p role="status">{data.partial ? '일부 정보만 조회되었습니다.' : '원천 조회 완료'}</p>
          {data.stale && (
            <p role="alert">연결 근거와 현재 원천의 기준이 달라 업무 요약을 보류했습니다.</p>
          )}
          {!data.business && (
            <p>
              {(
                {
                  ambiguous: '같은 객체로 연결할 후보가 여러 개입니다.',
                  conflict: '동일성 근거가 서로 충돌합니다.',
                  unresolved: '확정된 동일성 연결이 없습니다.',
                } as Record<string, string>
              )[data.identityStatus] || '확정된 업무 요약이 없습니다.'}{' '}
              연결 상태와 원본 기록을 확인하세요.
            </p>
          )}
          {data.business && (
            <>
              <section aria-label="현재 상태">
                <h3>
                  {data.business.asset.name} · {nativeId}
                </h3>
                <dl>
                  <div>
                    <dt>현재 원천 상태</dt>
                    <dd>{data.business.asset.status}</dd>
                  </div>
                  <div>
                    <dt>소속</dt>
                    <dd>{data.business.asset.unit}</dd>
                  </div>
                  <div>
                    <dt>제약 사항</dt>
                    <dd>{data.business.asset.limitation || '기록 없음'}</dd>
                  </div>
                </dl>
              </section>
              <section aria-label="정비 현황">
                <h3>정비 현황</h3>
                {!data.business.maintenance.length && <p>연결된 정비 작업이 없습니다.</p>}
                {data.business.maintenance.map((w: any) => (
                  <article key={w.id}>
                    <h4>정비 작업 {w.id}</h4>
                    <p>{w.status}</p>
                    <p>
                      정비 소요 시간: {w.durationHours ?? '정보 없음'} h · {w.otherFaults}
                    </p>
                    <p>
                      필요 부품:{' '}
                      {w.requirements
                        .map((q: any) => `${q.partId} · ${q.quantity} ${q.unit || ''}`)
                        .join(', ') || '기록 없음'}
                    </p>
                  </article>
                ))}
              </section>
              <section>
                <h3>관련 부품 재고</h3>
                <p>보유·예약 수량은 특정 작업에 배정 가능한 수량과 다를 수 있습니다.</p>
                {data.business.inventory.map((r: any, i: number) => (
                  <p key={i}>
                    {r.partId} · {r.warehouse} · 보유 {r.onHand ?? '정보 없음'} / 예약{' '}
                    {r.reserved ?? '정보 없음'} {r.unit}
                  </p>
                ))}
                {!data.business.inventory.length && <p>연결된 재고 기록이 없습니다.</p>}
              </section>
              <section>
                <h3>관련 수송</h3>
                {data.business.transport.map((r: any) => (
                  <article key={r.id}>
                    <h4>{r.id}</h4>
                    <p>{r.status}</p>
                    <p>
                      입항 예정 {formatTime(r.arrivalAt)}
                      <br />
                      인도 예정 {formatTime(r.deliveryAt)}
                    </p>
                  </article>
                ))}
                {!data.business.transport.length && <p>연결된 수송 기록이 없습니다.</p>}
              </section>
              <section>
                <h3>정보 시점</h3>
                {data.business.sourceTimes.map((r: any, i: number) => (
                  <p key={i}>
                    {r.source.toUpperCase()} · {r.nativeId || '원천 기록'}
                    <br />
                    데이터 기준 {formatTime(r.sourceTime)}
                    <br />
                    기록 갱신 {formatTime(r.recordUpdatedAt)}
                    <br />
                    최근 수신 {formatTime(r.lastReceivedAt)}
                  </p>
                ))}
                <p>이번 조회 완료 {formatTime(data.business.queriedAt)}</p>
              </section>
            </>
          )}
          <details>
            <summary>원천 식별자·버전·수집 진단</summary>
            <p>동일성: {data.identityStatus}</p>
            <p>Graph {data.graphVersion}</p>
            <pre>
              {JSON.stringify({ coverage: data.coverage, metadata: data.metadata }, null, 2)}
            </pre>
          </details>
          <details>
            <summary>원본 기록 ({data.records.length})</summary>
            {data.records.map((r: any, i: number) => (
              <section key={i}>
                <h3>
                  {r.systemId} · {r.recordType} · {r.nativeId}
                </h3>
                <small>
                  기준: {r.sourceTime || '정보 없음'}
                  <br />
                  상태 변경: {r.recordUpdatedAt || '정보 없음'}
                  <br />
                  최종 수신: {r.lastReceivedAt || '정보 없음'}
                </small>
                <dl>
                  {Object.entries(r.record)
                    .filter(([, v]) => v === null || typeof v !== 'object')
                    .map(([k, v]) => (
                      <div key={k}>
                        <dt>
                          {(
                            {
                              assetId: '군수 자산',
                              equipmentId: '원천 장비',
                              workOrderId: '정비 작업',
                              status: '원천 상태',
                              partId: '부품',
                              onHand: '보유 수량',
                              reserved: '예약 수량',
                              laborHours: '정비 소요 시간(h)',
                              arrivalAt: '입항 예정',
                              deliveryAt: '인도 예정',
                              transportId: '수송편',
                              quantity: '수량',
                              unit: '단위',
                              otherFaults: '다른 미해결 고장',
                              ownerCode: '소속 코드',
                            } as Record<string, string>
                          )[k] || k}
                        </dt>
                        <dd>{v === null ? '정보 없음' : String(v)}</dd>
                      </div>
                    ))}
                </dl>
                <details>
                  <summary>전체 원천 기록</summary>
                  <pre>{JSON.stringify(r.record, null, 2)}</pre>
                </details>
              </section>
            ))}
          </details>
          <details>
            <summary>연결 규칙·근거·버전 ({data.links.length})</summary>
            {data.links.map((link: any) => (
              <section key={link.evidenceId}>
                <p>
                  {link.start} → {link.kind} → {link.end}
                </p>
                <small>
                  {link.ruleId || link.provenanceKind} · {link.ruleVersion || link.adapterVersion}
                </small>
                {(link.documentRefs || [])
                  .filter((d: any) => d.documentKey && d.knowledgeSetVersion)
                  .map((d: any) => (
                    <button
                      key={d.documentKey}
                      onClick={() => onDocument(d.documentKey, d.knowledgeSetVersion)}
                    >
                      근거 문서 {d.documentKey}
                    </button>
                  ))}
              </section>
            ))}
            <pre>
              {JSON.stringify(
                {
                  knowledgeSetVersion: data.knowledgeSetVersion,
                  adapterVersion: data.adapterVersion,
                  links: data.links,
                },
                null,
                2,
              )}
            </pre>
          </details>
          <button onClick={onQuestion}>이 객체에 질문 작성</button>
        </>
      )}
    </aside>
  );
}
