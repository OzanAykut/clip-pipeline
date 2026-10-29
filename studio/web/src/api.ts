import type { Job, Media, Project } from './types';

// bu sekmenin kimligi: kendi kaydimizin WebSocket yankisini yok saymak icin
export const CLIENT_ID = 'ui-' + Math.random().toString(36).slice(2, 8);

const j = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

export const api = {
  listProjects: () => fetch('/api/projects').then(j) as Promise<{ id: string; name: string; updated: number; media: number }[]>,
  newProject: (name: string) =>
    fetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) }).then(j) as Promise<Project>,
  getProject: (id: string) => fetch(`/api/projects/${id}`).then(j) as Promise<Project>,
  saveProject: (p: Project) =>
    fetch(`/api/projects/${p.id}?client=${CLIENT_ID}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) }).then(j) as Promise<{ version: number }>,
  upload: (id: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return fetch(`/api/projects/${id}/media`, { method: 'POST', body: fd }).then(j) as Promise<Media>;
  },
  library: () => fetch('/api/library').then(j) as Promise<{ music: Media[]; sfx: Media[] }>,
  audiomap: (id: string, name: string) => fetch(`/api/projects/${id}/media/${encodeURIComponent(name)}/audiomap`).then(j) as Promise<AudioMap>,
  waveform: (id: string, name: string) => fetch(`/api/projects/${id}/media/${encodeURIComponent(name)}/waveform`).then(j) as Promise<number[]>,
  exportProject: (id: string) => fetch(`/api/projects/${id}/export`, { method: 'POST' }).then(j) as Promise<Job>,
  tool: (id: string, tool: string, args: Record<string, unknown> = {}) =>
    fetch(`/api/projects/${id}/tools`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tool, args }) }).then(j) as Promise<Job>,
  jobs: (id: string) => fetch(`/api/jobs?pid=${id}`).then(j) as Promise<Job[]>,
};

export function connect(id: string, onMsg: (m: any) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let ping: number | undefined;
  const open = () => {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/${id}`);
    ws.onmessage = e => onMsg(JSON.parse(e.data));
    ws.onopen = () => { ping = window.setInterval(() => ws?.readyState === 1 && ws.send('ping'), 20000); };
    ws.onclose = () => { window.clearInterval(ping); if (!closed) setTimeout(open, 1500); };
  };
  open();
  return () => { closed = true; ws?.close(); };
}

// ince dalga formu (log olcek 0-1, saniyede pps nokta) + sessiz araliklar [bas, son] (medya saniyesi)
export interface AudioMap { pps: number; peaks: number[]; silences: [number, number][] }
