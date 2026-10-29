import { useEffect, useMemo, useRef, useState } from 'react';
import { api, type AudioMap } from '../api';
import { defaultKind, fmtTime, useStore } from '../store';
import { itemDur, itemEnd, projectDuration, type Item, type Media, type Track, type TrackKind } from '../types';

const HEAD = 132;
const LANE = 56;
const SNAP_PX = 8;
const SIL_SNAP_PX = 16; // sessizlige yapisma daha genis: kesimin yeri sessiz bolge olmali
const AUDIO_KINDS: TrackKind[] = ['voice', 'music', 'sfx'];
const compatible = (from: TrackKind, to: TrackKind) =>
  from === to || (AUDIO_KINDS.includes(from) && AUDIO_KINDS.includes(to)) || ([from, to].every(k => k === 'video' || k === 'overlay'));
const COLORS: Record<TrackKind, string> = {
  video: '#3B82F6', overlay: '#A855F7', caption: '#F59E0B', voice: '#10B981', music: '#EC4899', sfx: '#F97316',
};

type Drag =
  | { mode: 'move'; id: string; x0: number; y0: number; start0: number; track0: string }
  | { mode: 'left' | 'right'; id: string; x0: number; item0: Item; maxOut: number; media?: string }
  | null;

export function Timeline() {
  const project = useStore(s => s.project)!;
  const zoom = useStore(s => s.zoom);
  const selected = useStore(s => s.selected);
  const scroller = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag>(null);
  const [preview, setPreview] = useState<{ id: string; start: number; track: string; inn?: number; out?: number } | null>(null);
  const dur = projectDuration(project) + 10;
  const width = dur * zoom;
  const mediaByUrl = useMemo(() => Object.fromEntries(project.media.map(m => [m.url, m])), [project.media]);

  const xToTime = (clientX: number) => {
    const r = scroller.current!.getBoundingClientRect();
    return Math.max(0, (clientX - r.left - HEAD + scroller.current!.scrollLeft) / zoom);
  };
  const yToTrack = (clientY: number): Track | undefined => {
    const r = scroller.current!.getBoundingClientRect();
    const i = Math.floor((clientY - r.top - 26 + scroller.current!.scrollTop) / LANE);
    return project.tracks[i];
  };

  // yapisma noktalari: diger ogelerin kenarlari + oynatma kafasi + 0
  const snap = (t: number, ignore: string) => {
    const pts = [0, useStore.getState().time, ...project.tracks.flatMap(tr => tr.items.filter(i => i.id !== ignore).flatMap(i => [i.start, itemEnd(i)]))];
    let best = t;
    let bd = SNAP_PX / zoom;
    for (const p of pts) if (Math.abs(p - t) < bd) { bd = Math.abs(p - t); best = p; }
    return best;
  };

  useEffect(() => {
    if (!drag) return;
    const s = useStore.getState();
    const onMove = (e: PointerEvent) => {
      const f = s.findItem(drag.id);
      if (!f) return;
      const dt = (e.clientX - drag.x0) / zoom;
      if (drag.mode === 'move') {
        let start = Math.max(0, drag.start0 + dt);
        const a = snap(start, drag.id);
        const b = snap(start + itemDur(f.item), drag.id) - itemDur(f.item);
        start = Math.abs(a - start) <= Math.abs(b - start) ? a : b;
        const tr = yToTrack(e.clientY);
        const track = tr && compatible(f.track.kind, tr.kind) ? tr.id : drag.track0;
        setPreview({ id: drag.id, start, track });
      } else {
        const it = drag.item0;
        const am = drag.media ? amaps[project.id + drag.media] : undefined;
        if (drag.mode === 'left') {
          // sol kenar: kaynakta in ve timeline'da start birlikte kayar
          let ns = snap(Math.max(0, it.start + dt), drag.id);
          let inn = it.in + (ns - it.start) * it.speed;
          // konusmanin hemen basina (sessizligin sonu - 60 ms) yapis
          if (am) inn = snapSilence(inn, am.silences.map(([, e]) => e - 0.06), SIL_SNAP_PX / zoom * it.speed);
          if (it.type === 'video' || it.type === 'audio') inn = Math.max(0, inn);
          inn = Math.min(inn, it.out - 0.1);
          ns = it.start + (inn - it.in) / it.speed;
          setPreview({ id: drag.id, start: ns, track: f.track.id, inn, out: it.out });
        } else {
          const end = snap(itemEnd(it) + dt, drag.id);
          let out = it.in + (end - it.start) * it.speed;
          // kelime kuyrugu kesilmesin: sessizligin basi + 120 ms'e yapis
          if (am) out = snapSilence(out, am.silences.map(([b]) => b + 0.12), SIL_SNAP_PX / zoom * it.speed);
          out = Math.max(it.in + 0.1, Math.min(out, drag.maxOut));
          setPreview({ id: drag.id, start: it.start, track: f.track.id, inn: it.in, out });
        }
      }
    };
    const onUp = () => {
      setDrag(null);
      setPreview(pv => {
        if (pv) {
          s.commit(p => {
            let moved: Item | undefined;
            for (const t of p.tracks) {
              const i = t.items.findIndex(x => x.id === pv.id);
              if (i >= 0) { moved = t.items[i]; t.items.splice(i, 1); }
            }
            if (!moved) return;
            moved.start = pv.start;
            if (pv.inn !== undefined) moved.in = pv.inn;
            if (pv.out !== undefined) moved.out = pv.out;
            const dst = p.tracks.find(t => t.id === pv.track)!;
            dst.items.push(moved);
            dst.items.sort((a, b) => a.start - b.start);
          });
        }
        return null;
      });
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, [drag, zoom, project]);

  const onWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey) { e.preventDefault(); useStore.getState().setZoom(zoom * (e.deltaY < 0 ? 1.15 : 0.87)); }
  };

  const onDrop = (e: React.DragEvent) => {
    const raw = e.dataTransfer.getData('application/x-klip-media');
    if (!raw) return;
    e.preventDefault();
    const m = JSON.parse(raw) as Media;
    const tr = yToTrack(e.clientY);
    const kind = tr && compatible(defaultKind(m), tr.kind) ? tr.kind : defaultKind(m);
    useStore.getState().addMedia(m, snap(xToTime(e.clientX), ''), kind);
  };

  // cetvel aralik secimi
  const step = zoom > 150 ? 0.5 : zoom > 60 ? 1 : zoom > 25 ? 5 : 10;
  const ticks = Array.from({ length: Math.ceil(dur / step) + 1 }, (_, i) => i * step);

  return (
    <div className="timeline">
      <div className="tl-tools">
        <button className="btn sm" onClick={() => useStore.getState().splitSelected()} title="Böl (S)">✂ Böl</button>
        <button className="btn sm" onClick={() => useStore.getState().deleteSelected()} title="Sil (Del)">🗑 Sil</button>
        <div className="grow" />
        <span className="muted small">Yakınlaştır</span>
        <input type="range" min={10} max={400} value={zoom} onChange={e => useStore.getState().setZoom(+e.target.value)} />
      </div>
      <div className="tl-scroll" ref={scroller} onWheel={onWheel} onDragOver={e => e.preventDefault()} onDrop={onDrop}>
        <div className="tl-inner" style={{ width: width + HEAD }}>
          <div className="ruler" onPointerDown={e => { useStore.getState().setTime(xToTime(e.clientX)); }}
            onPointerMove={e => { if (e.buttons === 1) useStore.getState().setTime(xToTime(e.clientX)); }}>
            <div className="ruler-head" />
            {ticks.map(t => (
              <div key={t} className="tick" style={{ left: HEAD + t * zoom }}><span>{fmtTime(t).replace(/\.\d+$/, '')}</span></div>
            ))}
          </div>
          {project.tracks.map(tr => (
            <div key={tr.id} className="lane" style={{ height: LANE }}
              onPointerDown={e => { if (e.target === e.currentTarget) { useStore.getState().select(null); useStore.getState().setTime(xToTime(e.clientX)); } }}>
              <div className="lane-head" style={{ borderLeft: `3px solid ${COLORS[tr.kind]}` }}>
                <span className="ell">{tr.name}</span>
                <button className={`ic ${tr.muted ? 'off' : ''}`} title="Sessiz" onClick={() => useStore.getState().commit(p => { const t = p.tracks.find(x => x.id === tr.id)!; t.muted = !t.muted; })}>{tr.muted ? '🔇' : '🔊'}</button>
                <button className={`ic ${tr.hidden ? 'off' : ''}`} title="Gizle" onClick={() => useStore.getState().commit(p => { const t = p.tracks.find(x => x.id === tr.id)!; t.hidden = !t.hidden; })}>{tr.hidden ? '🙈' : '👁'}</button>
              </div>
              {tr.items.map(it => {
                const pv = preview?.id === it.id ? preview : null;
                if (pv && pv.track !== tr.id) return null;
                const view: Item = pv ? { ...it, start: pv.start, in: pv.inn ?? it.in, out: pv.out ?? it.out } : it;
                return <Clip key={it.id} it={view} color={COLORS[tr.kind]} zoom={zoom} sel={selected === it.id} pid={project.id}
                  media={mediaByUrl[it.src ?? '']}
                  onDown={(e, mode) => {
                    e.stopPropagation();
                    useStore.getState().select(it.id);
                    const m = mediaByUrl[it.src ?? ''];
                    const maxOut = it.type === 'video' || it.type === 'audio' ? (m?.duration ?? it.out) : 3600;
                    setDrag(mode === 'move'
                      ? { mode, id: it.id, x0: e.clientX, y0: e.clientY, start0: it.start, track0: tr.id }
                      : { mode, id: it.id, x0: e.clientX, item0: it, maxOut, media: m?.name });
                  }} />;
              })}
              {preview && preview.track === tr.id && !tr.items.some(i => i.id === preview.id) && (() => {
                const f = useStore.getState().findItem(preview.id);
                return f ? <Clip it={{ ...f.item, start: preview.start }} color={COLORS[tr.kind]} zoom={zoom} sel pid={project.id} onDown={() => {}} /> : null;
              })()}
            </div>
          ))}
          <Playhead zoom={zoom} />
        </div>
      </div>
    </div>
  );
}

