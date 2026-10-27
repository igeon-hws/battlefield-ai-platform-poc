import { useEffect, useState } from 'react';
import SourceApp from './SourceApp';
import NativeSourceApp from './NativeSourceApp';

export default function SourceEntry({ system }: { system: 'atcis' | 'knccs' }) {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    void fetch('/health')
      .then((r) => r.json())
      .then((data) => setVersion(data.sourceSchemaVersion || '2'))
      .catch(() => setVersion('2'));
  }, []);
  return version === null ? (
    <p>연결 중</p>
  ) : ['3.0.0', '4.0.0'].includes(version) ? (
    <NativeSourceApp system={system} />
  ) : (
    <SourceApp system={system} />
  );
}
