import { useCallback, useEffect, useState } from 'react';

type Editable = {
  path: string;
  label: string;
  type: string;
  options: Record<string, string>;
  description: string;
  value: string;
};
type Rule = { ruleId: string; title: string; dependsOn: string[]; documentKey: string };
type Query = { queryId: string; title: string; description: string; rules: string[] };
type History = {
  knowledgeSetVersion: string;
  declarationVersion: string;
  author: string;
  approver: string;
  publishedAt: string;
  diff: Change[];
};
type Change = { path: string; label: string; before: string; after: string };
type Ontology = {
  knowledgeSetVersion: string;
  declarationVersion: string;
  declaration: { title: string; rules: Rule[]; businessQueries: Query[] };
  editable: Editable[];
  history: History[];
};
type PreviewRow = {
  queryId: string;
  title: string;
  params: Record<string, string>;
  before: unknown;
  after: unknown;
};
type Draft = {
  draftId: string;
  declarationVersion: string;
  baseDeclarationVersion: string;
  diff: Change[];
  impact: {
    rules: string[];
    dependentRules: string[];
    businessQueries: string[];
    screens: string[];
    terms: string[];
  };
  preview?: { rows: PreviewRow[]; error?: string; graphVersion?: string };
};

const screenLabels: Record<string, string> = {
  'object-detail': '객체 상세(C)',
  'semantic-map': '의미 상황판',
  'availability-answer': 'C 가용 현황 답변',
};
const summary = (value: unknown) => {
  if (value && typeof value === 'object' && 'available' in value) {
    const v = value as { available: number; total: number; byStatus: Record<string, number> };
    return `가용 ${v.available} / 전체 ${v.total} · ${Object.entries(v.byStatus)
      .map(([k, n]) => `${k} ${n}`)
      .join(', ')}`;
  }
  return JSON.stringify(value);
};