// oynatma kafasi ayri: oynarken saniyede 30 kez sadece bu cizilir, tum timeline degil
function Playhead({ zoom }: { zoom: number }) {
  const time = useStore(s => s.time);
  return <div className="playhead" style={{ left: HEAD + time * zoom }} />;
}

interface Mark { t: number; label: string; color?: string }

function Clip({ it, color, zoom, sel, pid, media, onDown }: {
  it: Item; color: string; zoom: number; sel: boolean; pid: string; media?: Media;
  onDown: (e: React.PointerEvent, mode: 'move' | 'left' | 'right') => void;
}) {
  const w = Math.max(6, itemDur(it) * zoom);
  const label = it.type === 'text' ? it.props.text : it.type === 'caption'
    ? (it.props.words ?? []).map(x => x.w).join(' ') : it.src?.split('/').pop();
  return (
    <div className={`clip ${sel ? 'sel' : ''}`} style={{ left: HEAD + it.start * zoom, width: w, background: color + '33', borderColor: color }}
      onPointerDown={e => onDown(e, 'move')}>
      {it.type === 'video' && media && <Thumbs pid={pid} name={media.name} it={it} w={w} />}
      {(it.type === 'audio' || (it.type === 'video' && media?.has_audio)) && media && <Wave pid={pid} name={media.name} it={it} media={media} w={w} color={color} />}
      <span className="clip-label ell">{label}</span>
      {/* oneri isaretleri (props.marks, kaynak saniyesi): kirpinca/tasiyinca kaynaktaki yerinde kalir */}
      {(it.props.marks as Mark[] | undefined)?.map((m, i) => {
        const x = (m.t - it.in) / (it.speed || 1) * zoom;
        if (x < -1 || x > w + 1) return null;
        return <div key={i} className="mark" style={{ left: x, borderColor: m.color ?? '#FDE047' }} title={m.label}>
          <span style={{ background: m.color ?? '#FDE047' }}>{m.label}</span></div>;
      })}
      {it.speed !== 1 && <span className="clip-badge">{it.speed}x</span>}
      <div className="handle l" onPointerDown={e => onDown(e, 'left')} />
      <div className="handle r" onPointerDown={e => onDown(e, 'right')} />
    </div>
  );
}

