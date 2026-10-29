import { useEffect, useState } from 'react';
import { api, connect, CLIENT_ID } from './api';
import { useStore } from './store';
import { TopBar } from './components/TopBar';
import { LeftPanel } from './components/LeftPanel';
import { Preview, togglePlayback } from './components/Preview';
import { Inspector } from './components/Inspector';
import { Timeline } from './components/Timeline';
import { ProjectPicker } from './components/ProjectPicker';
import { ChatDrawer } from './components/ChatDrawer';
import './styles.css';

export default function App() {
  const project = useStore(s => s.project);
  const [pid, setPid] = useState<string | null>(() => new URLSearchParams(location.search).get('p'));

  useEffect(() => {
    if (!pid) return;
    api.getProject(pid).then(p => useStore.getState().load(p));
    const off = connect(pid, m => {
      if (m.type === 'project' && m.origin !== CLIENT_ID) useStore.getState().external(m.project);
      if (m.type === 'claude') useStore.getState().claudeEvent(m);
      if (m.type === 'job') useStore.getState().upsertJob(m.job);
    });
    history.replaceState(null, '', `?p=${pid}`);
    return off;
  }, [pid]);

  // klavye kisayollari
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      const s = useStore.getState();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? s.redo() : s.undo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); s.redo(); }
      else if (e.key === ' ') { e.preventDefault(); togglePlayback(e); }
      else if (e.key.toLowerCase() === 's' && !e.ctrlKey) s.splitSelected();
      else if (e.key === 'Delete' || e.key === 'Backspace') s.deleteSelected();
      else if (e.key === 'ArrowLeft') s.setTime(s.time - (e.shiftKey ? 1 : 1 / 30));
      else if (e.key === 'ArrowRight') s.setTime(s.time + (e.shiftKey ? 1 : 1 / 30));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!pid || !project) return <ProjectPicker onOpen={setPid} loading={!!pid} />;

  return (
    <div className="app">
      <TopBar onHome={() => { setPid(null); useStore.setState({ project: null }); history.replaceState(null, '', '/'); }} />
      <div className="main">
        <LeftPanel />
        <Preview />
        <Inspector />
      </div>
      <Timeline />
      <ChatDrawer />
    </div>
  );
}
