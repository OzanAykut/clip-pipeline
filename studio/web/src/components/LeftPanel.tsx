import { useEffect, useRef, useState } from 'react';
import { nanoid } from 'nanoid';
import { api } from '../api';
import { trackFor, useStore } from '../store';
import { CAPTION_STYLES, CAPTIONEER_PRESETS } from '../remotion/captions';
import { TRANSITIONS } from '../remotion/Main';
import type { Media } from '../types';
import { AiPanel } from './AiPanel';

const TABS = [
  { id: 'media', label: 'Medya', icon: '🎞' },
  { id: 'text', label: 'Metin', icon: 'T' },
  { id: 'captions', label: 'Altyazı', icon: '💬' },
  { id: 'trans', label: 'Geçiş', icon: '⇄' },
  { id: 'audio', label: 'Ses', icon: '♫' },
  { id: 'ai', label: 'AI', icon: '✦' },
] as const;

export function LeftPanel() {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('media');
  return (
    <div className="left">
      <div className="tabs-v">
        {TABS.map(t => (
          <button key={t.id} className={`tab-v ${tab === t.id ? 'on' : ''}`} onClick={() => setTab(t.id)}>
            <span className="ti">{t.icon}</span><span>{t.label}</span>
          </button>
        ))}
      </div>
      <div className="left-body">
        {tab === 'media' && <MediaTab />}
        {tab === 'text' && <TextTab />}
        {tab === 'captions' && <CaptionsTab />}
        {tab === 'trans' && <TransitionsTab />}
        {tab === 'audio' && <AudioTab />}
        {tab === 'ai' && <AiTab />}
      </div>
    </div>
  );
}

export const dragMedia = (e: React.DragEvent, m: Media) => {
  e.dataTransfer.setData('application/x-klip-media', JSON.stringify(m));
  e.dataTransfer.effectAllowed = 'copy';
};

function MediaCard({ m }: { m: Media }) {
  const pid = useStore(s => s.project!.id);
  const thumb = m.kind === 'video' ? `/api/projects/${pid}/media/${encodeURIComponent(m.name)}/thumb?t=0.5`
    : m.kind === 'image' ? m.url : null;
  return (
    <div className="mcard" draggable onDragStart={e => dragMedia(e, m)} title="Sürükleyip timeline'a bırak ya da + ile ekle">
      <div className="mthumb">{thumb ? <img src={thumb} /> : <span className="big-ic">♫</span>}
        <span className="mdur">{m.duration ? `${m.duration.toFixed(1)}s` : ''}</span></div>
      <div className="mname">{m.name}</div>
      <button className="mplus" onClick={() => useStore.getState().addMedia(m)}>+</button>
    </div>
  );
}

function MediaTab() {
  const project = useStore(s => s.project)!;
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(0);
  const [over, setOver] = useState(false);
  const upload = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      setBusy(b => b + 1);
      try {
        const m = await api.upload(project.id, f);
        useStore.setState(s => s.project ? { project: { ...s.project, media: [...s.project.media.filter(x => x.name !== m.name), m] } } : s);
      } finally { setBusy(b => b - 1); }
    }
  };
  return (
    <div className={`drop ${over ? 'over' : ''}`}
      onDragOver={e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setOver(true); } }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}>
      <button className="btn primary wide" onClick={() => input.current?.click()}>⤒ Medya içe aktar</button>
      <input ref={input} type="file" multiple hidden accept="video/*,audio/*,image/*" onChange={e => e.target.files && upload(e.target.files)} />
      <div className="muted small center">ya da dosyaları buraya sürükle</div>
      {busy > 0 && <div className="pill">{busy} dosya yükleniyor…</div>}
      <div className="mgrid">
        {project.media.map(m => <MediaCard key={m.name} m={m} />)}
      </div>
    </div>
  );
}

const TEXT_PRESETS = [
  { name: 'Başlık', props: { text: 'BAŞLIK', size: 96, color: '#ffffff', y: 0.18 } },
  { name: 'Sarı vurgu', props: { text: 'WOW!', size: 130, color: '#FFE500', y: 0.4 } },
  { name: 'Kırmızı uyarı', props: { text: 'WRONG!', size: 150, color: '#E53935', y: 0.42 } },
  { name: 'Alt yazı notu', props: { text: 'part 2 👇', size: 64, color: '#ffffff', y: 0.88 } },
];

function TextTab() {
  return (
    <div className="stack">
      <div className="sec">Metin ekle</div>
      {TEXT_PRESETS.map(t => (
        <button key={t.name} className="preset" onClick={() => {
          const s = useStore.getState();
          const id = nanoid(8);
          s.commit(p => {
            trackFor(p, 'overlay').items.push({ id, type: 'text', start: s.time, in: 0, out: 2.5, speed: 1, volume: 1,
              fadeIn: 0.1, fadeOut: 0.1, transition: null, props: { ...t.props, x: 0.5, scale: 1 } });
          });
          s.select(id);
        }}>
          <span style={{ color: t.props.color, fontFamily: 'KlipBlack', fontSize: 22, WebkitTextStroke: '1px #000' }}>{t.props.text}</span>
          <span className="muted small">{t.name}</span>
        </button>
      ))}
    </div>
  );
}

export function useJob(id: string | null) {
  return useStore(s => (id ? s.jobs[id] : undefined));
}

export function JobLine({ id }: { id: string | null }) {
  const j = useJob(id);
  if (!j) return null;
  if (j.status === 'error') return <div className="pill err" title={j.message}>Hata: {j.message.slice(0, 80)}</div>;
  if (j.status === 'done') return <div className="pill ok">✓ Tamam</div>;
  return (
    <div className="jobline"><div className="bar"><div style={{ width: `${Math.max(4, j.progress * 100)}%` }} /></div>
      <span className="muted small ell">{j.message}</span></div>
  );
}

