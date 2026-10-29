import { useStore } from '../store';
import { CAPTION_STYLES, CAPTIONEER_PRESETS } from '../remotion/captions';
import { TRANSITIONS } from '../remotion/Main';
import { fromDb, itemDur, toDb, type Item } from '../types';

function Num({ label, value, onChange, min, max, step = 0.1, unit }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; unit?: string;
}) {
  return (
    <label className="field">
      <span className="flabel">{label}<span className="fval">{value.toFixed(step < 1 ? (step < 0.1 ? 2 : 1) : 0)}{unit}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(parseFloat(e.target.value))} />
    </label>
  );
}

export function Inspector() {
  const selected = useStore(s => s.selected);
  useStore(s => s.project); // proje degisince yeniden ciz
  const found = useStore.getState().findItem(selected);
  if (!found) {
    return (
      <div className="inspector">
        <div className="sec">Özellikler</div>
        <div className="muted small">Timeline'da bir öğe seç.</div>
        <div className="help">
          <div><kbd>Boşluk</kbd> oynat / durdur</div>
          <div><kbd>S</kbd> oynatma kafasından böl</div>
          <div><kbd>Del</kbd> seçiliyi sil</div>
          <div><kbd>Ctrl+Z</kbd> / <kbd>Ctrl+Y</kbd> geri / ileri al</div>
          <div><kbd>← →</kbd> kare kare, <kbd>Shift</kbd> ile 1 sn</div>
          <div>Kenarlardan sürükle: kırp / uzat</div>
        </div>
      </div>
    );
  }
  const { item, track } = found;
  const set = (fn: (it: Item) => void) => useStore.getState().commit(p => {
    for (const t of p.tracks) { const it = t.items.find(i => i.id === item.id); if (it) fn(it); }
  });
  const hasAudio = item.type === 'video' || item.type === 'audio';
  const visual = item.type !== 'audio';
  const dur = itemDur(item);
  return (
    <div className="inspector">
      <div className="sec">{({ video: 'Video', audio: 'Ses', image: 'Görsel', text: 'Metin', caption: 'Altyazı' } as const)[item.type]} · <span className="muted">{track.name}</span></div>
      <div className="muted small ell">{item.src?.split('/').pop()}</div>
      <div className="kv"><span>Başlangıç</span><b>{item.start.toFixed(2)} sn</b></div>
      <div className="kv"><span>Süre</span><b>{dur.toFixed(2)} sn</b></div>

      {item.type === 'text' && (
        <>
          <textarea className="input" rows={3} value={item.props.text ?? ''} onChange={e => set(it => { it.props.text = e.target.value; })} />
          <label className="field row"><span className="flabel">Renk</span>
            <input type="color" value={(item.props.color as string) ?? '#ffffff'} onChange={e => set(it => { it.props.color = e.target.value; })} /></label>
          <Num label="Yazı boyutu" value={item.props.size ?? 80} min={24} max={220} step={1} onChange={v => set(it => { it.props.size = v; })} />
          <Num label="Süre" value={dur} min={0.3} max={20} onChange={v => set(it => { it.out = it.in + v; })} unit=" sn" />
        </>
      )}

      {item.type === 'caption' && (
        <label className="field"><span className="flabel">Stil</span>
          <select className="input" value={(item.props.style as string) ?? 'pop'} onChange={e => set(it => { it.props.style = e.target.value; })}>
            {CAPTION_STYLES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            {CAPTIONEER_PRESETS.map(s => <option key={s.id} value={s.id}>{s.category} · {s.name}</option>)}
          </select></label>
      )}

      {hasAudio && (
        <>
          <div className="sec2">Ses</div>
          <Num label="Seviye" value={Math.round(toDb(item.volume))} min={-40} max={12} step={1} unit=" dB"
            onChange={v => set(it => { it.volume = fromDb(v); })} />
          <div className="row gap">
            {[-12, -6, 0, 6].map(db => <button key={db} className="btn sm" onClick={() => set(it => { it.volume = fromDb(db); })}>{db > 0 ? '+' : ''}{db} dB</button>)}
            <button className="btn sm" onClick={() => set(it => { it.volume = 0; })}>Sessiz</button>
          </div>
        </>
      )}

      {track.kind === 'music' && (
        <>
          <label className="check"><input type="checkbox" checked={!!item.props.duck}
            onChange={e => set(it => { it.props.duck = e.target.checked; it.props.duckLevel ??= 0.3; })} />
            Konuşmada müziği otomatik kıs</label>
          {!!item.props.duck && (
            <Num label="Kısma seviyesi" value={Math.round(toDb((item.props.duckLevel as number) ?? 0.3))} min={-30} max={-3} step={1} unit=" dB"
              onChange={v => set(it => { it.props.duckLevel = fromDb(v); })} />
          )}
          <div className="muted small">Konuşma anları altyazılardan alınır; önce altyazı oluştur.</div>
        </>
      )}

      {(item.type === 'video' || item.type === 'image') && (
        <>
          <div className="sec2">Giriş geçişi</div>
          <div className="row">
            <select className="input" value={item.transition?.type ?? ''} onChange={e => set(it => {
              it.transition = e.target.value ? { type: e.target.value, dur: it.transition?.dur ?? 0.4 } : null;
            })}>
              <option value="">Yok</option>
              {TRANSITIONS.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          {item.transition && <Num label="Geçiş süresi" value={item.transition.dur} min={0.15} max={1.5} step={0.05} unit=" sn"
            onChange={v => set(it => { if (it.transition) it.transition.dur = v; })} />}
        </>
      )}

      {(hasAudio || visual) && (
        <>
          <div className="sec2">Fade</div>
          <Num label="Fade giriş" value={item.fadeIn} min={0} max={3} onChange={v => set(it => { it.fadeIn = v; })} unit=" sn" />
          <Num label="Fade çıkış" value={item.fadeOut} min={0} max={3} onChange={v => set(it => { it.fadeOut = v; })} unit=" sn" />
        </>
      )}

      {(item.type === 'video' || item.type === 'audio') && (
        <>
          <div className="sec2">Hız</div>
          <Num label="Hız" value={item.speed} min={0.25} max={3} step={0.05} unit="x" onChange={v => set(it => { it.speed = v; })} />
          <div className="row gap">{[0.5, 1, 1.1, 1.25, 1.5, 2].map(s => <button key={s} className="btn sm" onClick={() => set(it => { it.speed = s; })}>{s}x</button>)}</div>
        </>
      )}

      {visual && item.type !== 'caption' && (
        <>
          <div className="sec2">Kadraj</div>
          <Num label="Ölçek" value={item.props.scale ?? 1} min={0.2} max={3} step={0.05} unit="x" onChange={v => set(it => { it.props.scale = v; })} />
          <Num label="Yatay konum" value={item.props.x ?? 0.5} min={0} max={1} step={0.01} onChange={v => set(it => { it.props.x = v; })} />
          <Num label="Dikey konum" value={item.props.y ?? 0.5} min={0} max={1} step={0.01} onChange={v => set(it => { it.props.y = v; })} />
          {(item.type === 'video' || item.type === 'image') && (
            <div className="row gap">
              <button className={`btn sm ${item.props.fit !== 'contain' ? 'on' : ''}`} onClick={() => set(it => { it.props.fit = 'cover'; })}>Doldur</button>
              <button className={`btn sm ${item.props.fit === 'contain' ? 'on' : ''}`} onClick={() => set(it => { it.props.fit = 'contain'; })}>Sığdır</button>
            </div>
          )}
        </>
      )}
      {item.type === 'caption' && (
        <Num label="Dikey konum" value={item.props.y ?? 0.7} min={0.1} max={0.95} step={0.01} onChange={v => set(it => { it.props.y = v; })} />
      )}

      <div className="row gap" style={{ marginTop: 14 }}>
        <button className="btn" onClick={() => useStore.getState().splitSelected()}>✂ Böl (S)</button>
        <button className="btn danger" onClick={() => useStore.getState().deleteSelected()}>🗑 Sil</button>
      </div>
    </div>
  );
}
