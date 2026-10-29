import { useEffect, useMemo, useRef, useState } from 'react';
import { Player, type PlayerRef } from '@remotion/player';
import { Main } from '../remotion/Main';
import { fmtTime, useStore } from '../store';
import { projectDuration } from '../types';

// Oynat/durdur dogrudan oynaticiya gider (tarayici autoplay izni icin kullanici hareketinin icinde cagrilmali);
// store.playing sadece oynaticinin olaylarini yansitir.
const playerRef: { current: PlayerRef | null } = { current: null };

export function togglePlayback(e?: { nativeEvent?: Event } | Event) {
  const p = playerRef.current;
  if (!p) return;
  if (p.isPlaying()) p.pause();
  else p.play(e as never);
}

export function Preview() {
  const project = useStore(s => s.project)!;
  const ref = useRef<PlayerRef>(null);
  // oynarken yapilan seek'te Remotion bir 'pause' yayar ve ardindan kendisi devam eder; o pause durdurma sayilmamali
  const seekWhilePlaying = useRef(false);
  const dur = projectDuration(project);
  const frames = Math.max(1, Math.round(dur * project.fps));
  const inputProps = useMemo(() => ({ project, mediaBase: '' }), [project]);
  // dongu acikken son kareden basa atlar: loop kliplerinde dikis (son -> bas) dogrudan duyulur
  const [loop, setLoop] = useState(true);

  // oynatici -> store
  useEffect(() => {
    const p = ref.current;
    if (!p) return;
    playerRef.current = p;
    const onFrame = (e: { detail: { frame: number } }) => useStore.getState().setTime(e.detail.frame / project.fps);
    const onPause = () => { if (!seekWhilePlaying.current) useStore.getState().setPlaying(false); };
    const onPlay = () => { seekWhilePlaying.current = false; useStore.getState().setPlaying(true); };
    p.addEventListener('frameupdate', onFrame);
    p.addEventListener('pause', onPause);
    p.addEventListener('play', onPlay);
    return () => {
      p.removeEventListener('frameupdate', onFrame);
      p.removeEventListener('pause', onPause);
      p.removeEventListener('play', onPlay);
      if (playerRef.current === p) playerRef.current = null;
    };
  }, [project.fps]);

  // store -> oynatici: sadece oynaticinin bulundugu kareden farkliysa (timeline'a tiklama, ok tuslari).
  // Oynatmanin kendi kare guncellemeleri burada fark 0 oldugu icin seek tetiklemez.
  useEffect(() => useStore.subscribe((s, prev) => {
    const p = ref.current;
    if (!p || s.time === prev.time) return;
    const target = Math.round(s.time * project.fps);
    if (Math.abs(p.getCurrentFrame() - target) < 1) return;
    seekWhilePlaying.current = p.isPlaying();
    p.seekTo(target);
  }), [project.fps]);

  return (
    <div className="preview">
      <div className="stage">
        <Player
          ref={ref}
          component={Main}
          inputProps={inputProps}
          durationInFrames={frames}
          fps={project.fps}
          compositionWidth={project.width}
          compositionHeight={project.height}
          style={{ height: '100%', maxWidth: '100%', aspectRatio: `${project.width}/${project.height}`, borderRadius: 12, overflow: 'hidden', boxShadow: '0 10px 40px rgba(0,0,0,.6)' }}
          acknowledgeRemotionLicense
          clickToPlay
          doubleClickToFullscreen
          numberOfSharedAudioTags={12}
          loop={loop}
        />
      </div>
      <Transport dur={dur} fps={project.fps} loop={loop} setLoop={setLoop} />
    </div>
  );
}

// zaman sayaci ayri bilesen: oynarken sadece bu yeniden cizilir
function Transport({ dur, fps, loop, setLoop }: { dur: number; fps: number; loop: boolean; setLoop: (b: boolean) => void }) {
  const playing = useStore(s => s.playing);
  const time = useStore(s => s.time);
  const st = useStore.getState;
  return (
    <div className="transport">
      <button className="btn ghost" onClick={() => st().setTime(0)} title="Başa dön">⏮</button>
      <button className="btn ghost" onClick={() => st().setTime(st().time - 1 / fps)} title="Önceki kare (←)">◀</button>
      <button className="btn play" onClick={e => togglePlayback(e)} title="Oynat/Durdur (Boşluk)">{playing ? '❚❚' : '▶'}</button>
      <button className="btn ghost" onClick={() => st().setTime(st().time + 1 / fps)} title="Sonraki kare (→)">▶</button>
      <button className={`btn ghost ${loop ? 'on' : ''}`} onClick={() => setLoop(!loop)}
        title="Döngü: sona gelince başa sar">🔁</button>
      <button className="btn ghost" title="Dikişi dinle: son 3 sn + baştan devam (döngü açık olmalı)"
        onClick={e => { setLoop(true); st().setTime(Math.max(0, dur - 3)); if (!playerRef.current?.isPlaying()) togglePlayback(e); }}>
        ⤺ Dikiş</button>
      <span className="tc">{fmtTime(time)} <span className="muted">/ {fmtTime(dur)}</span></span>
    </div>
  );
}
