import { create } from 'zustand';
import { nanoid } from 'nanoid';
import { api } from './api';
import type { Item, Job, Media, Project, Track, TrackKind } from './types';
import { itemDur, itemEnd } from './types';

const HISTORY = 80;

interface State {
  project: Project | null;
  past: Project[];
  future: Project[];
  selected: string | null;      // item id
  time: number;                 // oynatma kafasi (sn)
  playing: boolean;
  zoom: number;                 // px / sn
  jobs: Record<string, Job>;
  saving: boolean;
  load: (p: Project) => void;
  external: (p: Project) => void;
  commit: (fn: (p: Project) => void) => void;
  undo: () => void;
  redo: () => void;
  select: (id: string | null) => void;
  setTime: (t: number) => void;
  setPlaying: (b: boolean) => void;
  setZoom: (z: number) => void;
  upsertJob: (j: Job) => void;
  addMedia: (m: Media, at?: number, kind?: TrackKind) => void;
  splitSelected: () => void;
  deleteSelected: () => void;
  findItem: (id: string | null) => { track: Track; item: Item } | null;
  chat: ChatState;
  setChat: (fn: (c: ChatState) => Partial<ChatState>) => void;
  claudeEvent: (m: { kind: string; text: string; session?: string; input?: unknown }) => void;
}

export interface ChatMsg { role: 'user' | 'claude' | 'tool' | 'error'; text: string }
export interface ChatState { open: boolean; msgs: ChatMsg[]; session: string | null; busy: boolean }

let saveTimer: number | undefined;
const scheduleSave = () => {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    const p = useStore.getState().project;
    if (!p) return;
    useStore.setState({ saving: true });
    try {
      const r = await api.saveProject(p);
      // sunucu surumu arttirir; yerel kopyayi esitle (dis degisiklik algilamasi icin)
      useStore.setState(s => ({ saving: false, project: s.project ? { ...s.project, version: r.version } : s.project }));
    } catch {
      useStore.setState({ saving: false });
    }
  }, 500);
};

export const trackFor = (p: Project, kind: TrackKind) => p.tracks.find(t => t.kind === kind)!;

export const defaultKind = (m: Media): TrackKind =>
  m.kind === 'audio' ? (m.url.startsWith('/library/sfx') ? 'sfx' : m.url.startsWith('/library/music') ? 'music' : 'voice')
    : m.kind === 'image' ? 'overlay' : 'video';

