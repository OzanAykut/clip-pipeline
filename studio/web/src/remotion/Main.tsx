import React from 'react';
import { AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Item, Project, Track } from '../types';
import { itemDur } from '../types';
import { Caption } from './captions';

export interface MainProps {
  project: Project;
  mediaBase: string; // onizlemede '' (vite proxy), renderda 'http://127.0.0.1:8765'
}

const url = (base: string, src?: string) => (!src ? '' : src.startsWith('http') ? src : base + src);

export const TRANSITIONS = [
  { id: 'fade', name: 'Fade' }, { id: 'slide-left', name: 'Sola kay' }, { id: 'slide-up', name: 'Yukarı kay' },
  { id: 'slide-right', name: 'Sağa kay' }, { id: 'zoom', name: 'Zoom' }, { id: 'wipe', name: 'Silme' },
  { id: 'circle', name: 'Daire açılış' },
];

type Speech = [number, number][]; // konusma araliklari (timeline sn) - muzik kisma icin

// muzik kisma: konusma araligina yaklastikca kazanc duck seviyesine iner (0.25 sn yumusak gecis)
const duckGain = (t: number, speech: Speech, level: number) => {
  let d = Infinity;
  for (const [s, e] of speech) {
    if (t >= s - 0.1 && t <= e + 0.15) return level;
    d = Math.min(d, Math.abs(t - s), Math.abs(t - e));
  }
  return level + (1 - level) * Math.min(1, d / 0.3);
};

