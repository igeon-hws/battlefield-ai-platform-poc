import { useEffect, useRef, useState } from 'react';
type Target = { key: string; version: string } | null;
export default function KnowledgeDocuments({
  get,
  target,
}: {
  get: (path: string) => Promise<any>;
  target: Target;
}) {
  const [sets, setSets] = useState<any[]>([]);
  const [version, setVersion] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [doc, setDoc] = useState<any>(null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    let active = true;
    void get('knowledge/sets')
      .then((r) => {
        if (active) {
          setSets(r.items);
          setVersion(target?.version || r.items[0]?.knowledgeSetVersion || '');
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      active = false;
    };
  }, [get]);
  const listing = async (next = '') => {
    const id = ++generation.current;
    setError('');
    try {
      const r = await get(
        'knowledge/search?' +
          new URLSearchParams({ knowledgeSetVersion: version, q, cursor: next }),
      );
      if (id === generation.current) {
        setItems(r.items);
        setCursor(r.nextCursor);
      }
    } catch (e) {
      if (id === generation.current) setError(String(e));
    }
  };
  const read = async (key: string, v = version) => {
    const id = ++generation.current;
    setDoc(null);
    setError('');
    try {
      const r = await get(
        'knowledge/documents/' +
          encodeURIComponent(key) +
          '?' +
          new URLSearchParams({ knowledgeSetVersion: v }),
      );
      if (id === generation.current) setDoc(r);
    } catch (e) {
      if (id === generation.current) setError(String(e));
    }
  };
  useEffect(() => {
    generation.current++;
    setDoc(null);
    setItems([]);
    let active = true;
    if (version)
      void (async () => {
        await listing();
        if (active && target?.version === version) await read(target.key, version);
      })();
    return () => {
      active = false;
      generation.current++;
    };
  }, [version, get, target]);
  useEffect(() => {
    if (target) {
      setVersion(target.version);
    }
  }, [target]);
  return (
    <div>
      <h2>Fabric 지식 문서</h2>
      <p>
        체계 밖에서 관리하는 검토된 코드북·규정·SOP입니다. 업무 관측 기록과 구분하며 B/C가 같은 지식
        집합을 사용합니다.
      </p>
      <label>
        지식 집합 버전
        <select
          aria-label="지식 집합 버전"
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        >
          {sets.map((s) => (
            <option key={s.knowledgeSetVersion} value={s.knowledgeSetVersion}>
              {s.reviewRevision} · {s.documents.length}문서 · {s.knowledgeSetVersion}
            </option>
          ))}
        </select>
      </label>
      <form
        className="graph-tools"
        onSubmit={(e) => {
          e.preventDefault();
          void listing();
        }}
      >
        <label>
          문서 검색
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="문서 ID · 본문 텍스트"
          />
        </label>
        <button disabled={!version}>문서 찾기</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <div className="knowledge-document-grid">
        <div>
          <h3>문서 목록</h3>
          {items.map((d) => (
            <button
              className="domain-record"
              aria-label={'문서 ' + d.documentKey}
              key={d.documentKey}
              onClick={() => void read(d.documentKey)}
            >
              <strong>
                {d.documentKey} · v{d.version}
              </strong>
              <small>
                발행 {d.issuer} · 적용 {d.appliesTo.join(', ')} · {d.section}
              </small>
            </button>
          ))}
          {cursor && <button onClick={() => void listing(cursor)}>다음 문서 페이지</button>}
        </div>
        <div>
          {doc ? (
            <>
              <h3>{doc.documentKey}</h3>
              <p>
                발행처 {doc.document.issuer} · 문서 버전 {doc.document.version} · 검토{' '}
                {doc.reviewRevision}
              </p>
              <p>
                알려진 시점 {doc.document.knownAt || '정보 없음'} · 적용 {doc.appliesTo.join(', ')}
              </p>
              <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{doc.document.text}</p>
              <details>
                <summary>버전·hash·원본 JSON</summary>
                <pre>{JSON.stringify(doc, null, 2)}</pre>
              </details>
            </>
          ) : (
            <p>문서를 선택하면 전체 본문과 출처를 확인할 수 있습니다.</p>
          )}
        </div>
      </div>
    </div>
  );
}
