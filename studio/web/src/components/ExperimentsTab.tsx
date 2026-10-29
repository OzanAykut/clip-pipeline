import { useEffect, useState } from 'react';

// grafik renkleri AnalysisView ile ayni (dataviz dogrulandi, koyu yuzey): tek seri = mavi
const BLUE = '#3987e5';
const RED = '#e66767';
const INK = '#E8EAF0';
const GRID = '#2A2E3A';
const nf = (n: number) => n.toLocaleString('tr-TR');

type ExpM = { views?: number; stay?: number | null; apv?: number | null; hold3s?: number | null; t1?: number | null; subs?: number | null; age_h?: number };
type Exp = {
  video_id: string; channel: string; style: string; variable: string; notes: string; title?: string; published?: string; age_h?: number;
  latest?: ExpM; snapshots: Record<string, ExpM>; error?: string;
};
type StyleRow = { style: string; n: number; views: number | null; stay: number | null; apv: number | null; hold3s: number | null; t1: number | null; subs: number | null };
type MetricKey = 'stay' | 'apv' | 'hold3s' | 't1' | 'views';
const METRICS: { k: MetricKey; label: string; unit: string; hint: string }[] = [
  { k: 'stay', label: 'Kaydırmadan izleyen', unit: '%', hint: 'engagedViews / views — Shorts akışında en önemli sinyal' },
  { k: 'apv', label: 'Ort. izlenme', unit: '%', hint: 'videonun ortalama yüzde kaçı izlendi' },
  { k: 'hold3s', label: '3. saniye', unit: '%', hint: '3. saniyedeki izleyici oranı (tekrar izleme dahil, 100 üstü olabilir)' },
  { k: 't1', label: 'T1 ülke payı', unit: '%', hint: 'ABD/İngiltere/Kanada/Avustralya izlenme payı' },
  { k: 'views', label: 'İzlenme', unit: '', hint: 'toplam izlenme' },
];
const SNAPS: [string, string][] = [['latest', 'Güncel'], ['h24', '24 saat'], ['h48', '48 saat'], ['d7', '7 gün']];
const fmt = (v: number | null | undefined, unit: string) => (v == null ? '–' : unit ? `${v.toFixed(0)}${unit}` : nf(v));

