import { useEffect, useState } from 'react';

// YouTube'a gonderme. Varsayilan: dosyayi Gezgin'de sec + YouTube yukleme sayfasini ac (kullanici surukler).
// API ile yukleme denetlenmemis projede OZEL kilitlenir; yine de secenek olarak var.
export function PublishDialog({ pid, file, name, onClose }: { pid: string; file: string; name: string; onClose: () => void }) {
  const [chs, setChs] = useState<string[]>([]);
  const [ch, setCh] = useState('whatif');
  const [title, setTitle] = useState(name);
  const [desc, setDesc] = useState('#shorts');
  const [tags, setTags] = useState('shorts');
  const [ai, setAi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  useEffect(() => { fetch('/api/analysis/channels').then(r => r.json()).then((l: string[]) => { setChs(l); if (l[0]) setCh(l[0]); }); }, []);

  const go = async (mode: 'studio' | 'api_private') => {
    setBusy(true); setMsg('');
    const r = await fetch('/api/analysis/publish', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid, file, channel: ch, mode, title, description: desc, tags, ai }),
    });
    const d = await r.json();
    setBusy(false);
    if (!r.ok) { setMsg('Hata: ' + (d.detail ?? r.status)); return; }
    if (mode === 'studio') {
      window.open(d.open, '_blank');
      setMsg('Dosya Gezgin\'de seçili açıldı; YouTube yükleme sayfasına sürükle. Başlık/açıklamayı aşağıdan kopyalayabilirsin.');
    } else setMsg(`Yüklendi (ÖZEL): ${d.url} — ${d.note}`);
  };

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal small-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><b>▶ YouTube'a gönder</b><div className="grow" /><button className="btn ghost" onClick={onClose}>✕</button></div>
        <div className="modal-body stack">
          <div className="muted small ell">{file}</div>
          <label className="field"><span className="flabel">Başlık</span><input className="input" value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="field"><span className="flabel">Açıklama</span><textarea className="input" rows={4} value={desc} onChange={e => setDesc(e.target.value)} /></label>
          <label className="field"><span className="flabel">Etiketler (virgülle)</span><input className="input" value={tags} onChange={e => setTags(e.target.value)} /></label>
          <label className="check"><input type="checkbox" checked={ai} onChange={e => setAi(e.target.checked)} /> AI ile oluşturulmuş / değiştirilmiş içerik</label>
          <button className="btn primary wide" disabled={busy} onClick={() => go('studio')}>YouTube Studio'da yükle (önerilen)</button>
          <button className="btn ghost sm" onClick={() => navigator.clipboard.writeText(`${title}\n\n${desc}`)}>Başlık + açıklamayı kopyala</button>
          <details>
            <summary className="muted small">API ile yükle (özel kalır)</summary>
            <div className="stack" style={{ marginTop: 8 }}>
              <select className="input" value={ch} onChange={e => setCh(e.target.value)}>{chs.map(c => <option key={c}>{c}</option>)}</select>
              <div className="muted small">Google API denetimi onaylanana kadar API ile yüklenen videolar ÖZEL olarak kilitlenir.</div>
              <button className="btn wide" disabled={busy} onClick={() => go('api_private')}>API ile özel yükle</button>
            </div>
          </details>
          {msg && <div className="pill">{msg}</div>}
        </div>
      </div>
    </div>
  );
}
