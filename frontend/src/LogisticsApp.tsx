import { useEffect, useState } from 'react';
import './Domain.css';
import { NativeRecord, nativeValue, resourceNames } from './NativePresentation';
const resources = [
  'assets',
  'work-orders',
  'parts',
  'inventory',
  'reservations',
  'supply-requests',
  'cargo',
];
export default function LogisticsApp() {
  const [snapshot, setSnapshot] = useState<any>(null),
    [resource, setResource] = useState('assets'),
    [selected, setSelected] = useState<any>(null),
    [read, setRead] = useState(''),
    [control, setControl] = useState(''),
    [error, setError] = useState(''),
    [status, setStatus] = useState('');
  const request = async (path: string, body?: unknown, method = 'POST') => {
    const r = await fetch('/api/v1/' + path, {
      ...(body || method === 'POST' ? { method } : {}),
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + (method === 'GET' ? read : control),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!r.ok) throw new Error(r.status + ': ' + (await r.text()));
    return r.json();
  };
  const refresh = async () => {
    try {
      const fresh = await request('snapshot', undefined, 'GET');
      setSnapshot(fresh);
      setSelected((current: any) => {
        if (!current) return null;
        const identity = Object.entries(current).find(([key]) => /Id$/.test(key));
        if (!identity) return null;
        return (
          (Object.values(fresh.records).flat() as any[]).find(
            (row) => row[identity[0]] === identity[1],
          ) || null
        );
      });
      setError('');
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => clearInterval(timer);
  }, [read]);
  const mutate = async (path: string, body?: unknown, method = 'POST') => {
    try {
      await request(path, body, method);
      await refresh();
      setStatus('갱신 완료');
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <div className="domain-shell">
      <header>
        <div>
          <small>SYNTHETIC LOGISTICS · NATIVE RECORDS</small>
          <h1>Mock LOGISTICS</h1>
          <span>
            {snapshot?.datasetId} · {snapshot?.sourceTime}
          </span>
        </div>
        <span>군수 원천 · 독립 실행</span>
      </header>
      <div className="domain-credentials">
        <label>
          읽기 토큰
          <input type="password" value={read} onChange={(e) => setRead(e.target.value)} />
        </label>
        <label>
          제어 토큰
          <input type="password" value={control} onChange={(e) => setControl(e.target.value)} />
        </label>
        <button onClick={() => void mutate('simulation/step')}>1초 진행</button>
        <button onClick={() => void mutate('simulation/start')}>시작</button>
        <button onClick={() => void mutate('simulation/pause')}>정지</button>
        <span role="status">{status}</span>
      </div>
      {error && <p role="alert">{error}</p>}
      <main className="fabric-grid">
        <aside>
          <h2>원천 자원</h2>
          {resources.map((r) => (
            <button
              className="domain-record"
              key={r}
              aria-pressed={resource === r}
              onClick={() => {
                setResource(r);
                setSelected(null);
              }}
            >
              {resourceNames[r] || r}
            </button>
          ))}
        </aside>
        <section>
          <h2>{resourceNames[resource] || resource}</h2>
          <p>원천 ID·업무 기록을 표시합니다. 다른 체계의 해석·Graph·LLM 연결 없이 동작합니다.</p>
          {(snapshot?.records[resource] || []).map((r: any, i: number) => (
            <button className="domain-record" key={i} onClick={() => setSelected(r)}>
              {Object.entries(r).find(([k]) => /Id$/.test(k))?.[1] as string}
            </button>
          ))}
          {selected && (
            <article>
              <h3>원천 레코드</h3>
              <NativeRecord record={selected} />
              {resource === 'work-orders' && (
                <label>
                  정비 상태
                  <select
                    aria-label="정비 상태 변경"
                    defaultValue={selected.status}
                    key={selected.workOrderId}
                    onChange={(e) =>
                      void mutate(
                        'work-orders/' + selected.workOrderId,
                        { status: e.target.value },
                        'PATCH',
                      )
                    }
                  >
                    {['WAIT_PART', 'IN_PROGRESS', 'DONE', 'UNKNOWN'].map((v) => (
                      <option key={v} value={v}>
                        {nativeValue('status', v)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </article>
          )}
        </section>
      </main>
    </div>
  );
}
