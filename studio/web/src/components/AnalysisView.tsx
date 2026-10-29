import { useEffect, useMemo, useRef, useState } from 'react';
import { ExperimentsTab } from './ExperimentsTab';

// grafik renkleri (dataviz dogrulandi, koyu yuzey #16181F): tek seri = mavi; diverging = mavi (+) / kirmizi (-)
const BLUE = '#3987e5';
const RED = '#e66767';
const INK = '#E8EAF0';
const MUTED = '#8A90A2';
const GRID = '#2A2E3A';

type Upload = { id: string; title: string; published: string; privacy: string; views: number; likes: number; comments: number; avd: number | null; avp: number | null; subs: number | null; thumb?: string };
type Channel = { channel: string; title: string; subs: number; views: number; videos: number; uploads: Upload[] };
const nf = (n: number) => n.toLocaleString('tr-TR');

export function AnalysisView({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<'channel' | 'research' | 'exp'>('channel');
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <b>📊 Analiz</b>
          <div className="seg">
            <button className={tab === 'channel' ? 'on' : ''} onClick={() => setTab('channel')}>Kanallar</button>
            <button className={tab === 'research' ? 'on' : ''} onClick={() => setTab('research')}>Hook araştırması</button>
            <button className={tab === 'exp' ? 'on' : ''} onClick={() => setTab('exp')}>Deneyler</button>
          </div>
          <div className="grow" />
          <button className="btn ghost" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{tab === 'channel' ? <ChannelTab /> : tab === 'research' ? <ResearchTab /> : <ExperimentsTab />}</div>
      </div>
    </div>
  );
}

