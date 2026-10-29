import { useEffect, useRef, useState } from 'react';
import { SituationMap, type EntityView } from './App';
import type {
  AnalysisResult,
  Claim,
  ClaimProvenance,
  SourceSnapshotSet,
} from '../generated/contracts';
import { formatTime } from './time';
import AnalysisView, { type AnalysisData } from './AnalysisView';
import './style.css';
import './NextApp.css';
import { domainScenarios } from './domainScenarios';

type Mode = 'off' | 'on';
type Evidence = {
  evidenceId: string;
  tool: string;
  systemId: string;
  data: Record<string, unknown>;
  arguments: unknown;
};
export type Run = {
  knowledgeMode?: string;
  runId: string;
  conversationId: string;
  semanticMode: Mode;
  question: string;
  trigger: string;
  status: string;
  createdAt: string;
  error?: string;
  selectedCourseId: string | null;
  result:
    | (Omit<AnalysisResult, 'claims'> & {
        claims?: (Claim & {
          provenance?: ClaimProvenance;
        })[];
      })
    | null;
  evidence: Evidence[];
  toolCalls: { name: string; status: string; arguments: unknown; response: unknown }[];
  iterations: { usage?: { input_tokens?: number; output_tokens?: number } }[];
  semanticPolicyVersion?: string;
};
type Comparison = {
  comparisonId: string;
  question: string;
  status: string;
  error?: string;
  offRunId: string | null;
  onRunId: string | null;
  manifest: {
    graphVersion: string;
    sourceSnapshotSet: SourceSnapshotSet;
    ontologyVersion: string;
    captureSpanSeconds: number;
    semanticPolicyVersion?: string;
    baselineSourceSnapshotSet?: SourceSnapshotSet;
    baselineReportRef?: string | null;
    documents?: unknown;
    modelId?: string;
    agentBudget?: unknown;
  } | null;
};
type Situation = {
  entities: (EntityView & { nativeStatus?: unknown })[];
  sources?: Record<string, { sourceTime: string }>;
};
type Connections = {
  sources: Record<string, { connected: boolean; error?: string }>;
  mcp: Record<string, { connected: boolean; error?: string }>;
};
const names: Record<string, string> = {
  available: '가용',
  unavailable: '가용 불가',
  unknown: '미확인',
  conflicting: '불일치',
  tank: '탱크',
  naval_vessel: '함정',
  uav: '무인기',
  armored_vehicle: '장갑차',
  support_vehicle: '지원 차량',
  friendly: '아군',
  hostile: '적군',
  completed: '완료',
  running: '분석 중',
  queued: '대기',
  partial: '부분 결과',
  failed: '실패',
  preparing: '기준 준비 중',
  incomplete: '불완전 비교',
};
const label = (value: string) => names[value] || value;
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
function graphRefs(value: unknown): string[] {
  if (!value || typeof value !== 'object') return [];
  if (Array.isArray(value)) return [...new Set(value.flatMap(graphRefs))];
  const object = value as Record<string, unknown>;
  const direct = Array.isArray(object.evidenceRefs)
    ? object.evidenceRefs.filter((v): v is string => typeof v === 'string')
    : [];
  return [...new Set([...direct, ...Object.values(object).flatMap(graphRefs)])];
}
type BusinessQueryData = AnalysisData & {
  queryId: string;
  title: string;
  params: Record<string, string>;
  declarationVersion: string;
  graphVersion: string;
  sourceRecords: {
    systemId: string;
    recordType: string;
    nativeId: string;
    snapshotId?: string;
    sourceTime?: string;
  }[];
};
const businessQuery = (e?: Evidence) =>
  e && typeof e.data.queryId === 'string' ? (e.data as unknown as BusinessQueryData) : null;