export const useStore = create<State>((set, get) => ({
  project: null, past: [], future: [], selected: null, time: 0, playing: false, zoom: 70, jobs: {}, saving: false,
  chat: { open: false, msgs: [], session: null, busy: false },
  setChat: fn => set(s => ({ chat: { ...s.chat, ...fn(s.chat) } })),
  claudeEvent: m => set(s => {
    const c = s.chat;
    const session = m.session ?? c.session;
    if (m.kind === 'text') return { chat: { ...c, session, msgs: [...c.msgs, { role: 'claude', text: m.text }] } };
    if (m.kind === 'tool') return { chat: { ...c, session, msgs: [...c.msgs, { role: 'tool', text: m.text }] } };
    if (m.kind === 'error') {
      // CLI hatayi once asistan mesaji olarak da basiyor: ayni metni ikinci kez gosterme
      const last = c.msgs[c.msgs.length - 1];
      const msgs = last?.role === 'claude' && m.text.startsWith(last.text) ? c.msgs.slice(0, -1) : c.msgs;
      return { chat: { ...c, session, busy: false, msgs: [...msgs, { role: 'error', text: m.text }] } };
    }
    if (m.kind === 'done') return { chat: { ...c, session, busy: false } };
    return {};
  }),

  load: p => set({ project: p, past: [], future: [], selected: null, time: 0 }),

  external: p => {
    // Claude/MCP ya da baska sekme diskteki projeyi degistirdi: gecmise ekleyip yeni hali goster
    const cur = get().project;
    if (cur && p.version <= cur.version) return;
    set(s => ({ project: p, past: s.project ? [...s.past, s.project].slice(-HISTORY) : s.past, future: [] }));
  },

  commit: fn => {
    const cur = get().project;
    if (!cur) return;
    const next = structuredClone(cur);
    fn(next);
    set(s => ({ project: next, past: [...s.past, cur].slice(-HISTORY), future: [] }));
    scheduleSave();
  },

  undo: () => {
    const { past, project } = get();
    if (!past.length || !project) return;
    const prev = past[past.length - 1];
    set(s => ({ project: { ...prev, version: project.version }, past: s.past.slice(0, -1), future: [project, ...s.future] }));
    scheduleSave();
  },

  redo: () => {
    const { future, project } = get();
    if (!future.length || !project) return;
    const next = future[0];
    set(s => ({ project: { ...next, version: project.version }, future: s.future.slice(1), past: [...s.past, project] }));
    scheduleSave();
  },

  select: id => set({ selected: id }),
  setTime: t => set({ time: Math.max(0, t) }),
  setPlaying: b => set({ playing: b }),
  setZoom: z => set({ zoom: Math.min(400, Math.max(10, z)) }),
  upsertJob: jb => set(s => ({ jobs: { ...s.jobs, [jb.id]: jb } })),

  addMedia: (m, at, kind) => {
    const k = kind ?? defaultKind(m);
    const id = nanoid(8);
    get().commit(p => {
      const tr = trackFor(p, k);
      // konum verilmediyse (+ butonu): kanalin sonuna ekle (CapCut gibi); muzik/efekt oynatma kafasina
      const trackEnd = Math.max(0, ...tr.items.map(itemEnd));
      const start = at ?? (k === 'video' || k === 'voice' ? trackEnd : Math.max(get().time, 0));
      const dur = m.kind === 'image' ? 3 : m.duration || 3;
      tr.items.push({
        id, type: m.kind === 'image' ? 'image' : m.kind === 'audio' ? 'audio' : 'video',
        src: m.url, start, in: 0, out: dur, speed: 1,
        volume: k === 'music' ? 0.3 : 1, fadeIn: 0, fadeOut: 0, transition: null,
        props: m.kind === 'image' ? { x: 0.5, y: 0.5, scale: 1, fit: 'contain' } : k === 'music' ? { duck: true, duckLevel: 0.3 } : { fit: 'cover' },
      });
      tr.items.sort((a, b) => a.start - b.start);
    });
    set({ selected: id });
  },

  splitSelected: () => {
    const { selected, time } = get();
    const f = get().findItem(selected);
    if (!f) return;
    const { item } = f;
    if (time <= item.start + 0.05 || time >= itemEnd(item) - 0.05) return;
    get().commit(p => {
      for (const t of p.tracks) {
        const i = t.items.findIndex(x => x.id === item.id);
        if (i < 0) continue;
        const a = t.items[i];
        const cut = a.in + (time - a.start) * a.speed;
        const b: Item = { ...structuredClone(a), id: nanoid(8), start: time, in: cut, fadeIn: 0, transition: null };
        a.out = cut;
        a.fadeOut = 0;
        if (a.type === 'caption' && a.props.words) {
          const rel = time - a.start;
          b.props.words = a.props.words.filter(w => w.s >= rel).map(w => ({ ...w, s: w.s - rel, e: w.e - rel }));
          a.props.words = a.props.words.filter(w => w.s < rel);
        }
        t.items.splice(i + 1, 0, b);
      }
    });
  },

  deleteSelected: () => {
    const { selected } = get();
    if (!selected) return;
    get().commit(p => p.tracks.forEach(t => (t.items = t.items.filter(i => i.id !== selected))));
    set({ selected: null });
  },

  findItem: id => {
    const p = get().project;
    if (!p || !id) return null;
    for (const track of p.tracks) {
      const item = track.items.find(i => i.id === id);
      if (item) return { track, item };
    }
    return null;
  },
}));

export const fmtTime = (t: number) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};

export { itemDur, itemEnd };
