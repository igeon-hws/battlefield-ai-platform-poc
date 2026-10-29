import { useMemo, useState } from 'react';

export type AnalysisStep = {
  step: number;
  title: string;
  detail: string;
  ruleIds: string[];
  count: number | null;
  nodeKeys: string[];
};
export type AnalysisData = {
  appliedRules: { ruleId: string; title?: string }[];
  graphEvidence: { evidenceId: string; kind: string; start: string; end: string; role?: string }[];
  steps?: AnalysisStep[];
  excluded?: { key: string; name: string; reason: string; ruleId: string; step: number }[];
  graphNodes?: { key: string; name: string; concept: string | null; state: string | null }[];
  relationLabels?: Record<string, string>;
  roleLabels?: Record<string, string>;
};

const STATE_LABELS: Record<string, string> = {
  available: '가용',
  limited: '제한',
  unavailable: '불가',
  unknown: '미상',
  excluded: '제외',
};
const W = 420;
const ROW = 78;
const BOX_H = 36;

// Layered layout: a node sits one row below everything it points to (child → parent).
function layout(keys: string[], edges: { start: string; end: string }[]) {
  const out = new Map<string, string[]>();
  for (const e of edges) out.set(e.start, [...(out.get(e.start) || []), e.end]);
  const rank = new Map<string, number>();
  const visit = (key: string, seen: Set<string>): number => {
    if (rank.has(key)) return rank.get(key)!;
    if (seen.has(key)) return 0;
    seen.add(key);
    const ends = (out.get(key) || []).filter((k) => keys.includes(k));
    const value = ends.length ? 1 + Math.max(...ends.map((k) => visit(k, seen))) : 0;
    rank.set(key, value);
    return value;
  };
  keys.forEach((k) => visit(k, new Set()));
  const rows: string[][] = [];
  keys.forEach((k) => (rows[rank.get(k)!] ||= []).push(k));
  const position = new Map<string, { x: number; y: number; w: number }>();
  rows.forEach((row, r) => {
    if (r > 0) {
      const center = (k: string) => {
        const xs = (out.get(k) || []).map((e) => position.get(e)?.x).filter((x) => x !== undefined);
        return xs.length ? xs.reduce((a, b) => a + b!, 0)! / xs.length : W / 2;
      };
      row.sort((a, b) => center(a) - center(b));
    }
    const slot = W / row.length;
    row.forEach((k, i) =>
      position.set(k, { x: slot * (i + 0.5), y: 20 + r * ROW, w: Math.min(120, slot - 8) }),
    );
  });
  return { position, height: 20 + rows.length * ROW };
}

const clip = (text: string, width: number) => {
  const max = Math.max(3, Math.floor(width / 10));
  return text.length > max ? text.slice(0, max - 1) + '…' : text;
};

export default function AnalysisView({ data }: { data: AnalysisData }) {
  const [selected, setSelected] = useState<number | null>(null);
  const steps = data.steps || [];
  const nodes = data.graphNodes || [];
  const ruleTitle = (id: string) => data.appliedRules.find((r) => r.ruleId === id)?.title || id;
  const { position, height } = useMemo(
    () =>
      layout(
        nodes.map((n) => n.key),
        data.graphEvidence,
      ),
    [nodes, data.graphEvidence],
  );
  const focus = selected === null ? null : new Set(steps[selected - 1]?.nodeKeys || []);
  const lit = (key: string) => !focus || focus.has(key);
  return (
    <section className="analysis-view" aria-label="분석 과정">
      <div className="analysis-steps">
        <b>분석 과정</b>
        <small>
          {' '}
          업무 질의가 선언 규칙대로 계산한 순서입니다. 단계를 누르면 그래프에서 강조됩니다.
        </small>
        <ol>
          {steps.map((s) => (
            <li key={s.step}>
              <button
                type="button"
                aria-pressed={selected === s.step}
                onClick={() => setSelected(selected === s.step ? null : s.step)}
              >
                <span className="analysis-step-head">
                  <b>
                    {s.step}. {s.title}
                  </b>
                  {s.count !== null && <span className="analysis-count">{s.count}</span>}
                </span>
                <span>{s.detail}</span>
                <small>규칙: {s.ruleIds.map(ruleTitle).join(', ')}</small>
              </button>
            </li>
          ))}
        </ol>
        {data.excluded && data.excluded.length > 0 && (
          <div className="analysis-excluded" aria-label="제외 항목">
            <b>제외 {data.excluded.length}건</b>
            <ul>
              {data.excluded.map((e) => (
                <li key={e.key}>
                  <span>{e.name}</span> {e.reason}{' '}
                  <small>
                    ({e.step}단계 · {ruleTitle(e.ruleId)})
                  </small>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <figure className="analysis-graph">
        <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label="분석에 쓰인 지식그래프">
          {data.graphEvidence.map((e) => {
            const a = position.get(e.start);
            const b = position.get(e.end);
            if (!a || !b) return null;
            const on = lit(e.start) && lit(e.end);
            const dashed = [e.start, e.end].some(
              (k) => nodes.find((n) => n.key === k)?.state === 'excluded',
            );
            // The role says more than the generic relation name (편제 vs 배정(역할 포함)).
            const label = e.role
              ? data.roleLabels?.[e.role] || e.role
              : data.relationLabels?.[e.kind] || e.kind;
            // Near the lower node, where fanned-out edges are furthest apart.
            const t = 0.3;
            return (
              <g key={e.evidenceId} className={on ? 'analysis-edge' : 'analysis-edge dim'}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y + BOX_H}
                  strokeDasharray={dashed ? '4 4' : undefined}
                />
                <text
                  x={a.x + (b.x - a.x) * t}
                  y={a.y + (b.y + BOX_H - a.y) * t}
                  textAnchor="middle"
                  className="analysis-edge-label"
                >
                  {label}
                  <title>{data.relationLabels?.[e.kind] || e.kind}</title>
                </text>
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = position.get(n.key);
            if (!p) return null;
            return (
              <g
                key={n.key}
                className={`analysis-node state-${n.state || 'none'}${lit(n.key) ? '' : ' dim'}`}
              >
                <title>
                  {n.name} · {n.concept}
                  {n.state ? ` · ${STATE_LABELS[n.state] || n.state}` : ''}
                </title>
                <rect x={p.x - p.w / 2} y={p.y} width={p.w} height={BOX_H} rx={6} />
                <text x={p.x} y={p.y + 15} textAnchor="middle">
                  {clip(n.name, p.w)}
                </text>
                <text x={p.x} y={p.y + 29} textAnchor="middle" className="analysis-concept">
                  {clip(n.state ? STATE_LABELS[n.state] || n.state : n.concept || '', p.w)}
                </text>
              </g>
            );
          })}
        </svg>
        <figcaption>
          <span className="analysis-legend state-available">가용</span>
          <span className="analysis-legend state-limited">제한</span>
          <span className="analysis-legend state-unavailable">불가</span>
          <span className="analysis-legend state-excluded">제외</span>
          <span className="analysis-legend state-none">연결 노드</span>
        </figcaption>
      </figure>
    </section>
  );
}
