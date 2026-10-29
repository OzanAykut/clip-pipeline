import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { AnimatedCaptions, type CaptionData } from 'captioneer-ui';
import { presets, getPresetCategories } from 'captioneer-presets';
import type { Item, Word } from '../types';

// remotion-captioneer (MIT) preset'leri: id'si "cap:<preset>" olan stiller bu kutuphaneyle cizilir
export const CAPTIONEER_PRESETS = Object.entries(getPresetCategories()).flatMap(([cat, names]) =>
  names.map(n => ({ id: `cap:${n}`, name: presets[n].name, desc: (presets[n].description as string) ?? '', category: cat })));

const toCaptionData = (words: Word[]): CaptionData => {
  const segs: CaptionData['segments'] = [];
  for (const w of words) {
    const cw = { word: w.w, startMs: Math.round(w.s * 1000), endMs: Math.round(w.e * 1000), confidence: 1 };
    const last = segs[segs.length - 1];
    if (!last || cw.startMs - last.endMs > 450 || last.words.length >= 8 || /[.?!]$/.test(last.words[last.words.length - 1].word)) {
      segs.push({ text: cw.word, startMs: cw.startMs, endMs: cw.endMs, words: [cw] });
    } else {
      last.words.push(cw);
      last.text += ' ' + cw.word;
      last.endMs = cw.endMs;
    }
  }
  return { segments: segs, language: 'en', durationMs: segs.length ? segs[segs.length - 1].endMs : 0 };
};

// Altyazi stilleri. "pop" = mevcut pipeline stilimiz (smart_render: 3 kelimelik grup, aktif kelime yesil/sari ve buyuk).
export const CAPTION_STYLES: { id: string; name: string; desc: string }[] = [
  { id: 'pop', name: 'Pop (bizim)', desc: 'Gruplar zıplayarak gelir, aktif kelime yeşil/sarı' },
  { id: 'karaoke', name: 'Karaoke', desc: 'Kelimeler söylendikçe dolar' },
  { id: 'pill', name: 'Pill', desc: 'Aktif kelime renkli kapsül içinde' },
  { id: 'bold-white', name: 'Kalın beyaz', desc: 'Tek kelime, büyük, siyah konturlu' },
  { id: 'podcast', name: 'Podcast', desc: 'Alt yarıda sade iki satır' },
  { id: 'glow', name: 'Glow', desc: 'Neon parıltılı aktif kelime' },
];

const ACTIVE = ['#3CFF3C', '#FFE500'];

function groups(words: Word[], maxWords = 3, maxChars = 16, pause = 0.35): Word[][] {
  const out: Word[][] = [];
  for (const w of words) {
    const g = out[out.length - 1];
    const text = g ? g.map(x => x.w).join(' ') + ' ' + w.w : w.w;
    if (!g || g.length >= maxWords || text.length > maxChars || w.s - g[g.length - 1].e > pause || /[.?!,]$/.test(g[g.length - 1].w)) {
      out.push([w]);
    } else g.push(w);
  }
  return out;
}

export const Caption: React.FC<{ it: Item }> = ({ it }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const words = it.props.words ?? [];
  const style = (it.props.style as string) ?? 'pop';
  if (style.startsWith('cap:')) {
    const pr = presets[style.slice(4)];
    if (pr) {
      const { name: _n, description: _d, category: _c, ...props } = pr as Record<string, unknown>;
      return <AnimatedCaptions captions={toCaptionData(words)} {...(props as object)}
        fontSize={(it.props.size as number) ?? ((pr.fontSize ?? 64) * 1.35)} />;
    }
  }
  const y = it.props.y ?? (style === 'podcast' ? 0.8 : 0.7);
  const size = it.props.size ?? 92;
  const one = style === 'bold-white';
  const gs = groups(words, one ? 1 : style === 'podcast' ? 6 : 3, one ? 30 : style === 'podcast' ? 32 : 16);
  const gi = gs.findIndex((g, i) => t >= g[0].s && t < (gs[i + 1]?.[0].s ?? g[g.length - 1].e + 0.4));
  if (gi < 0) return null;
  const g = gs[gi];
  const start = g[0].s;
  const pop = spring({ frame: frame - Math.round(start * fps), fps, config: { damping: 12, stiffness: 220 } });
  const accent = ACTIVE[gi % ACTIVE.length];

  const base: React.CSSProperties = {
    position: 'absolute', left: '50%', top: `${y * 100}%`, transform: `translate(-50%, -50%) scale(${style === 'pop' || one ? 0.7 + 0.3 * pop : 1})`,
    width: '88%', textAlign: 'center', fontFamily: 'KlipBlack, sans-serif', fontSize: size, lineHeight: 1.15,
    textTransform: style === 'podcast' ? 'none' : 'uppercase', color: '#fff',
    WebkitTextStroke: style === 'podcast' ? '0' : '6px #000', paintOrder: 'stroke fill',
    textShadow: style === 'podcast' ? '0 3px 10px rgba(0,0,0,.9)' : '0 7px 0 rgba(0,0,0,.85)',
  };
  return (
    <div style={base}>
      {g.map((w, i) => {
        const active = t >= w.s && t < (g[i + 1]?.s ?? w.e + 0.3);
        const done = t >= w.s;
        let s: React.CSSProperties = { display: 'inline-block', margin: '0 0.2em' };
        if (style === 'pop' && active) s = { ...s, color: accent, transform: 'scale(1.12)' };
        if (style === 'karaoke') s = { ...s, color: done ? '#FFE500' : '#fff' };
        if (style === 'pill' && active) s = { ...s, background: '#7C3AED', borderRadius: 18, padding: '0 .18em', WebkitTextStroke: '0' };
        if (style === 'glow' && active) s = { ...s, color: '#9EF', textShadow: '0 0 18px #3BF, 0 0 36px #3BF' };
        if (style === 'podcast') s = { ...s, opacity: done ? 1 : 0.55 };
        if (style === 'bold-white') s = { ...s, fontSize: size * 1.25 };
        const o = style === 'pop' ? interpolate(t, [w.s - 0.02, w.s + 0.05], [0.85, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 1;
        return <span key={i} style={{ ...s, opacity: (s.opacity as number ?? 1) * o }}>{w.w}</span>;
      })}
    </div>
  );
};