function ChannelTab() {
  const [chs, setChs] = useState<string[]>([]);
  const [ch, setCh] = useState('');
  const [data, setData] = useState<Channel | null>(null);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState<Upload | null>(null);
  useEffect(() => { fetch('/api/analysis/channels').then(r => r.json()).then((l: string[]) => { setChs(l); setCh(l[0] ?? ''); }); }, []);
  useEffect(() => {
    if (!ch) return;
    setData(null); setErr(''); setSel(null);
    fetch(`/api/analysis/channel/${ch}`).then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json(); })
      .then(setData).catch(e => setErr(String(e.message ?? e)));
  }, [ch]);
  if (!chs.length) return <div className="muted">Bağlı kanal yok. Terminalde: <code>venv/Scripts/python youtube_api.py auth whatif</code></div>;
  return (
    <div className="stack">
      <div className="row">
        <select className="input" style={{ width: 200 }} value={ch} onChange={e => setCh(e.target.value)}>{chs.map(c => <option key={c}>{c}</option>)}</select>
        {data && <span className="muted small">{data.title}</span>}
      </div>
      {err && <div className="pill err">{err}</div>}
      {!data && !err && <div className="muted"><span className="spinner" />yükleniyor…</div>}
      {data && (
        <>
          <div className="tiles">
            <Tile label="Abone" value={nf(data.subs)} />
            <Tile label="Toplam izlenme" value={nf(data.views)} />
            <Tile label="Video" value={nf(data.videos)} />
            <Tile label="Son 28 gün en iyi" value={nf(Math.max(0, ...data.uploads.map(u => u.views)))} />
          </div>
          <div className="split2">
            <div className="tablewrap">
              <table className="tbl">
                <thead><tr><th>Video</th><th className="r">İzlenme</th><th className="r">Ort. sn</th><th className="r">Ort. %</th><th className="r">Beğeni</th></tr></thead>
                <tbody>
                  {data.uploads.map(u => (
                    <tr key={u.id} className={sel?.id === u.id ? 'on' : ''} onClick={() => setSel(u)} title="İzleyici tutma eğrisini göster">
                      <td><div className="row">{u.thumb && <img className="vthumb" src={u.thumb} />}<div><div className="ell2">{u.title}</div>
                        <div className="muted small">{new Date(u.published).toLocaleDateString('tr-TR')} · {u.privacy}</div></div></div></td>
                      <td className="r">{nf(u.views)}</td><td className="r">{u.avd != null ? u.avd.toFixed(0) : '–'}</td>
                      <td className="r">{u.avp != null ? u.avp.toFixed(0) : '–'}</td><td className="r">{nf(u.likes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="muted small">Ortalama süre/yüzde YouTube'dan 1–2 gün gecikmeli gelir.</div>
            </div>
            <div>{sel ? <Retention ch={ch} video={sel} /> : <div className="muted center" style={{ marginTop: 60 }}>Soldan bir video seç → izleyici tutma eğrisi</div>}</div>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return <div className="tile"><div className="muted small">{label}</div><div className="tval">{value}</div></div>;
}

function Retention({ ch, video }: { ch: string; video: Upload }) {
  const [d, setD] = useState<{ duration: number; curve: { at: number; watch: number; relative: number }[] } | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => { setD(null); fetch(`/api/analysis/retention/${ch}/${video.id}`).then(r => r.json()).then(setD); }, [video.id]);
  const W = 520, H = 260, L = 44, R = 12, T = 14, B = 30;
  const pts = useMemo(() => d?.curve.map(p => ({ t: p.at * d.duration, y: p.watch * 100 })) ?? [], [d]);
  if (!d) return <div className="muted"><span className="spinner" />eğri yükleniyor…</div>;
  if (!pts.length) return <div className="muted">Bu video için henüz izleyici tutma verisi yok (YouTube 1–2 gün gecikmeli).</div>;
  const ymax = Math.max(100, ...pts.map(p => p.y)) * 1.05;
  const x = (t: number) => L + (t / d.duration) * (W - L - R);
  const y = (v: number) => T + (1 - v / ymax) * (H - T - B);
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.y).toFixed(1)}`).join(' ');
  // en sert dusus: 1 sn'lik pencerede en buyuk kayip
  let worst = { i: 0, drop: 0 };
  pts.forEach((p, i) => {
    const j = pts.findIndex(q => q.t >= p.t + 1);
    if (j > 0 && p.y - pts[j].y > worst.drop) worst = { i, drop: p.y - pts[j].y };
  });
  const end = pts[pts.length - 1].y;
  const hp = hover != null ? pts[hover] : null;
  const ticks = [0, 25, 50, 75, 100].filter(v => v <= ymax);
  return (
    <div className="stack">
      <div className="ell"><b>{video.title}</b></div>
      <div className="row gap">
        <span className="pill">Sonda kalan: <b>%{end.toFixed(0)}</b></span>
        {worst.drop > 0 && <span className="pill">En sert kayıp: <b>{pts[worst.i].t.toFixed(1)}–{(pts[worst.i].t + 1).toFixed(1)} sn</b> (−{worst.drop.toFixed(0)} puan)</span>}
      </div>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="chart"
        onMouseMove={e => {
          const r = svg.current!.getBoundingClientRect();
          const t = ((e.clientX - r.left) / r.width * W - L) / (W - L - R) * d.duration;
          let best = 0;
          pts.forEach((p, i) => { if (Math.abs(p.t - t) < Math.abs(pts[best].t - t)) best = i; });
          setHover(best);
        }} onMouseLeave={() => setHover(null)}>
        {ticks.map(v => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={v === 100 ? 1.5 : 1} strokeDasharray={v === 100 ? '4 4' : undefined} />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fill={MUTED} fontSize="11">%{v}</text></g>)}
        {[0, 0.25, 0.5, 0.75, 1].map(f => <text key={f} x={x(f * d.duration)} y={H - 10} textAnchor="middle" fill={MUTED} fontSize="11">{(f * d.duration).toFixed(0)} sn</text>)}
        {worst.drop > 0 && <rect x={x(pts[worst.i].t)} y={T} width={x(pts[worst.i].t + 1) - x(pts[worst.i].t)} height={H - T - B} fill={RED} opacity={0.12} />}
        <path d={path} fill="none" stroke={BLUE} strokeWidth={2} strokeLinejoin="round" />
        {hp && <g>
          <line x1={x(hp.t)} x2={x(hp.t)} y1={T} y2={H - B} stroke={MUTED} strokeWidth={1} />
          <circle cx={x(hp.t)} cy={y(hp.y)} r={4.5} fill={BLUE} stroke="#16181F" strokeWidth={2} />
          <g transform={`translate(${Math.min(x(hp.t) + 8, W - 128)},${Math.max(y(hp.y) - 40, T)})`}>
            <rect width={118} height={36} rx={6} fill="#0E0F13" stroke={GRID} />
            <text x={8} y={15} fill={MUTED} fontSize="11">{hp.t.toFixed(1)} sn</text>
            <text x={8} y={29} fill={INK} fontSize="12" fontWeight={600}>%{hp.y.toFixed(0)} izliyor</text>
          </g>
        </g>}
      </svg>
      <div className="muted small">%100 üstü = tekrar izlemeler (loop). Kırmızı bant: 1 saniyede en çok izleyici kaybedilen yer.</div>
    </div>
  );
}

const LABELS: Record<string, string> = {
  shock_number: 'şok rakam', question: 'soru', danger: 'tehlike', danger_threat: 'tehlike', you_pov: '"sen" POV', myth_bust: 'yanlış inanış',
  curiosity_gap: 'merak boşluğu', bold_claim: 'iddialı cümle', story: 'hikâye', story_start: 'hikâye', celebrity: 'ünlü/marka',
  celebrity_name: 'ünlü', label_only: 'düz konu adı', visual_only: 'sözsüz görsel', curiosity: 'merak', fear: 'korku', humor: 'mizah',
  awe: 'hayranlık', outrage: 'öfke/drama', satisfying: 'tatmin edici', relatable: 'özdeşleşme', has_number: 'başlıkta rakam',
  you: 'başlıkta "you"', what_if: '"what if" kalıbı', caps_word: 'BÜYÜK kelime', emoji: 'emoji', short_title: 'kısa başlık (≤5 kelime)',
  exclaim: 'ünlem', reaction_moment: 'tek şok anı', explainer: 'açıklama', list_facts: 'liste', escalation: 'tırmanış',
};
const lab = (k: string) => { const [a, b] = k.split('='); return b ? `${LABELS[b] ?? b}` + (a === 'emotion' ? ' (duygu)' : '') : LABELS[a] ?? a; };

function ResearchTab() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { fetch('/api/analysis/research').then(r => r.json()).then(setD); }, []);
  if (!d) return <div className="muted"><span className="spinner" />yükleniyor…</div>;
  const atlas = d.atlas;
  const st = d.atlas_status;
  return (
    <div className="stack">
      <HookLibrary />
      <SpokenHooks niches={Object.keys(d.niches)} />
      <div className="sec">Kanal-içi karşılaştırma (Hook Atlas)</div>
      {st && <div className="muted small">{nf(st.channels[1] ?? 0)}/{nf(st.channels[0])} kanal tarandı · {nf(st.videos[0])} Short · {nf(st.videos[1] ?? 0)} patlamış (≥5× kanal medyanı) · {nf(st.videos[2] ?? 0)} başlık Jev ile etiketlendi</div>}
      {!atlas ? <div className="muted">Atlas raporu henüz hazır değil (tarama → etiketleme → analiz sürüyor).</div> : (
        <>
          <div className="muted small">Patlamış videolarda, AYNI kanalın normal videolarına göre ne kadar daha sık/seyrek görüldüğü (yüzde puan). {nf(atlas.channels_compared)} kanal karşılaştırıldı; |z| ≥ 2 güvenilir.</div>
          <LiftBars rows={atlas.features.filter((f: any) => Math.abs(f.z) >= 1.5).slice(0, 24)} />
          <div className="sec">Örnek: patlamış video vs aynı kanalın normal videoları</div>
          <div className="exgrid">
            {atlas.examples.slice(0, 12).map((e: any) => (
              <a key={e.id} className="excard" href={`https://youtube.com/shorts/${e.id}`} target="_blank">
                <div className="row"><b className="ratio">{e.ratio}×</b><span className="muted small">{nf(e.views)} izlenme · {e.niche}</span></div>
                <div className="ell2"><b>{e.title}</b></div>
                <div className="muted small ell2">normal: {e.channel_normal_titles.join(' · ')}</div>
              </a>
            ))}
          </div>
        </>
      )}
      <div className="sec">Niş örneklemleri (top %25 vs bottom %25, video içeriği)</div>
      {Object.entries(d.niches).map(([n, s]: [string, any]) => (
        <div key={n} className="nichecard">
          <b>{n}</b> <span className="muted small">{s.n} video · top medyan {s.median_outlier_top}× · bottom {s.median_outlier_bottom}×</span>
          <div className="row gap" style={{ marginTop: 6 }}>
            {s.labels.hook_type.slice(0, 4).map((r: any) => <span key={r.label} className="pill">{lab(r.label)} ×{r.lift}</span>)}
          </div>
          <div className="muted small" style={{ marginTop: 4 }}>Kelime/sn top {s.numeric.wps.top} vs bottom {s.numeric.wps.bottom} · kesim/sn {s.numeric.cps.top} vs {s.numeric.cps.bottom}</div>
        </div>
      ))}
    </div>
  );
}

