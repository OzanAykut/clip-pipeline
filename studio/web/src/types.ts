// project.json semasi (backend/store.py ile ayni). Tum zamanlar saniye.
export type TrackKind = 'video' | 'overlay' | 'caption' | 'voice' | 'music' | 'sfx';
export type ItemType = 'video' | 'audio' | 'image' | 'text' | 'caption';

export interface Word { w: string; s: number; e: number } // item basina gore

export interface Item {
  id: string;
  type: ItemType;
  src?: string;          // medya url'si (/media/... ya da /library/...)
  start: number;         // timeline'daki baslangic
  in: number;            // kaynakta baslangic
  out: number;           // kaynakta bitis
  speed: number;
  volume: number;        // dogrusal kazanc, 1 = 0 dB
  fadeIn: number;
  fadeOut: number;
  transition?: { type: string; dur: number } | null;
  props: {
    text?: string;
    words?: Word[];
    style?: string;
    x?: number; y?: number; scale?: number;   // 0-1 konum, olcek
    fit?: 'cover' | 'contain';
    color?: string; size?: number;
    [k: string]: unknown;
  };
}

export interface Track {
  id: string;
  kind: TrackKind;
  name: string;
  muted: boolean;
  hidden: boolean;
  items: Item[];
}

export interface Media {
  name: string;
  kind: 'video' | 'audio' | 'image';
  duration: number;
  width?: number | null;
  height?: number | null;
  has_audio: boolean;
  url: string;
}

export interface Project {
  id: string;
  name: string;
  version: number;
  fps: number;
  width: number;
  height: number;
  media: Media[];
  tracks: Track[];
  captionStyle: string;
}

export interface Job {
  id: string; pid: string; kind: string; status: 'queued' | 'running' | 'done' | 'error';
  progress: number; message: string; result: any;
}

export const itemDur = (it: Item) => (it.out - it.in) / (it.speed || 1);
export const itemEnd = (it: Item) => it.start + itemDur(it);
export const projectDuration = (p: Project) =>
  Math.max(1, ...p.tracks.flatMap(t => t.items.map(itemEnd)));
export const toDb = (g: number) => (g <= 0 ? -60 : 20 * Math.log10(g));
export const fromDb = (db: number) => (db <= -60 ? 0 : Math.pow(10, db / 20));
