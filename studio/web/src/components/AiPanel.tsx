import { useEffect, useState } from 'react';
import { nanoid } from 'nanoid';
import { api } from '../api';
import { trackFor, useStore } from '../store';
import { JobLine, useJob } from './LeftPanel';
import type { Media } from '../types';

const VOICES = ['Puck', 'Fenrir', 'Zubenelgenubi', 'Charon', 'Kore', 'Aoede', 'Sadachbia', 'Achird', 'Leda', 'Zephyr'];

function useTool() {
  const pid = useStore(s => s.project!.id);
  const [job, setJob] = useState<string | null>(null);
  const j = useJob(job);
  const busy = j?.status === 'running' || j?.status === 'queued';
  const run = async (tool: string, args: Record<string, unknown>) => {
    const jb = await api.tool(pid, tool, args);
    useStore.getState().upsertJob(jb);
    setJob(jb.id);
  };
  return { run, busy, job, result: j?.status === 'done' ? j.result : null };
}

function Section({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="aisec">
      <div className="sec">{title}</div>
      {desc && <div className="muted small">{desc}</div>}
      {children}
    </div>
  );
}

export function AiPanel() {
  return (
    <div className="stack">
      <SelectedTools />
      <TtsTool />
      <BrollTool />
      <MomentsTool />
      <PodcastRecipe />
      <StoryRecipe />
    </div>
  );
}

function SelectedTools() {
  const sel = useStore(s => s.selected);
  useStore(s => s.project);
  const f = useStore.getState().findItem(sel);
  const ok = f && f.item.type === 'video' && f.item.src?.startsWith('/media/');
  const a = useTool();
  const b = useTool();
  return (
    <Section title="Seçili klip" desc={ok ? f!.item.src!.split('/').pop() : 'Timeline\'da bir video klip seç.'}>
      <button className="btn wide" disabled={!ok || a.busy} onClick={() => a.run('reframe', { item_id: sel, split_people: true })}>
        ▣ Akıllı 9:16 kadraj (yüz takibi)</button>
      <JobLine id={a.job} />
      <button className="btn wide" disabled={!ok || b.busy} onClick={() => b.run('silence_cut', { item_id: sel, min_gap: 0.45 })}>
        ✂ Sessizlikleri / duraklamaları kes</button>
      <JobLine id={b.job} />
      {b.result && <div className="muted small">{b.result.pieces} parça, {b.result.saved_sec} sn kazanıldı</div>}
    </Section>
  );
}

function TtsTool() {
  const [text, setText] = useState('');
  const [voice, setVoice] = useState('Puck');
  const [style, setStyle] = useState('Energetic, expressive, fast-paced.');
  const [speed, setSpeed] = useState(1.1);
  const t = useTool();
  return (
    <Section title="Seslendirme" desc="Gemini TTS; oynatma kafasına eklenir. Büyük harf kullanma (harf harf okur).">
      <textarea className="input" rows={3} placeholder="Söylenecek replik (İngilizce)…" value={text} onChange={e => setText(e.target.value)} />
      <div className="row">
        <select className="input" value={voice} onChange={e => setVoice(e.target.value)}>{VOICES.map(v => <option key={v}>{v}</option>)}</select>
        <select className="input" value={speed} onChange={e => setSpeed(+e.target.value)}>{[1, 1.1, 1.2, 1.3].map(s => <option key={s} value={s}>{s}x</option>)}</select>
      </div>
      <input className="input" value={style} onChange={e => setStyle(e.target.value)} title="Duygu / üslup tarifi" />
      <button className="btn primary wide" disabled={!text.trim() || t.busy}
        onClick={() => t.run('tts', { text, voice, style, speed, at: useStore.getState().time })}>✦ Seslendir</button>
      <JobLine id={t.job} />
    </Section>
  );
}

function BrollTool() {
  const [q, setQ] = useState('');
  const [mode, setMode] = useState<'full' | 'pip'>('pip');
  const [dur, setDur] = useState(2.5);
  const t = useTool();
  return (
    <Section title="B-roll (Pexels)" desc="Konuyla ilgili dikey video/foto bulur, oynatma kafasına ekler.">
      <input className="input" placeholder="İngilizce arama (örn. neutron star)" value={q} onChange={e => setQ(e.target.value)} />
      <div className="row">
        <button className={`btn sm ${mode === 'pip' ? 'on' : ''}`} onClick={() => setMode('pip')}>Köşe kart</button>
        <button className={`btn sm ${mode === 'full' ? 'on' : ''}`} onClick={() => setMode('full')}>Tam ekran</button>
        <select className="input" style={{ width: 80 }} value={dur} onChange={e => setDur(+e.target.value)}>{[1.5, 2.5, 4].map(d => <option key={d} value={d}>{d} sn</option>)}</select>
      </div>
      <button className="btn wide" disabled={!q.trim() || t.busy} onClick={() => t.run('broll', { query: q, mode, dur, at: useStore.getState().time })}>＋ B-roll ekle</button>
      <JobLine id={t.job} />
    </Section>
  );
}

function longVideos(media: Media[]) {
  return media.filter(m => m.kind === 'video' && m.duration > 90);
}

