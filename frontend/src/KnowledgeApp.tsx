import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUpRight,
  ChevronDown,
  Clock3,
  Compass,
  History,
  Layers,
  Map as MapIcon,
  Maximize2,
  MessageSquare,
  Plus,
  Send,
  Target,
  X,
} from 'lucide-react';
import { SituationMap, type EntityView } from './App';
import { RunPanel, type Run } from './NextApp';
import { domainScenarios } from './domainScenarios';
import { formatTime } from './time';
import './KnowledgeApp.css';

type Mode = 'native' | 'documents' | 'structured';
const modes: Mode[] = ['native', 'documents', 'structured'];
const names: Record<Mode, string> = {
  native: 'A · 원천 데이터',
  documents: 'B · 원천 + 문서 지식',
  structured: 'C · 원천 + 구조화 지식',
};
const descriptions: Record<Mode, string> = {
  native: '원천 데이터로 분석',
  documents: '원천 데이터와 Fabric 문서로 분석',
  structured: '같은 문서와 검증된 관계·규칙으로 분석',
};
const statusName: Record<string, string> = {
  queued: '준비 대기',
  running: '분석 중',
  completed: '완료',
  partial: '부분 결과',
  failed: '실패',
  interrupted: '중단',
  preparing: '기준 준비 중',
  incomplete: '일부 미완료',
};
type KnowledgeRun = Run & {
  knowledgeMode: Mode;
  knowledgeSetVersion?: string;
  knowledgeSetHash?: string;
  graphInfo?: unknown;
};
type Comparison = {
  comparisonId: string;
  question: string;
  status: string;
  error?: string;
  runIds: Partial<Record<Mode, string>>;
  manifest: unknown;
};
type View = { center: [number, number]; zoom: number; bearing: number };
type Focus = { mode: Mode; conversation: string | null; comparison: string | null };
type UI = Focus & { view?: View; selected?: string | null; scroll?: Record<string, number> };
type MapEntity = EntityView & { nativeId?: string; nativeStatus?: unknown };
const storageKey = 'battlefield.v4.workspace';
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
function restore(): UI {
  try {
    const v = JSON.parse(sessionStorage.getItem(storageKey) || '{}');
    const view = v.view;
    return {
      mode: modes.includes(v.mode) ? v.mode : 'native',
      conversation: typeof v.conversation === 'string' ? v.conversation : null,
      comparison: typeof v.comparison === 'string' ? v.comparison : null,
      selected: typeof v.selected === 'string' ? v.selected : null,
      view:
        Array.isArray(view?.center) &&
        view.center.length === 2 &&
        view.center.every(Number.isFinite) &&
        Math.abs(view.center[0]) <= 180 &&
        Math.abs(view.center[1]) <= 90 &&
        Number.isFinite(view.zoom) &&
        view.zoom >= 0 &&
        view.zoom <= 18 &&
        Number.isFinite(view.bearing)
          ? view
          : undefined,
      scroll:
        v.scroll && typeof v.scroll === 'object'
          ? (Object.fromEntries(
              Object.entries(v.scroll)
                .filter(([, n]) => typeof n === 'number' && Number.isFinite(n) && n >= 0)
                .slice(-30),
            ) as Record<string, number>)
          : {},
    };
  } catch {
    return { mode: 'native', conversation: null, comparison: null };
  }
}
class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
async function api(path: string, body?: unknown, method = 'POST', signal?: AbortSignal) {
  const r = await fetch('/api/v1/' + path, {
    ...(body
      ? { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : {}),
    signal,
  });
  if (!r.ok) throw new ApiError(r.status, `${r.status}: ${await r.text()}`);
  return r.json();
}
function mergeRuns(old: KnowledgeRun[], next: KnowledgeRun[]): KnowledgeRun[] {
  const map = new Map(old.map((r) => [r.runId, r]));
  for (const run of next) {
    const prev = map.get(run.runId);
    if (
      prev &&
      ['completed', 'failed', 'partial', 'interrupted'].includes(prev.status) &&
      ['queued', 'running'].includes(run.status)
    )
      continue;
    map.set(run.runId, run);
  }
  return [...map.values()];
}
const keyFor = (f: Focus) =>
  f.comparison
    ? 'compare:' + f.comparison
    : f.conversation
      ? 'chat:' + f.conversation
      : 'draft:' + f.mode;
function progress(run: KnowledgeRun) {
  const call = run.toolCalls.find((c) => c.status === 'running');
  return call
    ? call.name.startsWith('knowledge__')
      ? '지식 문서 조회 중'
      : call.name.startsWith('semantic__')
        ? '구조화 지식 조회 중'
        : '원천 데이터 조회 중'
    : statusName[run.status] || run.status;
}

export default function KnowledgeApp({
  fabricUrl = 'http://localhost:4400',
}: {
  fabricUrl?: string;
}) {
  const [initial] = useState(restore);
  const [focus, setFocus] = useState<Focus>({
    mode: initial.mode,
    conversation: initial.conversation,
    comparison: initial.comparison,
  });
  const focusRef = useRef(focus);
  focusRef.current = focus;
  const selectionEpoch = useRef(0);
  const [view, setView] = useState<View>(
    initial.view || { center: [126.5, 37.8], zoom: 7, bearing: 0 },
  );
  const [selected, setSelected] = useState<string | null>(initial.selected || null);
  const [entities, setEntities] = useState<MapEntity[]>([]);
  const [sources, setSources] = useState<Record<string, { connected?: boolean; error?: string }>>(
    {},
  );
  const [sourceTime, setSourceTime] = useState('');
  const [mapError, setMapError] = useState('');
  const [connectionError, setConnectionError] = useState(false);
  const [runs, setRuns] = useState<KnowledgeRun[]>([]);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [objectsOpen, setObjectsOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [question, setQuestion] = useState('');
  const [baseline, setBaseline] = useState(false);
  const [busy, setBusy] = useState(false);
  const posting = useRef(false);
  const composing = useRef(false);
  const [mobile, setMobile] = useState<Mode>('native');
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  const editor = useRef<HTMLTextAreaElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const positions = useRef(initial.scroll || {});
  const restoredKey = useRef('');
  const [historyReady, setHistoryReady] = useState<string | null>(null);
  const [unseen, setUnseen] = useState(false);
  const [bounds, setBounds] = useState<[number, number, number, number] | null>(null);
  const fitted = useRef(Boolean(initial.view));
  const [mapFocus, setMapFocus] = useState(0);
  const focusKey = keyFor(focus);
  const persist = useCallback((f: Focus, v: View, s: string | null) => {
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ ...f, view: v, selected: s, scroll: positions.current }),
      );
    } catch {
      /* Storage may be disabled; analysis remains usable. */
    }
  }, []);
  useEffect(() => persist(focus, view, selected), [focus, view, selected, persist]);
  const navigate = (next: Focus) => {
    if (timelineRef.current)
      positions.current[keyFor(focusRef.current)] = timelineRef.current.scrollTop;
    selectionEpoch.current++;
    focusRef.current = next;
    restoredKey.current = '';
    setUnseen(false);
    setError('');
    setFocus(next);
    setHistoryOpen(false);
  };
  const acceptView = useCallback((v: View) => setView(v), []);
  const onFitted = useCallback(() => setBounds(null), []);
  const fit = (items: MapEntity[]) => {
    if (!items.length) return;
    const xs = items.map((e) => e.position.longitude),
      ys = items.map((e) => e.position.latitude);
    setBounds([
      Math.min(...xs) - 0.04,
      Math.min(...ys) - 0.04,
      Math.max(...xs) + 0.04,
      Math.max(...ys) + 0.04,
    ]);
  };
  useEffect(() => {
    if (entities.length && !fitted.current) {
      fitted.current = true;
      fit(entities);
    }
  }, [entities]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      const result = await Promise.allSettled(
        ['analyses', 'comparisons', 'situation', 'sources'].map((p) =>
          api(p, undefined, 'GET', controller.signal),
        ),
      );
      if (!active) return;
      if (result[0].status === 'fulfilled') {
        const items = result[0].value.items;
        setRuns((old) => mergeRuns(old, items));
      } else setNotice('대화 이력을 갱신하지 못했습니다.');
      if (result[1].status === 'fulfilled') {
        const items: Comparison[] = result[1].value.items;
        setComparisons((old) => [
          ...items,
          ...old.filter((c) => !items.some((next) => next.comparisonId === c.comparisonId)),
        ]);
      }
      if (result[2].status === 'fulfilled') {
        const s = result[2].value;
        setEntities(s.entities || []);
        setMapError('');
        const times = Object.values(s.sources || {})
          .map((v) => (v as { sourceTime?: string }).sourceTime)
          .filter((v): v is string => Boolean(v));
        setSourceTime(times.sort().at(-1) || '');
      } else setMapError('원천 갱신 지연 · 마지막 객체 정보 유지');
      if (result[3].status === 'fulfilled') {
        setSources(result[3].value.sources || {});
        setConnectionError(false);
      } else setConnectionError(true);
      timer = setTimeout(() => void poll(), 1200);
    };
    void poll();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, []);
  useEffect(() => {
    if (!focus.conversation) {
      setHistoryReady(null);
      return;
    }
    const id = focus.conversation;
    const controller = new AbortController();
    let active = true;
    setHistoryReady(null);
    void api('conversations/' + encodeURIComponent(id), undefined, 'GET', controller.signal)
      .then((data) => {
        if (active) {
          setRuns((old) => mergeRuns(old, data.items));
          setHistoryReady(id);
        }
      })
      .catch((e) => {
        if (!active) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotice('저장된 대화가 없어 새 대화를 열었습니다.');
          navigate({ ...focusRef.current, conversation: null });
        } else {
          setNotice('선택 대화의 이력을 불러오지 못했습니다.');
          setHistoryReady(id);
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [focus.conversation]);
  useEffect(() => {
    if (!focus.comparison) return;
    const id = focus.comparison;
    const controller = new AbortController();
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        // Lists are capped. Fetch the selected comparison and its runs explicitly
        // so a restored older comparison remains inspectable.
        const c: Comparison = await api(
          'comparisons/' + encodeURIComponent(id),
          undefined,
          'GET',
          controller.signal,
        );
        const results = await Promise.allSettled(
          Object.values(c.runIds).map((runId) =>
            api('analyses/' + encodeURIComponent(runId), undefined, 'GET', controller.signal),
          ),
        );
        if (!active) return;
        setComparisons((old) => [c, ...old.filter((item) => item.comparisonId !== id)]);
        const fetched = results.flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []));
        setRuns((old) => mergeRuns(old, fetched));
        if (results.some((r) => r.status === 'rejected'))
          setNotice('일부 비교 실행을 불러오지 못했습니다.');
      } catch (e) {
        if (!active) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotice('저장된 비교가 없어 대화로 돌아왔습니다.');
          navigate({ ...focusRef.current, comparison: null });
          return;
        }
        setNotice('선택 비교를 불러오지 못했습니다.');
      }
      if (active) timer = setTimeout(() => void refresh(), 1200);
    };
    void refresh();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [focus.comparison]);
  const timeline = useMemo(
    () =>
      runs
        .filter((r) => r.conversationId === focus.conversation && r.knowledgeMode === focus.mode)
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.runId.localeCompare(b.runId)),
    [runs, focus.conversation, focus.mode],
  );
  const current = comparisons.find((c) => c.comparisonId === focus.comparison);
  const conversationBusy = timeline.some((r) => ['queued', 'running'].includes(r.status));
  const signature =
    timeline
      .map((r) => r.runId + r.status + r.toolCalls.length + (r.result?.answer.length || 0))
      .join('|') + (current ? JSON.stringify(current) : '');
  useEffect(() => {
    const el = timelineRef.current;
    if (!el || (focus.conversation && historyReady !== focus.conversation && !focus.comparison))
      return;
    const frame = requestAnimationFrame(() => {
      if (restoredKey.current !== focusKey) {
        const saved = positions.current[focusKey];
        el.scrollTop = saved ?? el.scrollHeight;
        bottom.current = el.scrollHeight - el.clientHeight - el.scrollTop < 60;
        restoredKey.current = focusKey;
      } else if (bottom.current) el.scrollTop = el.scrollHeight;
      else setUnseen(true);
    });
    return () => cancelAnimationFrame(frame);
  }, [signature, focusKey, historyReady]);
  useEffect(() => {
    if (expanded) {
      dialog.current?.showModal();
      return () => {
        expandButton.current?.focus();
      };
    }
  }, [expanded]);
  const submit = async (compare = false) => {
    const text = question.trim();
    if (!text || posting.current || (!compare && conversationBusy)) return;
    posting.current = true;
    setBusy(true);
    setError('');
    const epoch = selectionEpoch.current;
    const atSend = focusRef.current;
    try {
      const body = { question: text, baselineReportRef: baseline ? 'atcis:report:R0' : null };
      if (compare) {
        const c = await api('comparisons', { ...body, firstKnowledgeMode: atSend.mode });
        setComparisons((old) => [c, ...old.filter((x) => x.comparisonId !== c.comparisonId)]);
        if (epoch === selectionEpoch.current) {
          navigate({ ...atSend, comparison: c.comparisonId });
          setQuestion((old) => (old.trim() === text ? '' : old));
        }
      } else {
        const r = await api('analyses', {
          ...body,
          knowledgeMode: atSend.mode,
          conversationId: atSend.conversation,
        });
        setRuns((old) => mergeRuns(old, [r]));
        if (epoch === selectionEpoch.current) {
          if (atSend.conversation !== r.conversationId)
            navigate({ ...atSend, comparison: null, conversation: r.conversationId });
          else if (atSend.comparison) navigate({ ...atSend, comparison: null });
          bottom.current = true;
          setQuestion((old) => (old.trim() === text ? '' : old));
        }
      }
    } catch (e) {
      if (epoch === selectionEpoch.current) setError(String(e));
    } finally {
      posting.current = false;
      setBusy(false);
    }
  };
  const select = async (runId: string, courseId: string) => {
    await api(`analyses/${runId}/selection`, { courseId }, 'PUT');
  };
  const groups = useMemo(() => {
    const map = new Map<string, KnowledgeRun>();
    for (const run of [...runs].sort((a, b) => a.createdAt.localeCompare(b.createdAt))) {
      if (modes.includes(run.knowledgeMode) && !map.has(run.conversationId))
        map.set(run.conversationId, run);
    }
    return [...map.values()].reverse();
  }, [runs]);
  const visible = entities.filter((e) => !filter || e.affiliation === filter);
  const selectedEntity = entities.find((e) => e.entityId === selected);
  const comparisonContent = (large = false) =>
    current ? (
      <section
        className={'bf-comparison ' + (large ? 'is-expanded' : '')}
        aria-label="A/B/C 비교 결과"
      >
        <div className="bf-comparison-heading">
          <div>
            <span className="bf-eyebrow">동일 기준 · 격리된 세 실행</span>
            <h3>A/B/C 동일 기준 비교 · {current.status}</h3>
          </div>
          {!large && (
            <button
              ref={expandButton}
              className="bf-icon"
              aria-label="비교 확대"
              onClick={() => setExpanded(true)}
            >
              <Maximize2 size={16} />
            </button>
          )}
        </div>
        <p className="bf-user-text">{current.question}</p>
        <p className="bf-meta">A↔B 지식 제공 · B↔C 구조화·규칙 재사용</p>
        {current.error && <p role="alert">{current.error}</p>}
        <details className="bf-conditions">
          <summary>공통 snapshot·지식 버전·준비 조건</summary>
          <pre>{pretty(current.manifest)}</pre>
        </details>
        <div className="knowledge-mobile" role="group" aria-label="비교군 선택">
          {modes.map((m) => (
            <button
              key={m}
              aria-label={names[m]}
              aria-pressed={mobile === m}
              onClick={() => setMobile(m)}
            >
              <b>{modes.indexOf(m) === 0 ? 'A' : modes.indexOf(m) === 1 ? 'B' : 'C'}</b>
              <span>{m === 'native' ? '원천' : m === 'documents' ? '문서' : '구조화'}</span>
            </button>
          ))}
        </div>
        <div className="knowledge-columns">
          {modes.map((m) => (
            <div key={m} className={mobile === m ? 'mobile-current' : ''}>
              <h4>{names[m]}</h4>
              <RunPanel run={runs.find((r) => r.runId === current.runIds[m])} onSelect={select} />
            </div>
          ))}
        </div>
      </section>
    ) : (
      <p className="bf-meta" role="status">
        비교 실행 조건을 불러오는 중…
      </p>
    );

  return (
    <div className="bf-shell knowledge-platform">
      <header className="bf-header">
        <button
          className="bf-icon"
          aria-label="대화 이력 열기"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen((v) => !v)}
        >
          <History size={19} />
        </button>
        <div className="bf-brand-mark">
          <MapIcon size={19} />
        </div>
        <div className="bf-brand">
          <span>BATTLEFIELD INTELLIGENCE</span>
          <h1>전장 상황판</h1>
        </div>
        <span className="bf-exercise">합성 연습 · v4</span>
        <div className="bf-connections">
          {['atcis', 'knccs'].map((s) => (
            <span
              key={s}
              className={
                connectionError || sources[s]?.connected === undefined
                  ? 'is-unknown'
                  : sources[s]?.connected
                    ? 'is-ready'
                    : 'is-error'
              }
              title={connectionError ? '연결 확인 불가' : sources[s]?.error || ''}
            >
              <i />
              {s.toUpperCase()}
              <small>
                {connectionError
                  ? '확인 불가'
                  : sources[s]?.connected === undefined
                    ? '확인 중'
                    : sources[s].connected
                      ? '연결'
                      : '단절'}
              </small>
            </span>
          ))}
        </div>
        <a className="bf-fabric" href={fabricUrl} target="_blank" rel="noreferrer">
          Data Fabric <ArrowUpRight size={13} />
        </a>
      </header>
      <main className="bf-workspace">
        <section className="bf-map" role="region" aria-label="전장 상황판">
          <div className="bf-map-toolbar">
            <div>
              <Compass size={15} />
              <strong>통합 상황</strong>
              <span>표시 객체 {visible.length}</span>
            </div>
            <button
              aria-label="객체 목록"
              aria-expanded={objectsOpen}
              onClick={() => setObjectsOpen((v) => !v)}
            >
              <Layers size={14} /> 객체
            </button>
            <button className="bf-icon" aria-label="지도 화면 맞춤" onClick={() => fit(visible)}>
              <Maximize2 size={15} />
            </button>
          </div>
          <div className="bf-map-host">
            <SituationMap
              entities={visible}
              selected={selected}
              onSelect={setSelected}
              focus={mapFocus}
              view={view}
              onView={acceptView}
              fitBounds={bounds}
              onFitted={onFitted}
            />
          </div>
          {mapError && (
            <p className="bf-map-error" role="status">
              {mapError}
            </p>
          )}
          {objectsOpen && (
            <aside className="bf-objects" aria-label="원천 객체 목록">
              <div className="bf-panel-title">
                <h2>원천 객체</h2>
                <button
                  className="bf-icon"
                  aria-label="객체 목록 닫기"
                  onClick={() => setObjectsOpen(false)}
                >
                  <X size={15} />
                </button>
              </div>
              <label>
                객체 구분
                <select
                  aria-label="객체 구분"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="">전체</option>
                  <option value="friendly">아군</option>
                  <option value="hostile">적군</option>
                  <option value="unknown">미상</option>
                </select>
              </label>
              <div className="bf-object-rows">
                {visible.map((e) => (
                  <button
                    key={e.entityId}
                    aria-pressed={selected === e.entityId}
                    onClick={() => {
                      setSelected(e.entityId);
                      setObjectsOpen(false);
                    }}
                  >
                    <span className={'bf-marker ' + e.affiliation} />
                    <div>
                      <b>{e.label || e.nativeId || e.entityId}</b>
                      <small>
                        {e.source?.toUpperCase()} · {e.unitId || '소속 정보 없음'}
                      </small>
                    </div>
                  </button>
                ))}
                {!visible.length && <p className="bf-meta">표시할 객체 없음</p>}
              </div>
            </aside>
          )}
          {selectedEntity && (
            <aside className="bf-object-detail" aria-label="선택 객체">
              <div className="bf-panel-title">
                <strong>{selectedEntity.label || selectedEntity.entityId}</strong>
                <button
                  className="bf-icon"
                  aria-label="객체 선택 해제"
                  onClick={() => setSelected(null)}
                >
                  <X size={14} />
                </button>
              </div>
              <p>
                {selectedEntity.source?.toUpperCase()} ·{' '}
                {selectedEntity.nativeId || selectedEntity.entityId}
              </p>
              <p className="bf-coordinate">
                {selectedEntity.position.latitude.toFixed(4)}° N ·{' '}
                {selectedEntity.position.longitude.toFixed(4)}° E
              </p>
              <small>
                관측{' '}
                {selectedEntity.observedAt ? formatTime(selectedEntity.observedAt) : '정보 없음'}
              </small>
              <details>
                <summary>원천 상태</summary>
                <pre>{pretty(selectedEntity.nativeStatus ?? '정보 없음')}</pre>
              </details>
              <button onClick={() => setMapFocus((n) => n + 1)}>
                <Target size={12} /> 대상 위치로 이동
              </button>
            </aside>
          )}
          <div className="bf-map-caption">
            <span>
              <i className="bf-marker friendly" /> 아군
            </span>
            <span>
              <i className="bf-marker hostile" /> 적군
            </span>
            <span>
              <i className="bf-marker unknown" /> 미상
            </span>
            <span>WGS84</span>
          </div>
        </section>
        <section className="bf-chat" aria-label="AI 분석 채팅">
          <div className="bf-chat-header">
            <div>
              <MessageSquare size={17} />
              <h2>AI 분석</h2>
              <span className="bf-mode-badge">
                {modes.indexOf(focus.mode) === 0
                  ? 'A'
                  : modes.indexOf(focus.mode) === 1
                    ? 'B'
                    : 'C'}
              </span>
            </div>
            {focus.comparison && (
              <button
                className="bf-icon"
                aria-label="대화로 돌아가기"
                onClick={() => navigate({ ...focus, comparison: null })}
              >
                <X size={16} />
              </button>
            )}
            <button
              className="bf-icon"
              aria-label="새 대화"
              title="새 대화"
              onClick={() => {
                navigate({ mode: focus.mode, conversation: null, comparison: null });
                editor.current?.focus();
              }}
            >
              <Plus size={19} />
            </button>
          </div>
          <div
            className="bf-chat-scroll"
            ref={timelineRef}
            aria-label="대화 타임라인"
            onScroll={() => {
              const el = timelineRef.current;
              if (!el) return;
              bottom.current = el.scrollHeight - el.clientHeight - el.scrollTop < 60;
              positions.current[focusKey] = el.scrollTop;
              if (bottom.current) setUnseen(false);
              persist(focus, view, selected);
            }}
          >
            {notice && (
              <div className="bf-notice" role="status">
                {notice}
                <button className="bf-icon" aria-label="안내 닫기" onClick={() => setNotice('')}>
                  <X size={12} />
                </button>
              </div>
            )}
            {focus.comparison ? (
              comparisonContent()
            ) : timeline.length ? (
              timeline.map((run) => (
                <article className="bf-turn" key={run.runId} data-run-id={run.runId}>
                  <div className="bf-user-message" data-message-role="user">
                    <span>사용자</span>
                    <p>{run.question}</p>
                  </div>
                  <div className="bf-assistant-message" data-message-role="assistant">
                    <div className="bf-agent-label">
                      <MessageSquare size={14} />
                      <b>분석 Agent</b>
                      <span>{statusName[run.status] || run.status}</span>
                    </div>
                    {['queued', 'running'].includes(run.status) && (
                      <p className="bf-progress" role="status">
                        <i />
                        {progress(run)}
                      </p>
                    )}
                    <RunPanel run={run} onSelect={select} />
                    <details className="bf-conditions">
                      <summary>실행 조건·버전</summary>
                      <pre>
                        {pretty({
                          runId: run.runId,
                          mode: run.knowledgeMode,
                          knowledgeSetVersion: run.knowledgeSetVersion,
                          graphInfo: run.graphInfo,
                        })}
                      </pre>
                    </details>
                  </div>
                </article>
              ))
            ) : (
              <div className="bf-empty">
                <span className="bf-eyebrow">상황에서 질문으로</span>
                <h3>현재 상황을 질문하세요</h3>
                <p>
                  지도를 보며 원천 기록과 근거를 확인하고,
                  <br />
                  분석을 이어갈 수 있습니다.
                </p>
                <button
                  onClick={() => {
                    setQuestion(domainScenarios[5][1]);
                    editor.current?.focus();
                  }}
                >
                  가용 전차와 제한 사항 <ArrowUpRight size={13} />
                </button>
                <button
                  onClick={() => {
                    setQuestion(domainScenarios[2][1]);
                    editor.current?.focus();
                  }}
                >
                  사건 진행 상황 <ArrowUpRight size={13} />
                </button>
              </div>
            )}
          </div>
          {unseen && (
            <button
              className="bf-new-message"
              onClick={() => {
                bottom.current = true;
                timelineRef.current?.scrollTo({
                  top: timelineRef.current.scrollHeight,
                  behavior: 'smooth',
                });
                setUnseen(false);
              }}
            >
              <ArrowDown size={13} /> 새 내용 보기
            </button>
          )}
          <div className="bf-composer">
            {error && (
              <p role="alert" className="bf-error">
                {error}
              </p>
            )}
            <div className="bf-composer-controls">
              <label className="bf-mode-select">
                <select
                  aria-label="지식 제공 방식"
                  title={descriptions[focus.mode]}
                  value={focus.mode}
                  onChange={(e) =>
                    navigate({ mode: e.target.value as Mode, conversation: null, comparison: null })
                  }
                >
                  {modes.map((m) => (
                    <option value={m} key={m}>
                      {names[m]}
                    </option>
                  ))}
                </select>
              </label>
              <details className="bf-quick">
                <summary aria-label="분석 옵션">
                  <ChevronDown size={14} /> 옵션
                </summary>
                <div>
                  <h3>빠른 질문</h3>
                  {domainScenarios.map(([id, text]) => (
                    <button
                      key={id}
                      title={text}
                      onClick={(e) => {
                        setQuestion(text);
                        setBaseline(id === 'F5');
                        e.currentTarget.closest('details')?.removeAttribute('open');
                        editor.current?.focus();
                      }}
                    >
                      <b>{id}</b>
                      <span>{text}</span>
                    </button>
                  ))}
                  <label>
                    <input
                      type="checkbox"
                      checked={baseline}
                      onChange={(e) => setBaseline(e.target.checked)}
                    />{' '}
                    기준보고 R0 · T0/T1 비교
                  </label>
                  <p>A↔B 지식 제공 · B↔C 구조화 체계</p>
                </div>
              </details>
            </div>
            <div className="bf-input-box">
              <textarea
                ref={editor}
                aria-label="분석 질의"
                value={question}
                rows={2}
                onChange={(e) => setQuestion(e.target.value)}
                onCompositionStart={() => {
                  composing.current = true;
                }}
                onCompositionEnd={() => {
                  composing.current = false;
                }}
                onKeyDown={(e) => {
                  if (
                    e.key === 'Enter' &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing &&
                    !composing.current &&
                    e.keyCode !== 229
                  ) {
                    e.preventDefault();
                    void submit();
                  }
                }}
                placeholder="상황에 대해 질문하세요…"
              />
              <div className="bf-send-row">
                <span>
                  {baseline ? '기준보고 R0 · ' : ''}
                  {descriptions[focus.mode]}
                </span>
                <button
                  className="bf-send"
                  aria-label="분석 실행"
                  title="Enter 전송 · Shift+Enter 줄바꿈"
                  disabled={busy || !question.trim() || conversationBusy}
                  onClick={() => void submit()}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
            <button
              className="bf-compare-action"
              aria-label="동일 기준 A/B/C 비교"
              disabled={busy || !question.trim()}
              onClick={() => void submit(true)}
            >
              <Layers size={13} /> 동일 기준 A/B/C 비교 <ArrowUpRight size={12} />
            </button>
          </div>
        </section>
      </main>
      <footer className="bf-footer">
        <span>
          <Clock3 size={11} />{' '}
          {sourceTime ? '원천 관측 ' + formatTime(sourceTime) : '원천 관측 시각 확인 중'}
        </span>
        <span>읽기 전용 분석 · 명령 전송 없음</span>
      </footer>
      {historyOpen && (
        <>
          <button
            className="bf-drawer-scrim"
            aria-label="이력 배경 닫기"
            onClick={() => setHistoryOpen(false)}
          />
          <aside className="bf-history" aria-label="대화 및 비교 이력">
            <div className="bf-panel-title">
              <h2>대화 이력</h2>
              <button
                className="bf-icon"
                aria-label="이력 닫기"
                onClick={() => setHistoryOpen(false)}
              >
                <X size={17} />
              </button>
            </div>
            <button
              className="bf-history-new"
              onClick={() => navigate({ mode: focus.mode, conversation: null, comparison: null })}
            >
              <Plus size={15} /> 새 대화
            </button>
            <div className="bf-history-list">
              {groups.map((r) => (
                <button
                  key={r.conversationId}
                  aria-pressed={focus.conversation === r.conversationId}
                  onClick={() =>
                    navigate({
                      mode: r.knowledgeMode,
                      conversation: r.conversationId,
                      comparison: null,
                    })
                  }
                >
                  <small>{names[r.knowledgeMode]}</small>
                  <span>{r.question}</span>
                </button>
              ))}
              {!groups.length && <p className="bf-meta">아직 대화가 없습니다.</p>}
              <h3>비교 이력</h3>
              {comparisons.map((c) => (
                <button
                  key={c.comparisonId}
                  onClick={() => navigate({ ...focusRef.current, comparison: c.comparisonId })}
                >
                  {c.status} · {c.question}
                </button>
              ))}
            </div>
          </aside>
        </>
      )}
      {expanded && (
        <dialog
          ref={dialog}
          className="bf-comparison-dialog"
          aria-label="A/B/C 비교 확대"
          onCancel={(e) => {
            e.preventDefault();
            setExpanded(false);
          }}
        >
          <div className="bf-panel-title">
            <h2>같은 기준의 세 분석</h2>
            <button
              className="bf-icon"
              aria-label="비교 확대 닫기"
              onClick={() => setExpanded(false)}
            >
              <X size={18} />
            </button>
          </div>
          <div className="bf-dialog-content">{comparisonContent(true)}</div>
        </dialog>
      )}
    </div>
  );
}
