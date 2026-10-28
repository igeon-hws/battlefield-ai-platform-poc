import { DemoEntry } from '../../src/LogisticsPanels';
import { configureDemo } from '../../src/KnowledgeApp';
import KnowledgeApp from '../../src/KnowledgeApp';
import { createRoot } from 'react-dom/client';
import App from '../../src/App';
import NextApp from '../../src/NextApp';
import '../../src/style.css';
const root = createRoot(document.getElementById('root')!);
let v5Detected = false;
fetch('/api/v1/config')
  .then(async (response) => (response.ok ? response.json() : { profile: 'legacy' }))
  .then(async (config) => {
    if (config.sourceToolContractVersion === '5') {
      v5Detected = true;
      const modes: Record<string, 'native' | 'documents' | 'structured' | 'compare'> = {
        '/demo/a': 'native',
        '/demo/b': 'documents',
        '/demo/c': 'structured',
        '/demo/compare': 'compare',
      };
      const mode = modes[location.pathname];
      if (!mode) {
        root.render(<DemoEntry />);
        return;
      }
      const response = await fetch('/api/v1/demo-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (!response.ok) throw new Error('Demo context unavailable');
      const session = await response.json();
      configureDemo(session.sessionId);
      root.render(
        <KnowledgeApp
          fixedMode={mode === 'compare' ? 'native' : mode}
          comparePage={mode === 'compare'}
        />,
      );
      return;
    }
    root.render(
      config.sourceToolContractVersion === '4' ? (
        <KnowledgeApp fabricUrl={config.fabricUrl} />
      ) : config.profile === 'heterogeneous' ? (
        <NextApp domain={config.sourceToolContractVersion === '3'} />
      ) : (
        <App mode="platform" />
      ),
    );
  })
  .catch(() =>
    root.render(
      v5Detected ? (
        <main className="demo-entry" role="alert">
          <h1>시연 화면을 열지 못했습니다</h1>
          <p>서버 연결을 확인한 뒤 다시 진입하세요.</p>
          <a href="/">조건 선택으로</a>
        </main>
      ) : (
        <App mode="platform" />
      ),
    ),
  );