function MomentsTool() {
  const project = useStore(s => s.project)!;
  const vids = longVideos(project.media);
  const [media, setMedia] = useState('');
  const [clips, setClips] = useState(8);
  const t = useTool();
  useEffect(() => { if (!media && vids[0]) setMedia(vids[0].name); }, [vids.length]);
  const moments = ((project as any).moments ?? []) as { src: string; start: number; end: number; title: string; hook: string; score: number }[];
  return (
    <Section title="Uzun videodan an bul" desc="Podcast/yayın: Gemini en güçlü hook'lu anları seçer.">
      {vids.length === 0 ? <div className="muted small">1.5 dakikadan uzun bir video içe aktar.</div> : (
        <>
          <div className="row">
            <select className="input" value={media} onChange={e => setMedia(e.target.value)}>{vids.map(v => <option key={v.name}>{v.name}</option>)}</select>
            <select className="input" style={{ width: 70 }} value={clips} onChange={e => setClips(+e.target.value)}>{[4, 8, 12].map(n => <option key={n}>{n}</option>)}</select>
          </div>
          <button className="btn wide" disabled={t.busy || !media} onClick={() => t.run('moments', { media, clips })}>✦ Anları bul</button>
          <JobLine id={t.job} />
        </>
      )}
      {moments.sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).map((m, i) => (
        <div key={i} className="moment">
          <div className="grow">
            <b className="ell2">{m.title}</b>
            <div className="muted small">{m.start.toFixed(0)}–{m.end.toFixed(0)} sn · puan {m.score ?? '-'}</div>
          </div>
          <button className="btn sm" onClick={() => {
            const s = useStore.getState();
            s.commit(p => {
              const tr = trackFor(p, 'video');
              const at = Math.max(0, ...tr.items.map(x => x.start + (x.out - x.in) / x.speed));
              tr.items.push({ id: nanoid(8), type: 'video', src: m.src, start: at, in: m.start, out: m.end, speed: 1, volume: 1,
                fadeIn: 0, fadeOut: 0, transition: null, props: { fit: 'cover' } });
            });
          }}>＋</button>
        </div>
      ))}
    </Section>
  );
}

function PodcastRecipe() {
  const project = useStore(s => s.project)!;
  const vids = longVideos(project.media);
  const [media, setMedia] = useState('');
  const [clips, setClips] = useState(4);
  const t = useTool();
  useEffect(() => { if (!media && vids[0]) setMedia(vids[0].name); }, [vids.length]);
  return (
    <Section title="🍳 Tarif: Podcast klipleri" desc="Uzun video → en iyi anlar → her biri ayrı proje: 9:16 kadraj + altyazı + manşet.">
      {vids.length === 0 ? <div className="muted small">Önce uzun bir video içe aktar.</div> : (
        <>
          <div className="row">
            <select className="input" value={media} onChange={e => setMedia(e.target.value)}>{vids.map(v => <option key={v.name}>{v.name}</option>)}</select>
            <select className="input" style={{ width: 70 }} value={clips} onChange={e => setClips(+e.target.value)}>{[2, 4, 6].map(n => <option key={n}>{n}</option>)}</select>
          </div>
          <button className="btn primary wide" disabled={t.busy || !media} onClick={() => t.run('podcast_recipe', { media, clips })}>Klipleri üret</button>
          <JobLine id={t.job} />
          {t.result?.projects?.map((q: { id: string; title: string }) => (
            <a key={q.id} className="pill ok" href={`/?p=${q.id}`} target="_blank">↗ {q.title}</a>
          ))}
        </>
      )}
    </Section>
  );
}

function StoryRecipe() {
  const project = useStore(s => s.project)!;
  const visuals = project.media.filter(m => m.kind === 'video' || m.kind === 'image');
  const [rows, setRows] = useState<{ media: string; text: string }[]>([{ media: '', text: '' }]);
  const [voice, setVoice] = useState('Puck');
  const [music, setMusic] = useState('banjo_doops.mp3');
  const [lib, setLib] = useState<string[]>([]);
  const t = useTool();
  useEffect(() => { api.library().then(l => setLib(l.music.map(m => m.name))); }, []);
  const setRow = (i: number, k: 'media' | 'text', v: string) => setRows(r => r.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <Section title="🍳 Tarif: Karakter / What If" desc="Sahne başına klip + replik. Replikler seslendirilir, klipler sürelerine göre dizilir, geçiş + müzik + altyazı eklenir. Video/ses kanalları yeniden kurulur.">
      {rows.map((r, i) => (
        <div key={i} className="scene">
          <div className="row">
            <span className="muted small">{i + 1}</span>
            <select className="input" value={r.media} onChange={e => setRow(i, 'media', e.target.value)}>
              <option value="">— klip —</option>{visuals.map(v => <option key={v.name}>{v.name}</option>)}
            </select>
            <button className="btn ghost sm" onClick={() => setRows(x => x.filter((_, j) => j !== i))}>✕</button>
          </div>
          <input className="input" placeholder="Replik (boş = sadece görüntü)" value={r.text} onChange={e => setRow(i, 'text', e.target.value)} />
        </div>
      ))}
      <button className="btn sm" onClick={() => setRows(x => [...x, { media: '', text: '' }])}>＋ Sahne</button>
      <div className="row">
        <select className="input" value={voice} onChange={e => setVoice(e.target.value)}>{VOICES.map(v => <option key={v}>{v}</option>)}</select>
        <select className="input" value={music} onChange={e => setMusic(e.target.value)}>
          <option value="">Müzik yok</option>{lib.map(m => <option key={m}>{m}</option>)}
        </select>
      </div>
      <button className="btn primary wide" disabled={t.busy || rows.some(r => !r.media)}
        onClick={() => t.run('story_recipe', { scenes: rows, voice, music, transition: 'slide-left' })}>Videoyu kur</button>
      <JobLine id={t.job} />
    </Section>
  );
}
