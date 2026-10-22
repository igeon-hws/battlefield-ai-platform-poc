import { createRoot } from 'react-dom/client';
import SourceApp from '../../src/SourceEntry';
createRoot(document.getElementById('root')!).render(<SourceApp system="atcis" />);