function LiftBars({ rows }: { rows: { feature: string; diff_pp: number; z: number; channels: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!rows.length) return <div className="muted">Anlamlı fark yok.</div>;
  const m = Math.max(...rows.map(r => Math.abs(r.diff_pp)), 1);
  return (
    <div className="lift">
      {rows.map((r, i) => {
        const w = (Math.abs(r.diff_pp) / m) * 48;
        const pos = r.diff_pp >= 0;
        return (
          <div key={r.feature} className="liftrow" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <span className="liftlab ell">{lab(r.feature)}</span>
            <div className="lifttrack">
              <div className="mid" />
              <div className="liftbar" style={{ left: pos ? '50%' : `${50 - w}%`, width: `${w}%`, background: pos ? BLUE : RED,
                borderRadius: pos ? '0 4px 4px 0' : '4px 0 0 4px' }} />
            </div>
            <span className="liftval">{pos ? '+' : ''}{r.diff_pp} pp</span>
            {hover === i && <div className="tip">{lab(r.feature)}: patlamışlarda {pos ? 'daha sık' : 'daha seyrek'} ({pos ? '+' : ''}{r.diff_pp} puan), z={r.z}, {r.channels} kanal</div>}
          </div>
        );
      })}
      <div className="muted small row"><span style={{ color: BLUE }}>■</span> patlamışlarda daha sık <span style={{ color: RED, marginLeft: 10 }}>■</span> daha seyrek</div>
    </div>
  );
}

type HookItem = { id: string; title: string; ratio: number; views: number; channel: string; niche: string; channel_median: number;
  labels: Record<string, string | boolean>; normals: string[] };

// Hook kutuphanesi: kanalina gore patlamis Short'larin GERCEK basliklari, tipine gore filtrelenir
function HookLibrary() {
  const [niche, setNiche] = useState('');
  const [hook, setHook] = useState('');
  const [emotion, setEmotion] = useState('');
  const [q, setQ] = useState('');
  const [minRatio, setMinRatio] = useState(5);
  const [data, setData] = useState<{ items: HookItem[]; total: number; facets: { hook: Record<string, number>; emotion: Record<string, number> } } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [limit, setLimit] = useState(40);
  useEffect(() => {
    const t = setTimeout(() => {
      const u = new URLSearchParams({ niche, hook, emotion, q, min_ratio: String(minRatio), limit: String(limit) });
      fetch(`/api/analysis/hooks?${u}`).then(r => r.json()).then(setData);
    }, 250);
    return () => clearTimeout(t);
  }, [niche, hook, emotion, q, minRatio, limit]);
  const facets = data?.facets;
  return (
    <div className="stack">
      <div className="sec">📚 Hook kütüphanesi <span className="muted small">— kanalının kaç katı izlenmiş gerçek videolar</span></div>
      <div className="row gap">
        <select className="input" style={{ width: 150 }} value={niche} onChange={e => setNiche(e.target.value)}>
          <option value="">Tüm nişler</option><option value="whatif">What if / bilim</option><option value="character">Karakter</option><option value="podcast">Podcast</option>
        </select>
        <select className="input" style={{ width: 150 }} value={emotion} onChange={e => setEmotion(e.target.value)}>
          <option value="">Tüm duygular</option>
          {facets && Object.entries(facets.emotion).sort((a, b) => b[1] - a[1]).map(([k, n]) => <option key={k} value={k}>{lab(k)} ({n})</option>)}
        </select>
        <select className="input" style={{ width: 130 }} value={minRatio} onChange={e => setMinRatio(+e.target.value)}>
          {[3, 5, 10, 25, 50].map(r => <option key={r} value={r}>≥ {r}× kanal</option>)}
        </select>
        <input className="input" style={{ width: 200 }} placeholder="Başlıkta ara…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="row gap">
        <button className={`chip ${!hook ? 'on' : ''}`} onClick={() => setHook('')}>Hepsi</button>
        {facets && Object.entries(facets.hook).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
          <button key={k} className={`chip ${hook === k ? 'on' : ''}`} onClick={() => setHook(k)}>{lab(k)} <span className="muted">{n}</span></button>
        ))}
      </div>
      {!data ? <div className="muted"><span className="spinner" />yükleniyor…</div> : (
        <>
          <div className="muted small">{nf(data.total)} sonuç (etiketleme sürdükçe artar)</div>
          <div className="hooklist">
            {data.items.map(it => (
              <div key={it.id} className="hookrow">
                <span className="ratio">{it.ratio}×</span>
                <div className="grow">
                  <a href={`https://youtube.com/shorts/${it.id}`} target="_blank" className="htitle">{it.title}</a>
                  <div className="muted small">{it.channel} · {nf(it.views)} izlenme (kanal normali {nf(it.channel_median)}) · {it.labels.hook ? `${lab(String(it.labels.hook))} · ${lab(String(it.labels.emotion))}` : 'tip etiketi yok'}
                    {' '}<button className="linkbtn" onClick={() => setOpen(open === it.id ? null : it.id)}>{open === it.id ? 'gizle' : 'aynı kanalın normalleri'}</button></div>
                  {open === it.id && <div className="normals">{it.normals.length ? it.normals.map((n, i) => <div key={i}>· {n}</div>) : <div className="muted">örnek yok</div>}</div>}
                </div>
              </div>
            ))}
          </div>
          {data.items.length < data.total && <button className="btn sm" onClick={() => setLimit(l => l + 40)}>Daha fazla göster</button>}
        </>
      )}
    </div>
  );
}