function TraceChain({ data, fabricUrl }: { data: BusinessQueryData; fabricUrl: string }) {
  const node = (key: string) =>
    `${fabricUrl.replace(/\/$/, '')}/?${new URLSearchParams({ graphVersion: data.graphVersion, node: key })}`;
  return (
    <ol className="next-trace-chain" aria-label="근거 추적">
      <li>
        <b>업무 질의</b> {data.title}{' '}
        <small>
          {data.queryId} · {JSON.stringify(data.params)}
        </small>
      </li>
      <li>
        <b>온톨로지 정의</b> 선언 {data.declarationVersion} · 규칙{' '}
        {data.appliedRules.map((r) => r.ruleId).join(', ')}
      </li>
      <li>
        <b>지식그래프 연결</b> {data.graphEvidence.length}개
        <div className="next-trace-edges">
          {data.graphEvidence.slice(0, 8).map((e) => (
            <a key={e.evidenceId} href={node(e.start)} target="_blank" rel="noreferrer">
              {e.kind}: {e.start.split(':').slice(-1)[0]} → {e.end.split(':').slice(-1)[0]}
            </a>
          ))}
          {data.graphEvidence.length > 8 && <small>외 {data.graphEvidence.length - 8}개</small>}
        </div>
      </li>
      <li>
        <b>원천 기록</b>{' '}
        {data.sourceRecords.map((r) => `${r.systemId}/${r.recordType}/${r.nativeId}`).join(' · ')}
        <small>
          {' '}
          · 고정 snapshot {[...new Set(data.sourceRecords.map((r) => r.snapshotId))].join(', ')}
        </small>
      </li>
    </ol>
  );
}
const KIND_LABELS: Record<string, string> = {
  observation: '원천 관측',
  inference: '모델 추론',
  semantic: 'Semantic 해석',
  calculation: '근거 계산',
};
const sourceLabel = (provenance: ClaimProvenance) =>
  provenance.sources
    .map(
      (s) =>
        ({ source: '원천', document: '문서', semantic: 'Semantic', calculation: '계산 도구' })[s] ||
        s,
    )
    .join(' · ') || '인용 없음';
