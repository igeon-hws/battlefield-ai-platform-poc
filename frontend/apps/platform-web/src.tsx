import KnowledgeApp from '../../src/KnowledgeApp';
import { createRoot } from 'react-dom/client';
import App from '../../src/App';
import NextApp from '../../src/NextApp';
import '../../src/style.css';
const root = createRoot(document.getElementById('root')!);
fetch('/api/v1/config')
  .then(async (response) => (response.ok ? response.json() : { profile: 'legacy' }))
  .then((config) =>
    root.render(
      config.sourceToolContractVersion === '4' ? (
        <KnowledgeApp fabricUrl={config.fabricUrl} />
      ) : config.profile === 'heterogeneous' ? (
        <NextApp domain={config.sourceToolContractVersion === '3'} />
      ) : (
        <App mode="platform" />
      ),
    ),
  )
  .catch(() => root.render(<App mode="platform" />));