// fade giris/cikis + ses seviyesi (+ istege bagli kisma). f = sequence icindeki kare
const volumeFn = (it: Item, fps: number, muted: boolean, speech: Speech, extra = 0) => (f: number) => {
  if (muted) return 0;
  const d = itemDur(it) * fps;
  const fi = Math.max(1, it.fadeIn * fps);
  const fo = Math.max(1, it.fadeOut * fps);
  const a = it.fadeIn > 0 ? interpolate(f, [0, fi], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
  const b = it.fadeOut > 0 ? interpolate(f, [d - fo, d], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
  // gecis uzantisinda (sonraki klip ustune gelirken) ses kisilarak cikar
  const x = extra > 0 && f > d ? interpolate(f, [d, d + extra * fps], [1, 0], { extrapolateRight: 'clamp' }) : 1;
  const duck = it.props.duck ? duckGain(it.start + f / fps, speech, (it.props.duckLevel as number) ?? 0.3) : 1;
  return Math.max(0, it.volume * a * b * x * duck);
};

const VisualFade: React.FC<{ it: Item; children: React.ReactNode }> = ({ it, children }) => {
  const f = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const d = itemDur(it) * fps;
  const a = it.fadeIn > 0 ? interpolate(f, [0, it.fadeIn * fps], [0, 1], { extrapolateRight: 'clamp' }) : 1;
  const b = it.fadeOut > 0 ? interpolate(f, [d - it.fadeOut * fps, d], [1, 0], { extrapolateLeft: 'clamp' }) : 1;
  // giris gecisi: onceki klip altta devam ederken bu klip efektle gelir
  const tr = it.transition;
  let style: React.CSSProperties = { opacity: Math.min(a, b) };
  if (tr && tr.dur > 0) {
    const p = interpolate(f, [0, tr.dur * fps], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
    const ease = 1 - Math.pow(1 - p, 3);
    if (tr.type === 'fade') style.opacity = Math.min(a, b) * ease;
    if (tr.type === 'slide-left') style.transform = `translateX(${(1 - ease) * width}px)`;
    if (tr.type === 'slide-right') style.transform = `translateX(${-(1 - ease) * width}px)`;
    if (tr.type === 'slide-up') style.transform = `translateY(${(1 - ease) * 100}%)`;
    if (tr.type === 'zoom') style = { ...style, transform: `scale(${0.6 + 0.4 * ease})`, opacity: Math.min(a, b) * ease };
    if (tr.type === 'wipe') style.clipPath = `inset(0 ${(1 - ease) * 100}% 0 0)`;
    if (tr.type === 'circle') style.clipPath = `circle(${ease * 75}% at 50% 50%)`;
  }
  return <AbsoluteFill style={style}>{children}</AbsoluteFill>;
};

const ItemView: React.FC<{ it: Item; track: Track; base: string; speech: Speech; extra: number; maxSrc: number }> = (
  { it, track, base, speech, extra, maxSrc }) => {
  const { fps } = useVideoConfig();
  const vol = volumeFn(it, fps, track.muted, speech, extra);
  const fit = it.props.fit ?? 'cover';
  const scale = it.props.scale ?? 1;
  const x = it.props.x ?? 0.5;
  const y = it.props.y ?? 0.5;
  const placed: React.CSSProperties = {
    position: 'absolute', left: `${x * 100}%`, top: `${y * 100}%`,
    transform: `translate(-50%, -50%) scale(${scale})`, width: '100%', height: '100%', objectFit: fit,
  };
  if (it.type === 'video' && !it.props.radius) {
    return (
      <VisualFade it={it}>
        <OffthreadVideo src={url(base, it.src)} trimBefore={Math.round(it.in * fps)}
          trimAfter={Math.round(Math.min(maxSrc, it.out + extra * it.speed) * fps)}
          playbackRate={it.speed} volume={vol} style={placed} />
      </VisualFade>
    );
  }
  // kose (pip) B-roll: yuvarlak kenarli, cerceveli kart
  const radius = it.props.radius as number | undefined;
  if (radius && (it.type === 'video' || it.type === 'image')) {
    const box: React.CSSProperties = {
      position: 'absolute', left: `${x * 100}%`, top: `${y * 100}%`, width: `${scale * 100}%`, aspectRatio: '9/16',
      transform: 'translate(-50%, -50%)', borderRadius: radius, overflow: 'hidden',
      border: it.props.border ? '6px solid #fff' : undefined, boxShadow: '0 12px 30px rgba(0,0,0,.55)',
    };
    const fill: React.CSSProperties = { width: '100%', height: '100%', objectFit: 'cover' };
    return (
      <VisualFade it={it}><div style={box}>
        {it.type === 'video'
          ? <OffthreadVideo src={url(base, it.src)} trimBefore={Math.round(it.in * fps)} trimAfter={Math.round(it.out * fps)} volume={0} style={fill} />
          : <Img src={url(base, it.src)} style={fill} />}
      </div></VisualFade>
    );
  }
  if (it.type === 'image') {
    return <VisualFade it={it}><Img src={url(base, it.src)} style={placed} /></VisualFade>;
  }
  if (it.type === 'audio') {
    return <Audio src={url(base, it.src)} trimBefore={Math.round(it.in * fps)} trimAfter={Math.round(it.out * fps)}
      playbackRate={it.speed} volume={vol} />;
  }
  if (it.type === 'text' && it.props.card) {
    // manset karti (smart_render'daki beyaz yuvarlak kart): *kelime* kirmizi vurgu
    const parts = String(it.props.text ?? '').split(/(\*[^*]+\*)/g);
    return (
      <VisualFade it={it}>
        {/* tam genislikte satir + ortalanmis kart: left:50% + translate kartin genisligini yariya kisiyordu */}
        <div style={{ position: 'absolute', left: 0, right: 0, top: `${y * 100}%`, display: 'flex',
          justifyContent: 'center', transform: `translate(${(x - 0.5) * 100}%, -50%)` }}>
          <div style={{
            maxWidth: '84%', background: '#fff', color: '#111', borderRadius: 30, padding: '22px 34px',
            fontFamily: 'KlipBlack, sans-serif', fontSize: it.props.size ?? 64, lineHeight: 1.12, textAlign: 'center',
            boxShadow: '0 10px 0 rgba(0,0,0,.35)', transform: `scale(${scale})`,
          }}>
            {parts.map((s, i) => s.startsWith('*') ? <span key={i} style={{ color: '#E53935' }}>{s.slice(1, -1)}</span> : s)}
          </div>
        </div>
      </VisualFade>
    );
  }
  if (it.type === 'text') {
    return (
      <VisualFade it={it}>
        <div style={{
          position: 'absolute', left: `${x * 100}%`, top: `${y * 100}%`, transform: `translate(-50%, -50%) scale(${scale})`,
          fontFamily: 'KlipBlack, sans-serif', fontSize: it.props.size ?? 80, color: it.props.color ?? '#fff',
          textAlign: 'center', width: '90%', lineHeight: 1.1, WebkitTextStroke: '3px #000', textShadow: '0 6px 0 #000',
          whiteSpace: 'pre-wrap',
        }}>{it.props.text}</div>
      </VisualFade>
    );
  }
  if (it.type === 'caption') return <Caption it={it} />;
  return null;
};

// cizim sirasi: alttan uste
const ORDER: Record<string, number> = { video: 0, overlay: 1, caption: 2, voice: 3, music: 3, sfx: 3 };

export const Main: React.FC<MainProps> = ({ project, mediaBase }) => {
  const { fps } = useVideoConfig();
  const tracks = [...project.tracks].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
  // konusma araliklari = altyazi kelimeleri (muzik kisma bunlara gore)
  const speech: Speech = project.tracks.filter(t => t.kind === 'caption').flatMap(t => t.items.flatMap(
    it => (it.props.words ?? []).map(w => [it.start + w.s, it.start + w.e] as [number, number])));
  // gecis: B klibinde gecis varsa ve A hemen ondan once bitiyorsa, A gecis suresi kadar uzatilir (ustune B gelir)
  const extra: Record<string, number> = {};
  for (const t of project.tracks) {
    const items = [...t.items].sort((a, b) => a.start - b.start);
    items.forEach((b, i) => {
      const a = items[i - 1];
      if (a && b.transition?.dur && Math.abs(a.start + itemDur(a) - b.start) < 0.05) extra[a.id] = b.transition.dur;
    });
  }
  const srcDur = Object.fromEntries(project.media.map(m => [m.url, m.duration]));
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <style>{`@font-face{font-family:KlipBlack;src:url(${mediaBase}/library/fonts/Montserrat-Black.ttf)}`}</style>
      {tracks.filter(t => !t.hidden).map(t => (
        <React.Fragment key={t.id}>
          {t.items.map(it => {
            const from = Math.round(it.start * fps);
            const ext = extra[it.id] ?? 0;
            const dur = Math.max(1, Math.round((itemDur(it) + ext) * fps));
            return (
              <Sequence key={it.id} from={from} durationInFrames={dur} layout={it.type === 'audio' ? 'none' : 'absolute-fill'}
                premountFor={it.type === 'video' || it.type === 'audio' ? fps : 0}>
                <ItemView it={it} track={t} base={mediaBase} speech={speech} extra={ext}
                  maxSrc={srcDur[it.src ?? ''] ?? it.out + ext * it.speed} />
              </Sequence>
            );
          })}
        </React.Fragment>
      ))}
    </AbsoluteFill>
  );
};
