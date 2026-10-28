import { useCallback, useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import './GraphExplorer.css';

type Snapshot = { datasetId?: string; epochId?: string; snapshotId?: string; sourceTime?: string };
type Build = {
  graphVersion: string;
  builtAt?: string;
  inputSnapshotSet?: Record<string, Snapshot>;
  isActive?: boolean;
  status?: string;
  ontologyVersion?: string;
};
type Node = { key: string; label: string; name: string };
type Edge = {
  evidenceId: string;
  start: string;
  end: string;
  kind: string;
  ruleId?: string;
  ruleVersion?: string;
  adapterVersion?: string;
  provenanceKind?: string;
  sourceRefs?: unknown[];
  documentRefs?: unknown[];
};
type Neighborhood = {
  graphVersion: string;
  nodes: Node[];
  edges: Edge[];
  completeness: string;
  omittedReasons: string[];
};
type Summary = {
  build: Build;
  nodeCounts: Record<string, number>;
  edgeCounts: Record<string, number>;
};
type Get = (path: string) => Promise<any>;
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
const kinds = [
  'SUBORDINATE_TO',
  'ASSIGNED_TO',
  'REFERS_TO',
  'DERIVED_FROM',
  'SUPERSEDES',
  'SAME_AS',
  'MAINTAINS',
  'REQUIRES',
  'STOCK_OF',
  'RESERVES',
  'FOR_WORK',
  'FULFILLED_BY',
  'CARRIED_BY',
  'CONTAINS_PART',
];
const time = (value?: string) =>
  value && !Number.isNaN(Date.parse(value))
    ? new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'Asia/Seoul',
        dateStyle: 'short',
        timeStyle: 'medium',
      }).format(new Date(value)) + ' KST'
    : '정보 없음';
const datasets = (b: Build) =>
  [...new Set(Object.values(b.inputSnapshotSet || {}).map((s) => s.datasetId || '정보 없음'))].join(
    ', ',
  ) || '정보 없음';
function shortId(id: string, builds: Build[]) {
  let length = 8;
  while (
    length < id.length &&
    builds.some((b) => b.graphVersion !== id && b.graphVersion.slice(-length) === id.slice(-length))
  )
    length += 4;
  return id.length > length ? '…' + id.slice(-length) : id;
}
const label = (b: Build, builds: Build[]) =>
  `${time(b.builtAt)} · ${datasets(b)} · ${shortId(b.graphVersion, builds)}`;

