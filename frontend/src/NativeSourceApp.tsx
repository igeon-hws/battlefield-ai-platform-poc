import { useEffect, useState } from 'react';
import { SituationMap, type EntityView } from './App';
import './Domain.css';

type Row = Record<string, any>;
type Snapshot = {
  snapshotId: string;
  baselineSnapshotId: string;
  sourceTime: string;
  running: boolean;
  datasetId: string;
  records: Record<string, Row[]>;
};
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
const tabs = {
  atcis: {
    equipment: '장비·정비',
    units: '편제',
    reports: '상황보고',
    journal: '상황일지',
    activities: '활동',
    documents: '기준 문서',
  },
  knccs: {
    'own-forces': '자군 함정',
    contacts: '접촉·항적',
    tracks: '관측 이력',
    formations: '편성',
    messages: '전문함',
    'delivery-events': '수신 이력',
    associations: '참조 기록',
    documents: '기준 문서',
  },
};

function identity(row: Row) {
  return String(
    row.equipmentId ||
      row.pennant ||
      row.reportId ||
      row.serial ||
      row.activityId ||
      row.observationId ||
      row.receiptId ||
      row.associationId ||
      row.entryId ||
      row.unitCode ||
      row.formationRef ||
      row.documentId ||
      `${row.originator}/${row.trackNo}`,
  );
}

