import { useEffect, useState } from 'react';
import './Domain.css';

const pretty = (value: unknown) => JSON.stringify(value, null, 2);
export default function FabricApp() {
  const [catalog, setCatalog] = useState<{ datasetId?: string; layers?: string[] }>({});
  const [tab, setTab] = useState('원천 연결');
  const [data, setData] = useState<unknown>(null);
  const [version, setVersion] = useState('');
  const [term, setTerm] = useState('all');
  const [subject, setSubject] = useState('atcis:report:R2');
  const [error, setError] = useState('');
  const [token, setToken] = useState(sessionStorage.getItem('fabric.readToken') || '');
  const get = async (path: string) => {
    const r = await fetch('/v1/' + path, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.json();
  };
  useEffect(() => {
    void get('catalog')
      .then(setCatalog)
      .catch((e) => setError(String(e)));
  }, [token]);
  const query = async () => {
    setError('');
    setData(null);
    try {
      if (tab === '원천 연결') setData(await get('sources'));
      else if (tab === 'Catalog') setData(await get('catalog'));
      else if (!version) setError('규칙을 조회할 Graph 버전이 필요합니다.');
      else if (tab === 'Graph build') setData(await get('builds/' + encodeURIComponent(version)));
      else if (tab === '관계·근거')
        setData(
          await get(
            `relations?graphVersion=${encodeURIComponent(version)}&subject=${encodeURIComponent(subject)}&relationTypes=REFERS_TO,DERIVED_FROM,SUPERSEDES,ASSIGNED_TO,SUBORDINATE_TO&depth=2&limit=100`,
          ),
        );
      else
        setData(
          await get(
            `concepts?graphVersion=${encodeURIComponent(version)}&term=${encodeURIComponent(term)}`,
          ),
        );
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <div className="domain-shell">
      <header>
        <div>
          <small>ONTOLOGY · MCP · PROVENANCE</small>
          <h1>Data Fabric</h1>
          <span>{catalog.datasetId}</span>
        </div>
        <span>읽기 전용 콘솔</span>
      </header>
      <div className="domain-credentials">
        <label>
          읽기 토큰
          <input
            type="password"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              sessionStorage.setItem('fabric.readToken', e.target.value);
            }}
          />
        </label>
        <label>
          Graph 버전
          <input
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="domain-… 또는 active"
          />
        </label>
      </div>
      <main className="fabric-grid">
        <aside>
          <h2>탐색</h2>
          {['원천 연결', 'Catalog', '도메인 규칙', '관계·근거', 'Graph build'].map((label) => (
            <button
              className="domain-record"
              key={label}
              aria-pressed={tab === label}
              onClick={() => {
                setTab(label);
                setData(null);
                setError(
                  label === '도메인 규칙' && !version
                    ? '규칙을 조회할 Graph 버전이 필요합니다.'
                    : '',
                );
              }}
            >
              {label}
            </button>
          ))}
          <h2>검증 층</h2>
          {catalog.layers?.map((layer, i) => (
            <p key={layer}>
              L{i + 1} · {layer}
            </p>
          ))}
        </aside>
        <section>
          <h2>{tab}</h2>
          {tab === '관계·근거' ? (
            <label>
              객체 참조
              <input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </label>
          ) : tab === '도메인 규칙' ? (
            <label>
              개념·규칙 ID
              <input value={term} onChange={(e) => setTerm(e.target.value)} />
            </label>
          ) : null}
          <button onClick={() => void query()}>조회</button>
          {error && <p role="alert">{error}</p>}
          {data !== null && <pre>{pretty(data)}</pre>}
          <p>
            원천·문서 버전, 매핑/규칙, 관계 assertion의 출처를 조회합니다. 분석형 AI 실행은
            플랫폼에서 진행합니다.
          </p>
        </section>
      </main>
    </div>
  );
}