// videonun ilk 3 saniyesinde SOYLENEN cumle (Whisper) - baslik degil
function SpokenHooks({ niches }: { niches: string[] }) {
  const [niche, setNiche] = useState(niches[0] ?? 'whatif');
  const [rows, setRows] = useState<{ id: string; title: string; hook: string; ratio: number; views: number; group: string; type: string; wps: number }[]>([]);
  useEffect(() => { fetch(`/api/analysis/spoken-hooks?niche=${niche}`).then(r => r.json()).then(setRows); }, [niche]);
  return (
    <div className="stack">
      <div className="sec">🗣 Konuşulan hook'lar <span className="muted small">— ilk 3 saniyede söylenen cümle (indirilen örnekler)</span></div>
      <div className="row gap">{niches.map(n => <button key={n} className={`chip ${niche === n ? 'on' : ''}`} onClick={() => setNiche(n)}>{n}</button>)}</div>
      <div className="hooklist short">
        {rows.map(r => (
          <div key={r.id} className="hookrow">
            <span className={`grp ${r.group}`}>{r.group === 'top' ? 'EN İYİ' : r.group === 'bottom' ? 'EN KÖTÜ' : 'orta'}</span>
            <div className="grow">
              <div>"{r.hook || '— sözsüz açılış —'}"</div>
              <div className="muted small"><a href={`https://youtube.com/shorts/${r.id}`} target="_blank">{r.title}</a> · {r.ratio}× · {nf(r.views)} izlenme · {lab(r.type ?? '')} · {r.wps} kelime/sn</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