function QueryEvidence({
  anchor,
  index,
  evidenceId,
  data,
  flash,
  fabricUrl,
}: {
  anchor: string;
  index?: number;
  evidenceId: string;
  data: BusinessQueryData;
  flash: boolean;
  fabricUrl: string;
}) {
  return (
    <section
      id={anchor}
      className={flash ? 'evidence-block flash' : 'evidence-block'}
      aria-label={`근거 ${index ?? ''} ${data.title}`.replace(/\s+/g, ' ')}
    >
      <header>
        <b>
          {index ? `${index}. ` : ''}
          {data.title}
        </b>{' '}
        <small>{evidenceId}</small>
      </header>
      {data.steps?.length ? (
        <>
          <AnalysisView data={data} />
          <details className="next-trace-details">
            <summary>세부 근거 (업무 질의·선언·간선·원천 기록)</summary>
            <TraceChain data={data} fabricUrl={fabricUrl} />
          </details>
        </>
      ) : (
        <TraceChain data={data} fabricUrl={fabricUrl} />
      )}
    </section>
  );
}
class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | undefined,
    body: string,
  ) {
    super(`${status}: ${body}`);
  }
}
async function api<T>(path: string, body?: object, method = 'POST'): Promise<T> {
  const response = await fetch(
    '/api/v1/' + path,
    body
      ? { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : undefined,
  );
  if (!response.ok) {
    const body = await response.text();
    let code: string | undefined;
    try {
      const data = JSON.parse(body);
      if (typeof data?.error === 'string') code = data.error;
    } catch {
      // Preserve non-JSON HTTP errors for display without retrying them.
    }
    throw new ApiError(response.status, code, body);
  }
  return response.json() as Promise<T>;
}

export function RunPanel({
  run,
  onSelect,
  loadEvidence = api,
  fabricUrl = 'http://localhost:4400',
}: {
  run?: Run;
  onSelect: (runId: string, courseId: string) => Promise<void>;
  loadEvidence?: (path: string) => Promise<unknown>;
  fabricUrl?: string;
}) {
  const [selectionError, setSelectionError] = useState('');
  const [proof, setProof] = useState<unknown>(null);
  const [proofError, setProofError] = useState('');
  const [flash, setFlash] = useState('');
  if (!run) return <p className="next-muted">실행 준비 중</p>;
  const usage = run.iterations.reduce(
    (total, i) => total + (i.usage?.input_tokens || 0) + (i.usage?.output_tokens || 0),
    0,
  );
  // Business-query evidence is shown once, in first-citation order; claims point at it.
  const queries = run.evidence.flatMap((e) => {
    const data = businessQuery(e);
    return data ? [{ evidenceId: e.evidenceId, data }] : [];
  });
  const citedIds = [...new Set((run.result?.claims || []).flatMap((c) => c.evidenceRefs))];
  const citedQueries = citedIds.flatMap((id) => queries.filter((q) => q.evidenceId === id));
  const uncitedQueries = queries.filter((q) => !citedIds.includes(q.evidenceId));
  const queryIndex = new Map(citedQueries.map((q, i) => [q.evidenceId, i + 1]));
  const queryTitle = (id: string) => queries.find((q) => q.evidenceId === id)?.data.title || id;
  const classCount = { fact: 0, judgment: 0 };
  for (const c of run.result?.claims || []) {
    if (c.provenance?.claimClass) classCount[c.provenance.claimClass] += 1;
  }
  const anchor = (id: string) => `evidence-${run.runId}-${id}`;
  const showEvidence = (id: string) => {
    setFlash(id);
    document.getElementById(anchor(id))?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    window.setTimeout(() => setFlash((current) => (current === id ? '' : current)), 1600);
  };
  return (
    <article className="next-run">
      <div className="next-meta">
        <span>{label(run.status)}</span>
        <span>
          {run.knowledgeMode || run.semanticMode.toUpperCase()} ·{' '}
          {run.knowledgeMode
            ? '지식 제공 조건'
            : run.semanticMode === 'off'
              ? '원천 도구·일반 계산'
              : 'Semantic 해석 사용'}{' '}
          · 정책 {run.semanticPolicyVersion || '이전 정책'}
        </span>
        <span>
          {run.toolCalls.length} tool · {run.iterations.length} model · {usage || '—'} tokens
        </span>
      </div>
      <p className="next-answer">
        {run.result?.answer || run.error || '원천 근거를 확인하고 있습니다.'}
      </p>
      {run.result?.findings.map((finding, i) => (
        <p key={i}>{finding.text}</p>
      ))}
      {!!run.result?.claims?.length && (
        <details>
          <summary>주장별 해석·근거</summary>
          {(classCount.fact > 0 || classCount.judgment > 0) && (
            <p className="claim-summary" aria-label="주장 분류 요약">
              계산된 사실 {classCount.fact} · 모델 판단 {classCount.judgment}
            </p>
          )}
          {citedQueries.length > 0 && (
            <section className="evidence-area" aria-label="근거">
              <b>근거 — 업무 질의가 계산한 결과</b>
              <small> 코드가 선언 규칙대로 계산했습니다. 아래 주장은 이 근거를 인용합니다.</small>
              {citedQueries.map((e, i) => (
                <QueryEvidence
                  key={e.evidenceId}
                  anchor={anchor(e.evidenceId)}
                  index={i + 1}
                  evidenceId={e.evidenceId}
                  data={e.data}
                  flash={flash === e.evidenceId}
                  fabricUrl={fabricUrl}
                />
              ))}
              {uncitedQueries.length > 0 && (
                <details className="evidence-uncited">
                  <summary>인용되지 않은 근거 {uncitedQueries.length}</summary>
                  {uncitedQueries.map((e) => (
                    <QueryEvidence
                      key={e.evidenceId}
                      anchor={anchor(e.evidenceId)}
                      evidenceId={e.evidenceId}
                      data={e.data}
                      flash={false}
                      fabricUrl={fabricUrl}
                    />
                  ))}
                </details>
              )}
            </section>
          )}
          {citedQueries.length > 0 && <b className="claim-heading">주장</b>}
          {run.result.claims.map((claim, i) => (
            <section
              className={`next-evidence${claim.provenance?.claimClass ? ' claim-' + claim.provenance.claimClass : ''}`}
              key={i}
              aria-label={
                claim.provenance?.claimClass
                  ? claim.provenance.claimClass === 'fact'
                    ? '계산된 사실'
                    : '모델 판단'
                  : undefined
              }
            >
              {claim.provenance?.claimClass ? (
                <div className="claim-head">
                  <b className="claim-badge">
                    {claim.provenance.claimClass === 'fact'
                      ? '계산된 사실 · 코드가 결정'
                      : '모델 판단 · LLM이 해석'}
                  </b>
                  {claim.provenance.claimClass === 'judgment' && (
                    <span className="claim-review">검토 필요</span>
                  )}
                </div>
              ) : (
                <b>{KIND_LABELS[claim.kind]}</b>
              )}
              {claim.provenance && !claim.provenance.claimClass && (
                <p>
                  <small>모델의 주장 분류 · 서버 확인 출처: {sourceLabel(claim.provenance)}</small>
                </p>
              )}
              <p>{claim.text}</p>
              {claim.provenance?.classReason && (
                <small
                  className="claim-reason"
                  title={`모델 분류: ${KIND_LABELS[claim.provenance.reportedKind]} · 서버 확인 출처: ${sourceLabel(claim.provenance)}`}
                >
                  {claim.provenance.classReason}
                </small>
              )}
              {claim.evidenceRefs.some((id) => queryIndex.has(id)) && (
                <div className="claim-chips">
                  {claim.evidenceRefs
                    .filter((id) => queryIndex.has(id))
                    .map((id) => (
                      <button
                        type="button"
                        key={id}
                        className="claim-chip"
                        onClick={() => showEvidence(id)}
                      >
                        근거 {queryIndex.get(id)}. {queryTitle(id)}
                      </button>
                    ))}
                </div>
              )}
              {claim.provenance &&
                !claim.provenance.sources.includes('semantic') &&
                claim.provenance.sources.includes('document') && (
                  <p className="next-trace-note">
                    정의 적용: 인용 문서를 읽은 모델의 해석(실행된 정의 아님)
                  </p>
                )}
              {claim.provenance &&
                claim.provenance.sources.length > 0 &&
                claim.provenance.sources.every((s) => s === 'source') && (
                  <p className="next-trace-note">원천 기록만 인용(추가 정의 없음)</p>
                )}
              <small>
                {claim.evidenceRefs.join(' · ')}
                {claim.ruleRefs?.length ? ` · 규칙 ${claim.ruleRefs.join(', ')}` : ''}
              </small>
              {claim.provenance?.documents.map((doc, i) => (
                <p key={i}>
                  <small>
                    문서 {doc.documentKey} · v{doc.version} · 집합 {doc.knowledgeSetVersion} · hash{' '}
                    {doc.hash}
                  </small>
                </p>
              ))}
              {!!claim.provenance?.documentRuleRefs.length && (
                <p>문서 내 규칙 표기: {claim.provenance.documentRuleRefs.join(', ')}</p>
              )}
              {!!claim.provenance?.unverifiedRuleRefs.length && (
                <p role="status">
                  확인되지 않은 규칙 표기: {claim.provenance.unverifiedRuleRefs.join(', ')}
                </p>
              )}
            </section>
          ))}
        </details>
      )}
      {!!run.result?.limitations.length && (
        <div className="next-limits">
          <b>분석 범위·한계</b>
          {run.result.limitations.map((l, i) => (
            <p key={i}>{l}</p>
          ))}
        </div>
      )}
      <details>
        <summary>도구 호출 ({run.toolCalls.length})</summary>
        {run.toolCalls.map((tool, i) => (
          <details key={i} className="next-trace">
            <summary>
              {i + 1}. {tool.name} · {label(tool.status)}
            </summary>
            <pre>{pretty(tool.arguments)}</pre>
            <pre>{pretty(tool.response)}</pre>
          </details>
        ))}
      </details>
      <details>
        <summary>관계·원천 근거</summary>
        {run.evidence.map((e) => (
          <section key={e.evidenceId} className="next-evidence">
            <div>
              <b>{e.tool}</b>
              <small>
                {e.evidenceId} · {e.systemId}
              </small>
            </div>
            {Array.isArray(e.data.paths) &&
              e.data.paths.map((p: { path?: string[] }, i) => (
                <div className="next-path" key={i}>
                  {p.path?.join(' → ')}
                </div>
              ))}
            {typeof e.data.rawRecordCount === 'number' && (
              <p>
                원천 레코드 {e.data.rawRecordCount}
                {e.data.interpretation === 'native_records_only' ? (
                  ' · 원천 필드값 집계 (의미 해석 없음)'
                ) : (
                  <>
                    {' '}
                    · 중복 제거 객체 {String(e.data.resolvedUniqueCount ?? '미확정')} · 확정 가용{' '}
                    {String(e.data.confirmedAvailable ?? '미확정')}
                    {Number(e.data.conflicting) > 0 && <> · 불일치 {String(e.data.conflicting)}</>}
                  </>
                )}
              </p>
            )}
            {e.data.typeStatusCounts && typeof e.data.typeStatusCounts === 'object' ? (
              <table aria-label="유형 및 상태별 집계">
                <thead>
                  <tr>
                    <th>유형</th>
                    <th>상태별 객체 수</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(e.data.typeStatusCounts).map(([kind, counts]) => (
                    <tr key={kind}>
                      <td>{label(kind)}</td>
                      <td>{pretty(counts)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {e.systemId === 'semantic' && (
              <div className="next-proof-links">
                {graphRefs(e.data).map((id, index) => (
                  <button
                    key={id}
                    onClick={() => {
                      setProofError('');
                      void loadEvidence(
                        `analyses/${run.runId}/semantic-evidence/${encodeURIComponent(id)}`,
                      )
                        .then(setProof)
                        .catch((error) => setProofError(String(error)));
                    }}
                  >
                    관계 근거 {index + 1} 원문
                  </button>
                ))}
              </div>
            )}
            <details>
              <summary>근거 데이터 열기</summary>
              <pre>{pretty(e.data)}</pre>
            </details>
          </section>
        ))}
      </details>
      {proofError && <p role="alert">{proofError}</p>}
      {proof !== null && (
        <details open>
          <summary>Graph 근거 원문 · 규칙·원천 snapshot</summary>
          <pre>{pretty(proof)}</pre>
        </details>
      )}
      {run.result?.courses && (
        <details>
          <summary>세 방책 비교·선택</summary>
          <div className="next-courses">
            {run.result.courses.map((c) => (
              <article key={c.id}>
                <h4>{c.title}</h4>
                <p>{c.summary}</p>
                <p>{c.expectedEffects.join(' · ')}</p>
                <p>{c.risksAndConstraints.join(' · ')}</p>
                <button
                  onClick={() => {
                    setSelectionError('');
                    void onSelect(run.runId, c.id).catch((e) => setSelectionError(String(e)));
                  }}
                >
                  {run.selectedCourseId === c.id ? '선택됨' : '이 방책 선택'}
                </button>
              </article>
            ))}
          </div>
          {selectionError && <p role="alert">{selectionError}</p>}
        </details>
      )}
      <small className="next-muted">실행 {run.runId}</small>
    </article>
  );
}

export default function NextApp({ domain = false }: { domain?: boolean }) {
  const [baselineReportRef, setBaselineReportRef] = useState('atcis:report:R0');
  const [situation, setSituation] = useState<Situation>({ entities: [] });
  const [connections, setConnections] = useState<Connections>({ sources: {}, mcp: {} });
  const [runs, setRuns] = useState<Run[]>([]);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [mode, setMode] = useState<Mode>(
    sessionStorage.getItem('vnext.mode') === 'on' ? 'on' : 'off',
  );
  const [conversation, setConversation] = useState<string | null>(
    sessionStorage.getItem('vnext.conversation'),
  );
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState('');
  const [kind, setKind] = useState('');
  const [affiliation, setAffiliation] = useState('');
  const [comparisonId, setComparisonId] = useState<string | null>(null);
  const [mobileMode, setMobileMode] = useState<Mode>('off');
  const closeButton = useRef<HTMLButtonElement>(null);
  const [view, setView] = useState({
    center: [126.5, 37.8] as [number, number],
    zoom: 7,
    bearing: 0,
  });
  const [semanticStatus, setSemanticStatus] = useState('사용 안 함');
  const refresh = async () => {
    const [s, r, c, status] = await Promise.all([
      api<Situation>('situation'),
      api<{ items: Run[] }>('analyses'),
      api<{ items: Comparison[] }>('comparisons'),
      api<Connections>('sources'),
    ]);
    setSituation(s);
    setRuns(r.items);
    setComparisons(c.items);
    setConnections(status);
  };
  useEffect(() => {
    let active = true;
    const update = () => {
      if (active) void refresh().catch((e) => setError(String(e)));
    };
    update();
    const timer = setInterval(update, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (mode === 'off' && !comparisonId) {
      setSemanticStatus('사용 안 함');
      return;
    }
    let active = true;
    const update = () => {
      void api<{ status: string; graphVersion?: string }>('semantic/status')
        .then((s) => {
          if (active)
            setSemanticStatus(
              s.status === 'READY' ? `준비됨 · ${s.graphVersion?.slice(0, 14)}` : s.status,
            );
        })
        .catch(() => {
          if (active) setSemanticStatus('연결 실패 / Graph 미준비');
        });
    };
    update();
    const timer = setInterval(update, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [mode, comparisonId]);
  useEffect(() => {
    if (comparisonId) closeButton.current?.focus();
  }, [comparisonId]);
  const changeMode = (value: Mode) => {
    setMode(value);
    sessionStorage.setItem('vnext.mode', value);
    setConversation(null);
    sessionStorage.removeItem('vnext.conversation');
  };
  const submit = async (compare: boolean) => {
    if (!question.trim()) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (compare) {
        const c = await api<Comparison>('comparisons', {
          question,
          ...(domain ? { baselineReportRef: baselineReportRef || null } : {}),
        });
        setComparisons((prev) => [c, ...prev]);
        setComparisonId(c.comparisonId);
      } else {
        let run: Run;
        try {
          run = await api<Run>('analyses', {
            question,
            semanticMode: mode,
            conversationId: conversation,
            ...(domain ? { baselineReportRef: baselineReportRef || null } : {}),
          });
        } catch (e) {
          if (
            !conversation ||
            !(e instanceof ApiError) ||
            e.status !== 404 ||
            e.code !== 'conversation_not_found'
          )
            throw e;
          // The server rejected the stale ID before enqueueing any run. Retry once.
          setConversation(null);
          sessionStorage.removeItem('vnext.conversation');
          setNotice('이전 대화가 현재 서버에 없어 새 대화로 시작했습니다.');
          run = await api<Run>('analyses', {
            question,
            semanticMode: mode,
            conversationId: null,
            ...(domain ? { baselineReportRef: baselineReportRef || null } : {}),
          });
        }
        setConversation(run.conversationId);
        sessionStorage.setItem('vnext.conversation', run.conversationId);
      }
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const selectCourse = async (runId: string, courseId: string) => {
    await api('analyses/' + runId + '/selection', { courseId }, 'PUT');
    await refresh();
  };
  const filtered = situation.entities.filter(
    (e) =>
      (!sourceFilter || e.source === sourceFilter) &&
      (!kind || e.kind === kind) &&
      (!affiliation || e.affiliation === affiliation),
  );
  const object = situation.entities.find((e) => e.entityId === selected);
  const comparison = comparisons.find((c) => c.comparisonId === comparisonId);
  const currentRuns = runs
    .filter((r) => r.conversationId === conversation && r.semanticMode === mode)
    .slice()
    .reverse();
  return (
    <div className="next-shell">
      <header className="next-header">
        <div>
          <span className="next-kicker">BATTLEFIELD INTELLIGENCE · SYNTHETIC</span>
          <h1>통합 상황판</h1>
        </div>
        <div className="next-connections">
          {['atcis', 'knccs'].map((s) => (
            <div key={s}>
              <b>{s.toUpperCase()}</b>
              <span>수집 {connections.sources[s]?.connected ? '연결' : '미연결'}</span>
              <span>MCP {connections.mcp[s]?.connected ? '연결' : '미확인'}</span>
            </div>
          ))}
          <div>
            <b>SEMANTIC</b>
            <span>{semanticStatus}</span>
          </div>
        </div>
      </header>
      {error && (
        <div role="alert" className="next-error">
          {error}
          <button onClick={() => setError('')}>알림 닫기</button>
        </div>
      )}
      <main className="next-workspace">
        <aside className="next-sidebar">
          <h2>원천 객체</h2>
          <small>
            원천 레코드 {situation.entities.length} · 현재 표시 {filtered.length}
          </small>
          <label>
            원천 필터
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
              <option value="">전체 체계</option>
              <option value="atcis">ATCIS</option>
              <option value="knccs">KNCCS</option>
            </select>
          </label>
          <label>
            유형 필터
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">전체 유형</option>
              {['tank', 'naval_vessel', 'uav', 'armored_vehicle', 'support_vehicle'].map((k) => (
                <option key={k} value={k}>
                  {label(k)}
                </option>
              ))}
            </select>
          </label>
          <label>
            소속 필터
            <select value={affiliation} onChange={(e) => setAffiliation(e.target.value)}>
              <option value="">전체 소속</option>
              <option value="friendly">아군</option>
              <option value="hostile">적군</option>
            </select>
          </label>
          <div className="next-object-list">
            {filtered.map((e) => (
              <button
                key={e.entityId}
                className={selected === e.entityId ? 'active' : ''}
                onClick={() => setSelected(e.entityId)}
              >
                <b>{e.label}</b>
                <span>
                  {e.source?.toUpperCase()} · {label(e.kind)} ·{' '}
                  {domain ? JSON.stringify(e.nativeStatus ?? '미확인') : label(e.availability)}
                </span>
              </button>
            ))}
          </div>
          {object && (
            <section className="next-object-detail">
              <h3>{object.label}</h3>
              <p>
                {object.source} · {object.unitId}
              </p>
              <p>
                {object.position.longitude.toFixed(5)}, {object.position.latitude.toFixed(5)}
              </p>
              <p>
                {label(object.affiliation)} ·{' '}
                {domain
                  ? JSON.stringify(object.nativeStatus ?? '미확인')
                  : label(object.availability)}
              </p>
              <small>실시간 원천 관측 · Graph 병합 위치 아님</small>
            </section>
          )}
          <h2>비교 이력</h2>
          {comparisons.map((c) => (
            <button
              className="next-history"
              key={c.comparisonId}
              aria-label="비교 이력 열기"
              onClick={() => setComparisonId(c.comparisonId)}
            >
              <span>{c.question}</span>
              <small>{label(c.status)}</small>
            </button>
          ))}
          <h2>분석 이력</h2>
          {runs.slice(0, 20).map((run) => (
            <button
              key={run.runId}
              className="next-history"
              aria-label="분석 이력 열기"
              onClick={() => {
                setMode(run.semanticMode);
                setConversation(run.conversationId);
                sessionStorage.setItem('vnext.mode', run.semanticMode);
                if (run.conversationId)
                  sessionStorage.setItem('vnext.conversation', run.conversationId);
                else sessionStorage.removeItem('vnext.conversation');
              }}
            >
              <span>
                {run.trigger === 'c4i_event' ? '원천 이벤트 자동 분석' : run.question.slice(0, 42)}
              </span>
              <small>
                Semantic {run.semanticMode.toUpperCase()} · {label(run.status)}
              </small>
            </button>
          ))}
        </aside>
        <section className="map-main">
          <SituationMap
            entities={filtered}
            selected={selected}
            onSelect={setSelected}
            focus={0}
            view={view}
            onView={setView}
            fitBounds={null}
            onFitted={() => {}}
            scenario={{
              scenarioId: 'semantic-demo-v1',
              version: 1,
              name: '지상·해상 통합 모의 상황',
              initialBounds: [125.3, 37.3, 127.5, 38.5],
              zones: [],
            }}
          />
        </section>
        <section className="next-analysis">
          <div className="next-analysis-header">
            <h2>상황 분석</h2>
            <button
              onClick={() => {
                setConversation(null);
                sessionStorage.removeItem('vnext.conversation');
              }}
            >
              새 대화
            </button>
          </div>
          <div className="next-mode" role="group" aria-label="Semantic 모드">
            {(['off', 'on'] as Mode[]).map((m) => (
              <button
                key={m}
                aria-pressed={mode === m}
                onClick={() => {
                  if (mode !== m) changeMode(m);
                }}
              >
                Semantic {m.toUpperCase()}
              </button>
            ))}
          </div>
          <small className="next-muted">
            모드 변경은 새 대화를 시작합니다. 분석 기준은 실행별로 고정됩니다.
          </small>
          <div className="next-conversation">
            {currentRuns.length ? (
              currentRuns.map((run) => (
                <section key={run.runId}>
                  <p className="next-question">{run.question}</p>
                  <RunPanel run={run} onSelect={selectCourse} />
                </section>
              ))
            ) : (
              <p className="next-muted">조직 소속·장비 현황·원천 간 정보 차이를 질의하세요.</p>
            )}
          </div>
          {notice && <p role="status">{notice}</p>}
          <label htmlFor="next-question">분석 질의</label>
          {domain && (
            <label>
              기준보고
              <select
                value={baselineReportRef}
                onChange={(e) => setBaselineReportRef(e.target.value)}
              >
                <option value="">기준보고 선택 안 함</option>
                <option value="atcis:report:R0">R0 · T0 기준보고</option>
              </select>
            </label>
          )}
          {domain && (
            <details>
              <summary>시연 질의 F1–F7</summary>
              {domainScenarios.map(([id, text]) => (
                <button key={id} onClick={() => setQuestion(text)}>
                  {id} · {text}
                </button>
              ))}
            </details>
          )}
          <textarea
            id="next-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="모의 1사단의 가용한 탱크를 보여줘."
          />
          <div className="next-submit">
            <button disabled={busy || !question.trim()} onClick={() => void submit(false)}>
              질의 실행
            </button>
            <button disabled={busy || !question.trim()} onClick={() => void submit(true)}>
              동일 기준으로 비교
            </button>
          </div>
        </section>
      </main>
      {comparisonId && (
        <div className="next-overlay">
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Semantic ON/OFF 비교"
            className="next-dialog"
            onKeyDown={(e) => {
              if (e.key === 'Escape') setComparisonId(null);
              if (e.key === 'Tab') {
                const focusable = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    'button,select,input,textarea,summary,a[href]',
                  ),
                ).filter(
                  (element) => element.offsetParent !== null && !element.hasAttribute('disabled'),
                );
                const first = focusable[0],
                  last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                }
                if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <header>
              <div>
                <h2>Semantic ON/OFF 비교</h2>
                <p>{comparison?.question}</p>
              </div>
              <button ref={closeButton} onClick={() => setComparisonId(null)}>
                비교 닫기
              </button>
            </header>
            <div className="next-comparison-meta">
              <b>
                {comparison?.status === 'completed'
                  ? '완전 비교'
                  : label(comparison?.status || 'preparing')}
              </b>
              {comparison?.manifest && (
                <>
                  <span>
                    Graph {comparison.manifest.graphVersion} · Ontology{' '}
                    {comparison.manifest.ontologyVersion}
                    {' · 정책 '}
                    {comparison.manifest.semanticPolicyVersion || '이전 정책'}
                  </span>
                  {Object.entries(comparison.manifest.sourceSnapshotSet).map(([system, ref]) => (
                    <span key={system}>
                      {system.toUpperCase()} · {ref.datasetId} · snapshot{' '}
                      {ref.snapshotId.slice(0, 12)} · {formatTime(ref.sourceTime)}
                    </span>
                  ))}
                  <details>
                    <summary>공통 비교 조건·문서·기준보고</summary>
                    <pre>
                      {pretty({
                        baselineReportRef: comparison.manifest.baselineReportRef,
                        baselineSourceSnapshotSet: comparison.manifest.baselineSourceSnapshotSet,
                        documents: comparison.manifest.documents,
                        model: comparison.manifest.modelId,
                        budget: comparison.manifest.agentBudget,
                      })}
                    </pre>
                  </details>
                </>
              )}
              {comparison?.error && <p role="alert">{comparison.error}</p>}
            </div>
            <div className="next-mobile-tabs">
              {(['off', 'on'] as Mode[]).map((m) => (
                <button
                  key={m}
                  aria-label={m.toUpperCase() + ' 비교 보기'}
                  aria-pressed={mobileMode === m}
                  onClick={() => setMobileMode(m)}
                >
                  Semantic {m.toUpperCase()} ·{' '}
                  {label(
                    runs.find((r) => r.runId === comparison?.[m === 'off' ? 'offRunId' : 'onRunId'])
                      ?.status || 'queued',
                  )}
                </button>
              ))}
            </div>
            <div className="next-compare-columns">
              {(['off', 'on'] as Mode[]).map((m) => (
                <section
                  key={m}
                  className={mobileMode === m ? 'mobile-active' : ''}
                  data-testid={'comparison-' + m}
                >
                  <h3>Semantic {m.toUpperCase()}</h3>
                  <p className="next-muted">
                    {m === 'off' ? '원천 C4I MCP' : '원천 C4I MCP + Semantic MCP'}
                  </p>
                  <RunPanel
                    key={comparison?.[m === 'off' ? 'offRunId' : 'onRunId'] || m}
                    run={runs.find(
                      (r) => r.runId === comparison?.[m === 'off' ? 'offRunId' : 'onRunId'],
                    )}
                    onSelect={selectCourse}
                  />
                </section>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