export default function OntologyEditor({ token }: { token: string }) {
  const [ontology, setOntology] = useState<Ontology | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [author, setAuthor] = useState('');
  const [approver, setApprover] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [published, setPublished] = useState<History | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const call = useCallback(
    async (path: string, body?: unknown) => {
      const r = await fetch('/v1/' + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
      return r.json();
    },
    [token],
  );
  const load = useCallback(async () => {
    setError('');
    try {
      const value: Ontology = await call('ontology');
      setOntology(value);
      setEdits(Object.fromEntries(value.editable.map((e) => [e.path, e.value])));
    } catch (e) {
      setError(String(e));
    }
  }, [call]);
  useEffect(() => {
    void load();
  }, [load]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  if (!ontology)
    return (
      <div className="onto">
        {error ? <p role="alert">{error}</p> : <p role="status">온톨로지 선언을 불러오는 중</p>}
      </div>
    );
  const changed = ontology.editable.filter((e) => edits[e.path] !== e.value);
  return (
    <div className="onto">
      <p className="onto-version">
        현재 선언 <b>{ontology.declarationVersion}</b> · 지식 집합{' '}
        <code>{ontology.knowledgeSetVersion}</code>
      </p>
      <p>
        이 선언 하나에서 B의 Fabric 문서(ONTOLOGY-01)와 C의 지식그래프 규칙·업무 질의가 함께
        생성됩니다. 편집은 검토된 항목만 가능하며, 승인 후 새 버전으로 발행됩니다. 기존 버전과 이미
        끝난 분석은 바뀌지 않습니다.
      </p>
      <section className="onto-card">
        <h3>1. 정의 편집</h3>
        {ontology.editable.map((item) => (
          <label key={item.path} className="onto-field">
            <span>
              {item.label} <small>현재 {item.value}</small>
            </span>
            <select
              value={edits[item.path]}
              onChange={(e) => {
                setEdits({ ...edits, [item.path]: e.target.value });
                setDraft(null);
                setPublished(null);
              }}
            >
              {Object.entries(item.options).map(([value, text]) => (
                <option key={value} value={value}>
                  {value} · {text}
                </option>
              ))}
            </select>
            <small>{item.description}</small>
          </label>
        ))}
        <label className="onto-field">
          <span>작성자</span>
          <input value={author} onChange={(e) => setAuthor(e.target.value)} />
        </label>
        <button
          disabled={busy || !changed.length || !author}
          onClick={() =>
            void run(async () => {
              setPublished(null);
              setDraft(
                await call('ontology/drafts', {
                  edits: Object.fromEntries(changed.map((e) => [e.path, edits[e.path]])),
                  author,
                }),
              );
            })
          }
        >
          초안 검증·영향 분석
        </button>
      </section>
      {draft && (
        <section className="onto-card" aria-label="영향 분석">
          <h3>
            2. 영향 분석 · {draft.baseDeclarationVersion} → {draft.declarationVersion}
          </h3>
          <table>
            <thead>
              <tr>
                <th>항목</th>
                <th>변경 전</th>
                <th>변경 후</th>
              </tr>
            </thead>
            <tbody>
              {draft.diff.map((d) => (
                <tr key={d.path}>
                  <td>{d.label}</td>
                  <td>{d.before}</td>
                  <td>{d.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="onto-impact">
            <li>변경 규칙: {draft.impact.rules.join(', ') || '없음'}</li>
            <li>의존 규칙: {draft.impact.dependentRules.join(', ') || '없음'}</li>
            <li>영향 업무 질의: {draft.impact.businessQueries.join(', ') || '없음'}</li>
            <li>
              영향 화면:{' '}
              {draft.impact.screens.map((s) => screenLabels[s] || s).join(', ') || '없음'}
            </li>
            <li>관련 용어: {draft.impact.terms.join(', ') || '없음'}</li>
          </ul>
          <p>
            <small>
              선언된 규칙 의존과 업무 질의 참조를 따라 결정론적으로 계산했습니다(LLM 미사용).
            </small>
          </p>
          {draft.preview?.error && <p role="alert">미리보기 불가: {draft.preview.error}</p>}
          {!!draft.preview?.rows.length && (
            <table aria-label="업무 질의 전후 미리보기">
              <thead>
                <tr>
                  <th>업무 질의</th>
                  <th>현재 정의</th>
                  <th>변경 정의</th>
                </tr>
              </thead>
              <tbody>
                {draft.preview.rows.map((row, i) => (
                  <tr key={i}>
                    <td>
                      {row.title}
                      <br />
                      <small>{JSON.stringify(row.params)}</small>
                    </td>
                    <td>{summary(row.before)}</td>
                    <td>{summary(row.after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h3>3. 승인·발행</h3>
          <label className="onto-field">
            <span>승인자 (작성자와 달라야 함)</span>
            <input value={approver} onChange={(e) => setApprover(e.target.value)} />
          </label>
          <button
            disabled={busy || !approver || approver === author}
            onClick={() =>
              void run(async () => {
                setPublished(await call(`ontology/drafts/${draft.draftId}/approve`, { approver }));
                setDraft(null);
                await load();
              })
            }
          >
            승인·발행
          </button>
          <p>
            <small>데모용 승인 단계이며 운영 인증이 아닙니다.</small>
          </p>
        </section>
      )}
      {published && (
        <p role="status" className="onto-published">
          발행 완료 · 선언 {published.declarationVersion} · 지식 집합{' '}
          <code>{published.knowledgeSetVersion}</code>. 새 대화부터 이 버전이 B 문서와 C
          지식그래프에 함께 적용됩니다. 진행 중인 대화는 시작할 때의 버전을 유지합니다.
        </p>
      )}
      <section className="onto-card">
        <h3>업무 질의 ({ontology.declaration.businessQueries.length})</h3>
        {ontology.declaration.businessQueries.map((q) => (
          <details key={q.queryId}>
            <summary>
              {q.title} <small>{q.queryId}</small>
            </summary>
            <p>{q.description}</p>
            <small>규칙 {q.rules.join(', ')}</small>
          </details>
        ))}
        <h3>규칙 ({ontology.declaration.rules.length})</h3>
        <ul className="onto-rules">
          {ontology.declaration.rules.map((r) => (
            <li key={r.ruleId}>
              <b>{r.ruleId}</b> {r.title}
              {r.dependsOn.length ? <small> · 의존 {r.dependsOn.join(', ')}</small> : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="onto-card">
        <h3>발행 이력</h3>
        {ontology.history.length ? (
          <table>
            <thead>
              <tr>
                <th>선언</th>
                <th>변경</th>
                <th>작성·승인</th>
                <th>발행 시각</th>
              </tr>
            </thead>
            <tbody>
              {[...ontology.history].reverse().map((h) => (
                <tr key={h.knowledgeSetVersion}>
                  <td>{h.declarationVersion}</td>
                  <td>{h.diff.map((d) => `${d.label}: ${d.before}→${d.after}`).join('; ')}</td>
                  <td>
                    {h.author} / {h.approver}
                  </td>
                  <td>{new Date(h.publishedAt).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>아직 발행된 변경이 없습니다. 기본 선언을 사용 중입니다.</p>
        )}
      </section>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
