import { useEffect, useState } from 'react';
import { api } from '../api';

export function ProjectPicker({ onOpen, loading }: { onOpen: (id: string) => void; loading: boolean }) {
  const [list, setList] = useState<{ id: string; name: string; updated: number; media: number }[]>([]);
  const [name, setName] = useState('');
  useEffect(() => { api.listProjects().then(setList).catch(() => setList([])); }, []);
  if (loading) return <div className="picker"><div className="spinner" /> Proje açılıyor…</div>;
  return (
    <div className="picker">
      <div className="picker-card">
        <div className="brand big">✂ Klip Studio</div>
        <p className="muted">Shorts / Reels / TikTok için yapay zeka destekli editör</p>
        <form className="row" onSubmit={async e => {
          e.preventDefault();
          const p = await api.newProject(name.trim() || 'Yeni proje');
          onOpen(p.id);
        }}>
          <input className="input grow" placeholder="Yeni proje adı (örn. Gizmo – kaşık)" value={name} onChange={e => setName(e.target.value)} />
          <button className="btn primary">+ Yeni proje</button>
        </form>
        <div className="plist">
          {list.length === 0 && <div className="muted small">Henüz proje yok.</div>}
          {list.map(p => (
            <button key={p.id} className="pitem" onClick={() => onOpen(p.id)}>
              <span className="pname">{p.name}</span>
              <span className="muted small">{p.media} medya · {new Date(p.updated * 1000).toLocaleString('tr-TR')}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
