import { useState } from 'react';
import { api } from '../api';
import { useStore } from '../store';
import { AnalysisView } from './AnalysisView';
import { PublishDialog } from './PublishDialog';

export function TopBar({ onHome }: { onHome: () => void }) {
  const project = useStore(s => s.project)!;
  const saving = useStore(s => s.saving);
  const past = useStore(s => s.past.length);
  const future = useStore(s => s.future.length);
  const jobs = useStore(s => s.jobs);
  const [exportId, setExportId] = useState<string | null>(null);
  const exp = exportId ? jobs[exportId] : null;
  const [analysis, setAnalysis] = useState(false);
  const [publish, setPublish] = useState(false);

  return (
    <div className="topbar">
      <button className="btn ghost" onClick={onHome} title="Projeler">✂ <b>Klip Studio</b></button>
      <input className="title-input" value={project.name}
        onChange={e => useStore.getState().commit(p => { p.name = e.target.value; })} />
      <span className="muted small">{saving ? 'kaydediliyor…' : 'kaydedildi'}</span>
      <div className="grow" />
      <button className="btn ghost" disabled={!past} onClick={() => useStore.getState().undo()} title="Geri al (Ctrl+Z)">↶</button>
      <button className="btn ghost" disabled={!future} onClick={() => useStore.getState().redo()} title="İleri al (Ctrl+Y)">↷</button>
      {exp && exp.status === 'running' && <span className="pill">Render %{Math.round(exp.progress * 100)}</span>}
      {exp && exp.status === 'queued' && <span className="pill">Sırada…</span>}
      {exp && exp.status === 'error' && <span className="pill err" title={exp.message}>Render hatası</span>}
      {exp && exp.status === 'done' && <a className="pill ok" href={exp.result.url} target="_blank">⬇ {exp.result.file}</a>}
      {exp && exp.status === 'done' && <button className="btn" onClick={() => setPublish(true)}>▶ YouTube'a gönder</button>}
      <button className="btn" onClick={() => setAnalysis(true)}>📊 Analiz</button>
      <button className="btn" onClick={() => useStore.getState().setChat(c => ({ open: !c.open }))} title="Claude ile düzenle">✦ Claude</button>
      <button className="btn primary" disabled={exp?.status === 'running' || exp?.status === 'queued'}
        onClick={async () => { const j = await api.exportProject(project.id); useStore.getState().upsertJob(j); setExportId(j.id); }}>
        Dışa aktar
      </button>
      {analysis && <AnalysisView onClose={() => setAnalysis(false)} />}
      {publish && exp?.result && <PublishDialog pid={project.id} file={exp.result.file} name={project.name} onClose={() => setPublish(false)} />}
    </div>
  );
}