export default function NativeSourceApp({ system }: { system: 'atcis' | 'knccs' }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState(system === 'atcis' ? 'equipment' : 'own-forces');
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [readToken, setReadToken] = useState(sessionStorage.getItem(`${system}.readToken`) || '');
  const [controlToken, setControlToken] = useState(
    sessionStorage.getItem(`${system}.controlToken`) || '',
  );
  const [stateCode, setStateCode] = useState('');
  const [view, setView] = useState({
    center: [126.5, 37.25] as [number, number],
    zoom: 9,
    bearing: 0,
  });
  const request = async (path: string, control = false, body?: object, method?: string) => {
    const response = await fetch('/api/v1/' + path, {
      method: method || (control ? 'POST' : 'GET'),
      headers: {
        Authorization: `Bearer ${control ? controlToken : readToken}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return response.json();
  };
  const refresh = async () => {
    try {
      setSnapshot(await request('snapshot'));
      setError('');
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [readToken]);
  const action = async (path: string, body?: object, method?: string) => {
    try {
      await request(path, true, body, method);
      setStatus('진행 완료');
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };
  const records = snapshot?.records[tab] || [];
  const record = records.find((r) => identity(r) === selected);
  const sourceRows =
    system === 'atcis'
      ? snapshot?.records.equipment || []
      : [...(snapshot?.records['own-forces'] || []), ...(snapshot?.records.contacts || [])];
  const entities: EntityView[] = sourceRows
    .map(
      (row) =>
        ({
          entityId: identity(row),
          label: identity(row),
          kind:
            system === 'atcis'
              ? { TK: 'tank', AAV: 'armored_vehicle', LOG: 'support_vehicle', UAS: 'uav' }[
                  row.classCode as string
                ] || 'unknown'
              : row.pennant
                ? 'naval_vessel'
                : 'unknown',
          affiliation:
            row.side === 'F' || row.identity === 'FRIEND'
              ? 'friendly'
              : row.side === 'H' || row.identity === 'HOSTILE'
                ? 'hostile'
                : 'unknown',
          availability: 'unknown',
          unitId: row.ownerCode || row.formationRef || '',
          position:
            system === 'atcis' ? { longitude: row.position.x, latitude: row.position.y } : row.geo,
          velocity:
            system === 'atcis'
              ? { eastMps: row.vector.east, northMps: row.vector.north }
              : {
                  eastMps:
                    ((row.motion.knots * 1852) / 3600) *
                    Math.sin((row.motion.course * Math.PI) / 180),
                  northMps:
                    ((row.motion.knots * 1852) / 3600) *
                    Math.cos((row.motion.course * Math.PI) / 180),
                },
          updatedAt: snapshot?.sourceTime || '',
          observedAt: snapshot?.sourceTime || '',
          revision: 1,
          source: system,
        }) as EntityView,
    )
    .map((entity) => {
      const { eastMps, northMps } = entity.velocity;
      const speedMps = Math.hypot(eastMps, northMps);
      return {
        ...entity,
        speedMps,
        bearingDegrees: speedMps
          ? ((Math.atan2(eastMps, northMps) * 180) / Math.PI + 360) % 360
          : null,
        displayVector: speedMps
          ? {
              horizonSeconds: 60,
              endPosition: {
                latitude: entity.position.latitude + (northMps * 60) / 111320,
                longitude:
                  entity.position.longitude +
                  (eastMps * 60) / (111320 * Math.cos((entity.position.latitude * Math.PI) / 180)),
              },
            }
          : null,
      };
    });
  return (
    <div className={`domain-shell ${system}`}>
      <header>
        <div>
          <small>SYNTHETIC {system === 'atcis' ? 'LAND COMMAND' : 'MARITIME COMMAND'}</small>
          <h1>Mock {system.toUpperCase()}</h1>
          <span>
            {snapshot?.datasetId} · {snapshot?.sourceTime}
          </span>
        </div>
        <div className="domain-actions">
          <button
            onClick={() => void action(`simulation/${snapshot?.running ? 'pause' : 'start'}`)}
          >
            {snapshot?.running ? '일시 정지' : '이동 시작'}
          </button>
          <button onClick={() => void action('simulation/step')}>1초 진행</button>
        </div>
      </header>
      <div className="domain-credentials">
        <label>
          읽기 토큰
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
          제어 토큰
          <input
            type="password"
            value={controlToken}
            onChange={(e) => {
              setControlToken(e.target.value);
              sessionStorage.setItem(`${system}.controlToken`, e.target.value);
            }}
          />
        </label>
        <span role="status">{status}</span>
      </div>
      {error && <p role="alert">{error}</p>}
      <nav>
        {Object.entries(tabs[system]).map(([key, label]) => (
          <button
            key={key}
            aria-pressed={key === tab}
            onClick={() => {
              setTab(key);
              setSelected(null);
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <main className="domain-source-grid">
        <aside>
          <h2>{(tabs[system] as Record<string, string>)[tab]}</h2>
          <span>{records.length}건 · 원천 기록</span>
          {records.map((r) => (
            <button
              className="domain-record"
              key={`${system}:${tab}:${identity(r)}`}
              aria-label={identity(r)}
              onClick={() => {
                setSelected(identity(r));
                setStateCode(r.maintenanceCode || r.mission || '');
              }}
            >
              {identity(r)}
              <small>
                {r.name ||
                  r.designation ||
                  r.text?.slice(0, 70) ||
                  r.classCode ||
                  r.domain ||
                  r.hullClass}
              </small>
            </button>
          ))}
        </aside>
        <section className="domain-map">
          <SituationMap
            entities={entities}
            selected={selected}
            onSelect={setSelected}
            focus={0}
            view={view}
            onView={setView}
            fitBounds={null}
            onFitted={() => {}}
            scenario={{
              scenarioId: 'c2-domain-demo-v3',
              version: 3,
              name: '모의 연습',
              initialBounds: [126.2, 37.1, 126.7, 37.5],
              zones: [],
            }}
          />
        </section>
        <aside>
          <h2>원천 레코드</h2>
          {record ? (
            <>
              <pre>{pretty(record)}</pre>
              {(tab === 'equipment' || tab === 'own-forces') && (
                <>
                  <label>
                    {system === 'atcis' ? '정비 코드' : '임무 상태'}
                    <select value={stateCode} onChange={(e) => setStateCode(e.target.value)}>
                      {(system === 'atcis'
                        ? ['FMC', 'PMC', 'NMC', 'UNK']
                        : ['GO', 'HOLD', 'UNKNOWN']
                      ).map((code) => (
                        <option key={code}>{code}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    onClick={() =>
                      void action(
                        `${tab}/${encodeURIComponent(identity(record))}`,
                        system === 'atcis'
                          ? { maintenanceCode: stateCode }
                          : { mission: stateCode },
                        'PATCH',
                      )
                    }
                  >
                    상태 적용
                  </button>
                </>
              )}
            </>
          ) : (
            <p>목록에서 기록을 선택하세요.</p>
          )}
        </aside>
      </main>
    </div>
  );
}