function CaptionsTab() {
  const project = useStore(s => s.project)!;
  const caps = project.tracks.find(t => t.kind === 'caption')!.items;
  const [lang, setLang] = useState('auto');
  const [job, setJob] = useState<string | null>(null);
  const running = useJob(job)?.status === 'running' || useJob(job)?.status === 'queued';
  const apply = (id: string) => useStore.getState().commit(p => {
    p.captionStyle = id;
    p.tracks.filter(t => t.kind === 'caption').forEach(t => t.items.forEach(i => { i.props.style = id; delete i.props.size; }));
  });
  const cats = CAPTIONEER_PRESETS.reduce<Record<string, typeof CAPTIONEER_PRESETS>>((a, x) => ((a[x.category] ??= []).push(x), a), {});
  return (
    <div className="stack">
      <div className="sec">Otomatik altyazı</div>
      <div className="row">
        <select className="input" style={{ width: 110 }} value={lang} onChange={e => setLang(e.target.value)}>
          <option value="auto">Dil: otomatik</option><option value="en">İngilizce</option><option value="tr">Türkçe</option>
        </select>
        <button className="btn primary grow" disabled={running} onClick={async () => {
          const j = await api.tool(project.id, 'captions', { language: lang });
          useStore.getState().upsertJob(j); setJob(j.id);
        }}>✦ Altyazı oluştur</button>
      </div>
      <JobLine id={job} />
      <div className="muted small">Timeline'daki konuşmalar Whisper ile yazıya dökülür. Elle eklenen altyazılar korunur. {caps.length} blok var.</div>

      <div className="sec">Bizim stiller</div>
      <div className="cgrid">
        {CAPTION_STYLES.map(st => (
          <button key={st.id} className={`preset ${project.captionStyle === st.id ? 'on' : ''}`} onClick={() => apply(st.id)}>
            <b>{st.name}</b><span className="muted small">{st.desc}</span>
          </button>
        ))}
      </div>
      {Object.entries(cats).map(([cat, list]) => (
        <div key={cat} className="stack">
          <div className="sec">{cat}</div>
          <div className="cgrid">
            {list.map(st => (
              <button key={st.id} className={`preset ${project.captionStyle === st.id ? 'on' : ''}`} onClick={() => apply(st.id)} title={st.desc}>
                <b>{st.name}</b><span className="muted small ell2">{st.desc}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TransitionsTab() {
  const selected = useStore(s => s.selected);
  useStore(s => s.project);
  const f = useStore.getState().findItem(selected);
  const [dur, setDur] = useState(0.4);
  const visual = f && (f.item.type === 'video' || f.item.type === 'image');
  const setTr = (type: string | null, all = false) => useStore.getState().commit(p => {
    for (const t of p.tracks) {
      if (all ? t.kind !== 'video' : false) continue;
      t.items.forEach((it, i) => {
        if (all ? i > 0 : it.id === selected) it.transition = type ? { type, dur } : null;
      });
    }
  });
  return (
    <div className="stack">
      <div className="sec">Geçişler</div>
      <div className="muted small">{visual ? 'Seçili klibe girişte uygulanır; önceki klip altında devam eder.' : 'Önce timeline\'da bir video/görsel klip seç.'}</div>
      <label className="field"><span className="flabel">Süre<span className="fval">{dur.toFixed(2)} sn</span></span>
        <input type="range" min={0.15} max={1.5} step={0.05} value={dur} onChange={e => setDur(+e.target.value)} /></label>
      <div className="cgrid">
        {TRANSITIONS.map(t => (
          <button key={t.id} className={`preset ${f?.item.transition?.type === t.id ? 'on' : ''}`} disabled={!visual}
            onClick={() => setTr(t.id)}><b>{t.name}</b></button>
        ))}
        <button className="preset" disabled={!visual} onClick={() => setTr(null)}><b>Yok</b></button>
      </div>
      <div className="sec">Hızlı</div>
      <button className="btn" onClick={() => setTr('slide-left', true)}>Tüm video kliplerine "Sola kay" uygula</button>
      <button className="btn" onClick={() => setTr(null, true)}>Tüm geçişleri kaldır</button>
    </div>
  );
}

function AudioTab() {
  const [lib, setLib] = useState<{ music: Media[]; sfx: Media[] } | null>(null);
  useEffect(() => { api.library().then(setLib); }, []);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const preview = (m: Media) => {
    audio.current?.pause();
    if (playing === m.url) { setPlaying(null); return; }
    audio.current = new Audio(m.url);
    audio.current.volume = 0.6;
    audio.current.play();
    audio.current.onended = () => setPlaying(null);
    setPlaying(m.url);
  };
  if (!lib) return <div className="muted">yükleniyor…</div>;
  const row = (m: Media) => (
    <div key={m.url} className="arow" draggable onDragStart={e => {
      e.dataTransfer.setData('application/x-klip-media', JSON.stringify(m));
    }}>
      <button className="btn ghost sm" onClick={() => preview(m)}>{playing === m.url ? '■' : '▶'}</button>
      <span className="grow ell">{m.name.replace(/\.[^.]+$/, '').replace(/_/g, ' ')}</span>
      <span className="muted small">{m.duration.toFixed(0)}s</span>
      <button className="btn ghost sm" onClick={() => useStore.getState().addMedia(m)}>+</button>
    </div>
  );
  return (
    <div className="stack">
      <div className="sec">Müzik (YouTube Audio Library)</div>
      {lib.music.map(row)}
      <div className="sec">Efektler</div>
      {lib.sfx.map(row)}
    </div>
  );
}

function AiTab() {
  return <AiPanel />;
}