export default function GraphExplorer({
  get,
  version,
  onVersion,
  visible,
  onRule,
  onDocument,
}: {
  get: Get;
  version: string;
  onVersion: (v: string) => void;
  visible: boolean;
  onRule: (rule: string) => void;
  onDocument?: (key: string, version: string) => void;
}) {
  const [builds, setBuilds] = useState<Build[]>([]);
  const [pinned, setPinned] = useState<Build[]>([]);
  const [active, setActive] = useState('');
  const [buildQuery, setBuildQuery] = useState('');
  const [dataset, setDataset] = useState('');
  const [date, setDate] = useState('');
  const [buildCursor, setBuildCursor] = useState<string | null>(null);
  const [buildError, setBuildError] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [system, setSystem] = useState('');
  const [type, setType] = useState('');
  const [relations, setRelations] = useState(kinds);
  const [graph, setGraph] = useState<Neighborhood | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [edge, setEdge] = useState<Edge | null>(null);
  const [evidence, setEvidence] = useState<any>(null);
  const [selected, setSelected] = useState('');
  const [mode, setMode] = useState('그래프');
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const generation = useRef(0);
  const buildGeneration = useRef(0);
  const chosen = useRef(version);
  const initialized = useRef(false);
  const nodeRequest = useRef(0);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  chosen.current = version;
  const options = [...new Map([...builds, ...pinned].map((b) => [b.graphVersion, b])).values()];
  const selectedBuild = options.find((b) => b.graphVersion === version);

  const loadBuilds = async (next = '') => {
    const id = ++buildGeneration.current;
    setBuildError('');
    try {
      const result = await get(
        'graph-builds?' + new URLSearchParams({ q: buildQuery, dataset, date, cursor: next }),
      );
      if (id !== buildGeneration.current) return;
      setBuilds(result.items);
      setBuildCursor(result.nextCursor);
      setActive(result.activeGraphVersion || '');
      const saved: Build[] = [];
      for (const value of new Set([result.activeGraphVersion, chosen.current].filter(Boolean))) {
        const info = await get('builds/' + encodeURIComponent(value));
        if (info.status === 'READY' && ['3.0.0', '4.0.0'].includes(info.ontologyVersion))
          saved.push(info);
      }
      if (id !== buildGeneration.current) return;
      setPinned(saved);
      if (!initialized.current) {
        initialized.current = true;
        const current = saved.find((b) => b.graphVersion === result.activeGraphVersion);
        if (current && !chosen.current) onVersion(current.graphVersion);
      }
    } catch (e) {
      if (id === buildGeneration.current) setBuildError(String(e));
    }
  };
  useEffect(() => {
    initialized.current = false;
    void loadBuilds();
    return () => {
      buildGeneration.current++;
    };
  }, [get]);

  const searchNodes = useCallback(
    async (next = '', append = false) => {
      const id = generation.current;
      const request = ++nodeRequest.current;
      if (!version) return;
      setError('');
      setBusy(true);
      try {
        const result = await get(
          'graph-nodes?' +
            new URLSearchParams({ graphVersion: version, q, system, type, cursor: next }),
        );
        if (id !== generation.current || request !== nodeRequest.current) return;
        setNodes((old) => (append ? [...old, ...result.items] : result.items));
        setCursor(result.nextCursor);
      } catch (e) {
        if (id === generation.current && request === nodeRequest.current) setError(String(e));
      } finally {
        if (id === generation.current && request === nodeRequest.current) setBusy(false);
      }
    },
    [get, version, q, system, type],
  );

  useEffect(() => {
    generation.current++;
    let disposed = false;
    nodeRequest.current++;
    setGraph(null);
    setDetail(null);
    setEdge(null);
    setEvidence(null);
    setNodes([]);
    setCursor(null);
    setSummary(null);
    setError('');
    setSelected('');
    setBusy(false);
    setView({ x: 0, y: 0, scale: 1 });
    if (version) {
      void get('graph-summary?' + new URLSearchParams({ graphVersion: version }))
        .then((value) => {
          if (!disposed) {
            setSummary(value);
            setPinned((old) => [
              ...old.filter((b) => b.graphVersion !== value.build.graphVersion),
              value.build,
            ]);
          }
        })
        .catch((e) => {
          if (!disposed) setError(String(e));
        });
    }
    return () => {
      disposed = true;
      generation.current++;
    };
  }, [version, get]);
  useEffect(() => {
    setNodes([]);
    setCursor(null);
    void searchNodes();
    return () => {
      nodeRequest.current++;
    };
  }, [searchNodes]);

  const chooseNode = async (key: string, expand = false) => {
    const id = ++generation.current;
    setBusy(true);
    setError('');
    setSelected(key);
    setEdge(null);
    setEvidence(null);
    setDetail(null);
    try {
      const [value, neighborhood] = await Promise.all([
        get('graph-node?' + new URLSearchParams({ graphVersion: version, nodeKey: key })),
        get(
          'graph-neighborhood?' +
            new URLSearchParams({
              graphVersion: version,
              subject: key,
              relationTypes: relations.join(','),
              depth: '1',
            }),
        ),
      ]);
      if (id !== generation.current) return;
      setDetail(value);
      setGraph((old) => {
        if (!expand || !old) return neighborhood;
        const mergedNodes = [
          ...new Map([...old.nodes, ...neighborhood.nodes].map((n) => [n.key, n])).values(),
        ];
        const mergedEdges = [
          ...new Map([...old.edges, ...neighborhood.edges].map((e) => [e.evidenceId, e])).values(),
        ];
        if (mergedNodes.length > 200 || mergedEdges.length > 300) {
          setError('화면 상한(200노드/300관계)에 도달했습니다. 필터를 줄여 다시 조회하세요.');
          return old;
        }
        return {
          ...neighborhood,
          nodes: mergedNodes,
          edges: mergedEdges,
          completeness:
            old.completeness === 'partial' || neighborhood.completeness === 'partial'
              ? 'partial'
              : 'complete',
          omittedReasons: [...new Set([...old.omittedReasons, ...neighborhood.omittedReasons])],
        };
      });
    } catch (e) {
      if (id === generation.current) setError(String(e));
    } finally {
      if (id === generation.current) setBusy(false);
    }
  };
  const chooseEdge = (value: Edge) => {
    generation.current++;
    setBusy(false);
    setEdge(value);
    setDetail(null);
    setEvidence(null);
  };
  const loadEvidence = async () => {
    if (!edge) return;
    const id = generation.current;
    try {
      const value = await get(
        `evidence/${encodeURIComponent(edge.evidenceId)}?` +
          new URLSearchParams({ graphVersion: version }),
      );
      if (id === generation.current) setEvidence(value);
    } catch (e) {
      if (id === generation.current) setError(String(e));
    }
  };
  const resetGraph = () => {
    generation.current++;
    setBusy(false);
    setGraph(null);
    setDetail(null);
    setEdge(null);
    setEvidence(null);
    setSelected('');
  };
  const points = new Map(
    (graph?.nodes || []).map((n, i, all) => {
      const columns = Math.max(2, Math.ceil(Math.sqrt(all.length)));
      return [n.key, { x: 130 + (i % columns) * 210, y: 80 + Math.floor(i / columns) * 135 }];
    }),
  );
  const columns = Math.max(2, Math.ceil(Math.sqrt(graph?.nodes.length || 1)));
  const width = Math.max(700, columns * 210 + 50);
  const height = Math.max(450, Math.ceil((graph?.nodes.length || 1) / columns) * 135 + 30);
  const pan = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (drag.current)
      setView((old) => ({
        ...old,
        x: drag.current!.vx + ((e.clientX - drag.current!.x) * width) / e.currentTarget.clientWidth,
        y:
          drag.current!.vy +
          ((e.clientY - drag.current!.y) * height) / e.currentTarget.clientHeight,
      }));
  };
  return (
    <div className="graph-explorer">
      <div className="graph-version-panel">
        <h2>Graph 버전</h2>
        <form
          className="graph-tools"
          onSubmit={(e) => {
            e.preventDefault();
            void loadBuilds();
          }}
        >
          <label>
            버전 검색
            <input
              value={buildQuery}
              onChange={(e) => setBuildQuery(e.target.value)}
              placeholder="생성 시각 · 데이터셋 · ID"
            />
          </label>
          <label>
            데이터셋
            <input value={dataset} onChange={(e) => setDataset(e.target.value)} />
          </label>
          <label>
            생성 날짜(UTC)
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button>버전 찾기·새로고침</button>
          {buildCursor && (
            <button type="button" onClick={() => void loadBuilds(buildCursor)}>
              다음 버전 페이지
            </button>
          )}
        </form>
        {buildError && (
          <p role="alert">
            Graph 조회 오류: {buildError} · 인증/Graph 연결을 확인하고 재시도하세요.
          </p>
        )}
        <label className="graph-version-select">
          조회할 Graph 버전
          <select
            aria-label="조회할 Graph 버전"
            value={version}
            onChange={(e) => {
              resetGraph();
              onVersion(e.target.value);
            }}
          >
            <option value="">버전을 선택하세요</option>
            {options.map((b) => (
              <option key={b.graphVersion} value={b.graphVersion}>
                {label(b, options)}
                {b.graphVersion === active ? ' · 현재 활성' : ''}
                {b.graphVersion === version ? ' · 조회 중' : ''}
              </option>
            ))}
          </select>
        </label>
        {!options.length && !buildError && (
          <p>
            생성된 READY Graph 없음. 원천을 준비하고 플랫폼의 Semantic ON 분석 준비 절차로 Graph를
            생성하세요.
          </p>
        )}
        {options.length > 0 && !version && <p>조회할 READY Graph를 목록에서 선택하세요.</p>}
        {version && (
          <div className="graph-current">
            <strong>조회 중 · {selectedBuild ? label(selectedBuild, options) : version}</strong>
            <span>{version === active ? '현재 활성' : '활성 버전과 다른 버전 조회 중'}</span>
            <button
              onClick={() =>
                void navigator.clipboard.writeText(version).catch((e) => setBuildError(String(e)))
              }
            >
              전체 버전 ID 복사
            </button>
            <details>
              <summary>버전 ID·원천 기준 상세</summary>
              <p>{version}</p>
              {Object.entries(selectedBuild?.inputSnapshotSet || {}).map(([source, s]) => (
                <p key={source}>
                  {source} · 원천 기준 {time(s.sourceTime)} · snapshot {s.snapshotId || '정보 없음'}{' '}
                  · epoch {s.epochId || '정보 없음'}
                </p>
              ))}
              <pre>{pretty(summary?.build || selectedBuild)}</pre>
            </details>
          </div>
        )}
      </div>
      {visible && (
        <>
          <p>
            저장된 의미·관계·근거를 조회합니다. 위치·가용 상태의 현재 값은 원천 화면에서 확인하세요.
          </p>
          {error && <p role="alert">{error}</p>}
          {summary && (
            <div className="graph-counts">
              <div>
                <h3>노드 유형별 레코드 수</h3>
                {Object.entries(summary.nodeCounts).map(([key, count]) => (
                  <button
                    key={key}
                    onClick={() => {
                      resetGraph();
                      setType(key);
                    }}
                  >
                    {key} · {count}
                  </button>
                ))}
              </div>
              <div>
                <h3>관계 유형별 레코드 수</h3>
                {Object.entries(summary.edgeCounts).map(([key, count]) => (
                  <span key={key}>
                    {key} · {count}{' '}
                  </span>
                ))}
              </div>
              <small>원천 기록·canonical 객체·assertion 수는 실제 자산 수와 다릅니다.</small>
            </div>
          )}
          <form
            className="graph-tools"
            onSubmit={(e) => {
              e.preventDefault();
              setMode('목록');
              void searchNodes();
            }}
          >
            <label>
              객체 검색
              <input
                value={q}
                onChange={(e) => {
                  resetGraph();
                  setQ(e.target.value);
                }}
                placeholder="이름 또는 원천/canonical ID"
              />
            </label>
            <label>
              원천
              <select
                value={system}
                onChange={(e) => {
                  resetGraph();
                  setSystem(e.target.value);
                }}
              >
                <option value="">전체</option>
                <option>atcis</option>
                <option>knccs</option>
              </select>
            </label>
            <label>
              노드 유형
              <select
                value={type}
                onChange={(e) => {
                  resetGraph();
                  setType(e.target.value);
                }}
              >
                <option value="">전체</option>
                {Object.keys(summary?.nodeCounts || {}).map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <button disabled={!version}>객체 찾기</button>
          </form>
          <div className="graph-tools">
            <label>
              관계 프리셋
              <select
                onChange={(e) => {
                  resetGraph();
                  setRelations(e.target.value.split(','));
                }}
                defaultValue={kinds.join(',')}
              >
                <option value={kinds.join(',')}>전체 도메인 관계</option>
                <option value="SUBORDINATE_TO,ASSIGNED_TO">조직·장비 배정</option>
                <option value="SAME_AS,MAINTAINS,REQUIRES,STOCK_OF,RESERVES,FOR_WORK,FULFILLED_BY,CARRIED_BY,CONTAINS_PART">
                  군수·정비·수송
                </option>
                <option value="REFERS_TO">동일성·원천 참조</option>
                <option value="DERIVED_FROM,SUPERSEDES">보고 계보</option>
              </select>
            </label>
            {kinds.map((k) => (
              <label key={k}>
                <input
                  type="checkbox"
                  checked={relations.includes(k)}
                  disabled={relations.length === 1 && relations.includes(k)}
                  onChange={(e) => {
                    resetGraph();
                    setRelations((old) =>
                      e.target.checked ? [...old, k] : old.filter((x) => x !== k),
                    );
                  }}
                />
                {k}
              </label>
            ))}
          </div>
          {busy && <p role="status">조회 중…</p>}
          <div className="graph-mobile-tabs">
            {['목록', '그래프', '상세'].map((m) => (
              <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)}>
                {m}
              </button>
            ))}
          </div>
          <div className="graph-workspace">
            <div className={'graph-list ' + (mode === '목록' ? 'mobile-selected' : '')}>
              <h3>객체 목록</h3>
              {!nodes.length && version && !busy && <p>검색 결과 0개</p>}
              {nodes.map((n) => (
                <button
                  className="domain-record"
                  key={n.key}
                  aria-label={'객체 ' + n.key}
                  aria-pressed={selected === n.key}
                  onClick={() => {
                    void chooseNode(n.key);
                    setMode('그래프');
                  }}
                >
                  <strong>{n.name}</strong>
                  <small>
                    {n.label} · {n.key}
                  </small>
                </button>
              ))}
              {cursor && (
                <button onClick={() => void searchNodes(cursor, true)}>객체 더 보기</button>
              )}
            </div>
            <div className={'graph-canvas-panel ' + (mode === '그래프' ? 'mobile-selected' : '')}>
              <h3>관계 그래프</h3>
              <div className="graph-tools">
                <button onClick={() => setView({ x: 0, y: 0, scale: 1 })}>화면 맞춤</button>
                <button
                  aria-label="확대"
                  onClick={() => setView((v) => ({ ...v, scale: Math.min(4, v.scale * 1.2) }))}
                >
                  ＋
                </button>
                <button
                  aria-label="축소"
                  onClick={() => setView((v) => ({ ...v, scale: Math.max(0.25, v.scale / 1.2) }))}
                >
                  −
                </button>
                <button
                  disabled={!selected || !relations.length}
                  onClick={() => void chooseNode(selected, true)}
                >
                  선택 객체 주변 확장
                </button>
              </div>
              {!graph && <p>목록에서 객체를 선택해 주변 관계를 조회하세요.</p>}
              {graph && (
                <>
                  <p>
                    {graph.nodes.length}노드 · {graph.edges.length}관계 ·{' '}
                    {graph.completeness === 'partial'
                      ? `부분 결과 (${graph.omittedReasons.join(', ')})`
                      : '요청 범위 조회 완료'}
                  </p>
                  <p className="graph-legend">
                    □ 조직(Unit) · ◇ 장비(Equipment) · ○ 기타 · 화살표: 저장된 관계 방향
                  </p>
                  <svg
                    role="img"
                    aria-label="Graph 관계 시각화"
                    viewBox={`0 0 ${width} ${height}`}
                    onPointerDown={(e) => {
                      if (e.target === e.currentTarget) {
                        drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
                        e.currentTarget.setPointerCapture(e.pointerId);
                      }
                    }}
                    onPointerMove={pan}
                    onPointerUp={() => {
                      drag.current = null;
                    }}
                    onPointerCancel={() => {
                      drag.current = null;
                    }}
                  >
                    <defs>
                      <marker
                        id="graph-arrow"
                        markerWidth="10"
                        markerHeight="8"
                        refX="10"
                        refY="4"
                        orient="auto"
                      >
                        <path d="M0,0 L10,4 L0,8" fill="#91a8b7" />
                      </marker>
                    </defs>
                    <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
                      {graph.edges.map((e, i) => {
                        const a = points.get(e.start)!;
                        const b = points.get(e.end)!;
                        const parallel = graph.edges.filter(
                          (x) =>
                            (x.start === e.start && x.end === e.end) ||
                            (x.start === e.end && x.end === e.start),
                        );
                        const index = parallel.indexOf(e);
                        const offset = (index - (parallel.length - 1) / 2) * 38;
                        const mx = (a.x + b.x) / 2 + offset;
                        const my = (a.y + b.y) / 2 - 42 - offset;
                        const path =
                          e.start === e.end
                            ? `M${a.x - 15},${a.y - 15} C${a.x - 100},${a.y - 110} ${a.x + 100},${a.y - 110} ${a.x + 15},${a.y - 15}`
                            : `M${a.x},${a.y + 22} Q${mx},${my} ${b.x},${b.y - 25}`;
                        return (
                          <g
                            key={e.evidenceId}
                            role="button"
                            tabIndex={0}
                            aria-label={`관계 ${e.kind} ${i + 1}`}
                            onClick={() => {
                              chooseEdge(e);
                              setMode('상세');
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                chooseEdge(e);
                                setMode('상세');
                              }
                            }}
                          >
                            <path
                              d={path}
                              fill="none"
                              stroke={edge?.evidenceId === e.evidenceId ? '#f2c475' : '#91a8b7'}
                              strokeWidth="2"
                              markerEnd="url(#graph-arrow)"
                            />
                            <text x={mx} y={my} textAnchor="middle">
                              {e.kind}
                            </text>
                          </g>
                        );
                      })}
                      {graph.nodes.map((n) => {
                        const p = points.get(n.key)!;
                        return (
                          <g
                            key={n.key}
                            role="button"
                            tabIndex={0}
                            aria-label={`그래프 객체 ${n.key}`}
                            transform={`translate(${p.x} ${p.y})`}
                            onClick={() => {
                              void chooseNode(n.key, true);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                void chooseNode(n.key, true);
                              }
                            }}
                          >
                            <title>
                              {n.name} · {n.key}
                            </title>
                            {n.label === 'Unit' ? (
                              <rect x="-28" y="-22" width="56" height="44" />
                            ) : n.label === 'Equipment' ? (
                              <path d="M0,-28 L34,0 L0,28 L-34,0 Z" />
                            ) : (
                              <circle r="24" />
                            )}
                            <text y="45" textAnchor="middle">
                              {n.name.length > 25 ? n.name.slice(0, 25) + '…' : n.name}
                            </text>
                            <text y="61" textAnchor="middle" className="graph-node-type">
                              {n.label}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  </svg>
                  <details>
                    <summary>관계 목록 · 키보드로 선택</summary>
                    {graph.edges.map((e) => (
                      <button
                        key={e.evidenceId}
                        className="domain-record"
                        aria-label={`관계 상세 ${e.evidenceId}`}
                        onClick={() => {
                          chooseEdge(e);
                          setMode('상세');
                        }}
                      >
                        {e.start} → {e.kind} → {e.end}
                      </button>
                    ))}
                    {!graph.edges.length && <p>선택한 관계 종류에 연결이 없는 고립 노드입니다.</p>}
                  </details>
                </>
              )}
            </div>
            <div className={'graph-detail ' + (mode === '상세' ? 'mobile-selected' : '')}>
              <h3>선택 상세</h3>
              {!detail && !edge && <p>객체나 관계를 선택하세요.</p>}
              {detail && (
                <>
                  <p>객체 ID · {detail.item.key}</p>
                  <p>유형 · {detail.item.label}</p>
                  <h4>원천·정의</h4>
                  <dl className="graph-properties">
                    {Object.entries(detail.item.payload || {})
                      .filter(([, value]) => value !== null && typeof value !== 'object')
                      .map(([key, value]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>{String(value)}</dd>
                        </div>
                      ))}
                  </dl>
                  <pre>
                    {pretty(
                      detail.item.sourceRef ||
                        detail.item.payload?.documentRefs ||
                        '원천 참조 없음',
                    )}
                  </pre>
                  <details>
                    <summary>객체 payload · 원본 JSON</summary>
                    <pre>{pretty(detail)}</pre>
                  </details>
                </>
              )}
              {edge && (
                <>
                  <p>
                    {edge.start} → {edge.kind} → {edge.end}
                  </p>
                  <p>
                    규칙 · {edge.ruleId || '도메인 규칙 없음'} /{' '}
                    {edge.ruleVersion || edge.adapterVersion || '정보 없음'}
                  </p>
                  {edge.ruleId && (
                    <button onClick={() => onRule(edge.ruleId!)}>규칙 {edge.ruleId} 보기</button>
                  )}
                  {(edge.documentRefs || []).map((value, i) => {
                    const ref = value as {
                      systemId: string;
                      nativeId: string;
                      documentKey?: string;
                      knowledgeSetVersion?: string;
                    };
                    return (
                      <button
                        key={i}
                        className="domain-record"
                        onClick={() => {
                          if (ref.documentKey && ref.knowledgeSetVersion)
                            onDocument?.(ref.documentKey, ref.knowledgeSetVersion);
                          else void chooseNode(`${ref.systemId}:document:${ref.nativeId}`);
                          setMode('상세');
                        }}
                      >
                        {ref.documentKey ? 'Fabric 지식' : '원천 문서'}{' '}
                        {ref.documentKey || ref.systemId + ' · ' + ref.nativeId} 보기
                      </button>
                    );
                  })}
                  <p>출처 유형 · {edge.provenanceKind || '도메인 assertion'}</p>
                  <p>assertion · {edge.evidenceId}</p>
                  <h4>원천 참조·문서 근거</h4>
                  <pre>
                    {pretty({ sourceRefs: edge.sourceRefs, documentRefs: edge.documentRefs })}
                  </pre>
                  <button onClick={() => void loadEvidence()}>근거 조회</button>
                  <details>
                    <summary>관계 원본 JSON</summary>
                    <pre>{pretty(edge)}</pre>
                  </details>
                </>
              )}
              {evidence && (
                <>
                  <h4>근거 응답</h4>
                  <pre>{pretty(evidence)}</pre>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