export function ExperimentsTab() {
  const [d, setD] = useState<{ videos: Exp[]; styles: StyleRow[]; channels: string[] } | null>(null);
  const [snap, setSnap] = useState('latest');
  const [metric, setMetric] = useState<MetricKey>('stay');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ channel: '', video: '', style: '', variable: '', notes: '' });

  const load = (refresh = false) => {
    setBusy(true);
    fetch(`/api/analysis/experiments?snap=${snap}${refresh ? '&refresh=1' : ''}`).then(r => r.json()).then(setD).finally(() => setBusy(false));
  };
  useEffect(() => { load(); }, [snap]);

  const add = async () => {
    if (!form.video || !form.style) return;
    setBusy(true);
    await fetch('/api/analysis/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
    setForm({ ...form, video: '', variable: '', notes: '' });
    load();
  };
  const del = async (vid: string) => { await fetch(`/api/analysis/experiments/${vid}`, { method: 'DELETE' }); load(); };

  if (!d) return <div className="muted"><span className="spinner" />yükleniyor…</div>;
  const M = METRICS.find(m => m.k === metric)!;
  const pick = (e: Exp) => (snap === 'latest' ? e.latest : e.snapshots?.[snap]);
  const styles = d.styles.filter(s => s[metric] != null);
  const max = Math.max(1, ...styles.map(s => Number(s[metric])));
  const missing = [...new Set(d.videos.filter(v => v.error?.includes('token')).map(v => v.channel))];

  return (
    <div className="stack">
      <div className="row">
        <div className="seg">{SNAPS.map(([k, l]) => <button key={k} className={snap === k ? 'on' : ''} onClick={() => setSnap(k)}>{l}</button>)}</div>
        <select className="input" style={{ width: 210 }} value={metric} onChange={e => setMetric(e.target.value as MetricKey)}>
          {METRICS.map(m => <option key={m.k} value={m.k}>{m.label}</option>)}
        </select>
        <div className="grow" />
        <button className="btn" disabled={busy} onClick={() => load(true)}>{busy ? <span className="spinner" /> : '↻'} Metrikleri YouTube'dan güncelle</button>
      </div>
      {missing.length > 0 && (
        <div className="pill err">API girişi eksik: {missing.map(c => <code key={c} style={{ marginRight: 8 }}>python youtube_api.py auth {c}</code>)}</div>
      )}

      <div className="card">
        <div className="row">
          <b>Stil karşılaştırması</b>
          <span className="muted small">— {M.label}: {M.hint}{snap !== 'latest' ? ` · yalnız ${SNAPS.find(s => s[0] === snap)![1]} verisi olan videolar` : ''}</span>
        </div>
        {styles.length === 0 ? (
          <div className="muted small" style={{ padding: 8 }}>Bu görünümde henüz veri yok (Analytics 1–2 gün gecikmeli).</div>
        ) : (
          <div className="stack" style={{ gap: 6, marginTop: 8 }}>
            {styles.map(s => (
              <div key={s.style} className="row" style={{ gap: 10 }} title={`${s.style} · ${s.n} video · ${M.label}: ${fmt(s[metric], M.unit)}`}>
                <div className="small ell" style={{ width: 230, color: INK }}>{s.style} <span className="muted">({s.n})</span></div>
                <div style={{ flex: 1, height: 18, background: GRID, borderRadius: 4 }}>
                  <div style={{ width: `${(100 * Number(s[metric])) / max}%`, height: '100%', background: BLUE, borderRadius: 4 }} />
                </div>
                <div className="small" style={{ width: 64, textAlign: 'right', color: INK }}>{fmt(s[metric], M.unit)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="tablewrap">
        <table className="tbl">
          <thead>
            <tr><th>Video</th><th>Stil / değişken</th><th className="r">Yaş</th>
              {METRICS.map(m => <th key={m.k} className="r" title={m.hint}>{m.label}</th>)}<th className="r">Abone</th><th /></tr>
          </thead>
          <tbody>
            {d.videos.map(e => {
              const m = pick(e);
              return (
                <tr key={e.video_id}>
                  <td>
                    <a href={`https://youtube.com/shorts/${e.video_id}`} target="_blank" rel="noreferrer" className="ell2" style={{ color: INK }}>{e.title ?? e.video_id}</a>
                    <div className="muted small">{e.channel}{e.error ? <span style={{ color: RED }}> · {e.error.slice(0, 50)}</span> : ''}</div>
                  </td>
                  <td><div className="small">{e.style}</div><div className="muted small">{e.variable}</div></td>
                  <td className="r small">{e.age_h != null ? (e.age_h < 48 ? `${e.age_h.toFixed(0)} sa` : `${(e.age_h / 24).toFixed(0)} g`) : '–'}</td>
                  {METRICS.map(mm => <td key={mm.k} className="r">{fmt(m?.[mm.k] as number | undefined, mm.unit)}</td>)}
                  <td className="r">{fmt(m?.subs, '')}</td>
                  <td><button className="ic" title="Deneyden çıkar" onClick={() => del(e.video_id)}>🗑</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card">
        <b>Yeni deney ekle</b>
        <div className="muted small">Her yüklemede tek bir şeyi değiştir; stil adını tutarlı yaz ki gruplanabilsin.</div>
        <div className="row" style={{ flexWrap: 'wrap', marginTop: 8 }}>
          <input className="input" style={{ width: 110 }} list="exp-ch" value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })} placeholder="kanal" />
          <datalist id="exp-ch">{[...new Set(d.channels)].map(c => <option key={c} value={c} />)}</datalist>
          <input className="input" style={{ width: 230 }} value={form.video} onChange={e => setForm({ ...form, video: e.target.value })} placeholder="video linki ya da ID" />
          <input className="input" style={{ width: 210 }} list="exp-style" value={form.style} onChange={e => setForm({ ...form, style: e.target.value })} placeholder="stil (örn. Sinematik motivasyon)" />
          <datalist id="exp-style">{d.styles.map(s => <option key={s.style} value={s.style} />)}</datalist>
          <input className="input" style={{ width: 200 }} value={form.variable} onChange={e => setForm({ ...form, variable: e.target.value })} placeholder="değişen tek şey" />
          <input className="input" style={{ width: 180 }} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="not (opsiyonel)" />
          <button className="btn" disabled={busy || !form.video || !form.style} onClick={add}>+ Ekle</button>
        </div>
      </div>
    </div>
  );
}