function Thumbs({ pid, name, it, w }: { pid: string; name: string; it: Item; w: number }) {
  const n = Math.max(1, Math.min(12, Math.floor(w / 56)));
  return (
    <div className="thumbs">
      {Array.from({ length: n }, (_, i) => {
        const t = it.in + ((it.out - it.in) * (i + 0.5)) / n;
        return <img key={i} src={`/api/projects/${pid}/media/${encodeURIComponent(name)}/thumb?t=${Math.round(t * 2) / 2}`} draggable={false} />;
      })}
    </div>
  );
}

// ses haritasi: medya basina bir kez yuklenir; kenar surukleme bunu senkron okur
const amaps: Record<string, AudioMap> = {};
const amapReq: Record<string, Promise<AudioMap>> = {};
const snapSilence = (t: number, pts: number[], reach: number) => {
  let best = t, bd = reach;
  for (const p of pts) if (Math.abs(p - t) < bd) { bd = Math.abs(p - t); best = p; }
  return best;
};

function Wave({ pid, name, it, media, w, color }: { pid: string; name: string; it: Item; media: Media; w: number; color: string }) {
  const [am, setAm] = useState<AudioMap | null>(amaps[pid + name] ?? null);
  useEffect(() => {
    if (!media.url.startsWith('/media/')) return;
    const k = pid + name;
    amapReq[k] ??= api.audiomap(pid, name).then(m => (amaps[k] = m));
    amapReq[k].then(setAm).catch(() => {});
  }, [pid, name]);
  if (!am || !media.duration) return null;
  const sp = it.speed || 1;
  const toX = (t: number) => ((t - it.in) / sp / ((it.out - it.in) / sp)) * w;
  const a = Math.max(0, Math.floor(it.in * am.pps));
  const b = Math.min(am.peaks.length, Math.ceil(it.out * am.pps));
  const slice = am.peaks.slice(a, b);
  const bars = Math.max(1, Math.min(slice.length, Math.floor(w / 2)));
  return (
    <svg className="wave" viewBox={`0 0 ${w} 100`} preserveAspectRatio="none">
      {/* sessiz araliklar: koyu bant = kesmek icin guvenli bosluk */}
      {am.silences.filter(([s, e]) => e > it.in && s < it.out).map(([s, e], i) => (
        <rect key={'s' + i} x={Math.max(0, toX(s))} y={0} width={Math.max(1, toX(Math.min(e, it.out)) - Math.max(0, toX(s)))} height={100} className="sil" />
      ))}
      {Array.from({ length: bars }, (_, i) => {
        // her cubuk kendi araligindaki en yuksek degeri gosterir (kisa kelimeler kaybolmasin)
        const lo = Math.floor((i / bars) * slice.length), hi = Math.max(lo + 1, Math.floor(((i + 1) / bars) * slice.length));
        let v = 0;
        for (let k = lo; k < hi; k++) v = Math.max(v, slice[k] ?? 0);
        const h = Math.max(1.5, v * 96 * Math.min(1.3, Math.sqrt(it.volume || 0)));
        return <rect key={i} x={(i / bars) * w} y={100 - h} width={Math.max(0.6, (w / bars) * 0.8)} height={h} fill={color} />;
      })}
    </svg>
  );
}
