import { useEffect, useState } from 'react';
import { SituationMap, type EntityView } from './App';
import { formatTime } from './time';
import './style.css';

type Situation = {
  snapshotId: string;
  epochId: string;
  running: boolean;
  sourceTime: string;
  datasetId: string;
  entities: EntityView[];
};

export default function SourceApp({ system }: { system: 'atcis' | 'knccs' }) {
  const [situation, setSituation] = useState<Situation | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [availability, setAvailability] = useState('available');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [view, setView] = useState({
    center: [126.5, 37.8] as [number, number],
    zoom: 7,
    bearing: 0,
  });
  const [readToken, setReadToken] = useState(sessionStorage.getItem(`${system}.readToken`) || '');
  const [controlToken, setControlToken] = useState(
    sessionStorage.getItem(`${system}.controlToken`) || '',
  );
  const headers = (control = false) => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${control ? controlToken : readToken}`,
  });
  const load = async () => {
    try {
      const response = await fetch('/api/v1/situation', { headers: headers() });
      if (!response.ok) throw new Error(`원천 조회 실패 (${response.status})`);
      setSituation(await response.json());
      setError('');
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    let active = true;
    const refresh = () => {
      if (active) void load();
    };
    refresh();
    const timer = setInterval(refresh, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [readToken]);
  const action = async (path: string, body?: object, method = 'POST') => {
    try {
      setMessage('');
      const response = await fetch('/api/v1/' + path, {
        method,
        headers: headers(true),
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) throw new Error(`변경 실패 (${response.status})`);
      setMessage('변경 저장됨');
      await load();
    } catch (e) {
      setError(String(e));
    }
  };
  const entity = situation?.entities.find((e) => e.entityId === selected);
  const select = (id: string) => {
    setSelected(id);
    const item = situation?.entities.find((e) => e.entityId === id);
    setAvailability(item?.availability || 'unknown');
    setMessage('');
  };
  const patch =
    system === 'atcis'
      ? { readyCode: { available: 'R', unavailable: 'N', unknown: 'U' }[availability] }
      : {
          serviceability: { available: 'READY', unavailable: 'NOT_READY', unknown: 'UNCONFIRMED' }[
            availability
          ],
        };
  return (
    <div className="source-shell">
      <header>
        <div>
          <h1>Mock {system.toUpperCase()}</h1>
          <span>합성 모의 {system === 'atcis' ? '지상' : '해상'} 체계 · 독립 원천 · {situation?.datasetId || '연결 중'}</span>
        </div>
        <div>
          <span role="status">
            {situation?.running ? '시뮬레이션 실행 중' : '시뮬레이션 일시 정지'}
          </span>
          <button
            onClick={() => void action(`simulation/${situation?.running ? 'pause' : 'start'}`)}
          >
            {situation?.running ? '일시 정지' : '이동 시작'}
          </button>
        </div>
      </header>
      <section className="source-status">
        <label>
          읽기 토큰{' '}
          <input
            type="password"
            value={readToken}
            onChange={(e) => {
              setReadToken(e.target.value);
              sessionStorage.setItem(`${system}.readToken`, e.target.value);
            }}
          />
        </label>
        <label>
          제어 토큰{' '}
          <input
            type="password"
            value={controlToken}
            onChange={(e) => {
              setControlToken(e.target.value);
              sessionStorage.setItem(`${system}.controlToken`, e.target.value);
            }}
          />
        </label>
        <span>{situation?.sourceTime ? formatTime(situation.sourceTime) : ''}</span>
      </section>
      {error && <p role="alert">{error}</p>}
      <main>
        <aside>
          <h2>원천 객체 {situation?.entities.length || 0}</h2>
          {situation?.entities.map((e) => (
            <button
              key={e.entityId}
              className={selected === e.entityId ? 'selected' : ''}
              onClick={() => select(e.entityId)}
            >
              {e.entityId}
            </button>
          ))}
        </aside>
        <section className="map-main">
          <SituationMap
            entities={situation?.entities || []}
            selected={selected}
            onSelect={select}
            focus={0}
            view={view}
            onView={setView}
            fitBounds={null}
            onFitted={() => {}}
            scenario={{
              scenarioId: 'semantic-demo-v1',
              version: 1,
              name: `Mock ${system.toUpperCase()} · 합성 시나리오`,
              initialBounds: [125.3, 37.3, 127.5, 38.5],
              zones: [],
            }}
          />
        </section>
        <aside>
          <h2>객체 상세</h2>
          {entity ? (
            <>
              <p>
                {entity.entityId} · {entity.kind}
              </p>
              <p>조직: {entity.unitId}</p>
              <p>원천: {system.toUpperCase()}</p>
              <p>
                {entity.position.longitude.toFixed(5)}, {entity.position.latitude.toFixed(5)}
              </p>
              <label>
                가용 상태 변경
                <select value={availability} onChange={(e) => setAvailability(e.target.value)}>
                  <option value="available">가용</option>
                  <option value="unavailable">가용 불가</option>
                  <option value="unknown">미확인</option>
                </select>
              </label>
              <button
                onClick={() =>
                  void action(`equipment/${encodeURIComponent(entity.entityId)}`, patch, 'PATCH')
                }
              >
                변경 적용
              </button>
              <p role="status">{message}</p>
            </>
          ) : (
            <p>객체를 선택하세요.</p>
          )}
        </aside>
      </main>
    </div>
  );
}
