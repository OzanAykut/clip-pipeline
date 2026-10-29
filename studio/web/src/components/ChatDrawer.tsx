import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store';

const TOOL_NAMES: Record<string, string> = {
  get_project: 'projeyi okudu', add_item: 'öğe ekledi', update_item: 'öğeyi düzenledi', split_item: 'böldü',
  delete_item: 'sildi', set_caption_style: 'altyazı stilini değiştirdi', run_tool: 'AI aracı çalıştırdı',
  export_project: 'dışa aktardı', add_media: 'medya ekledi', list_projects: 'projelere baktı', get_jobs: 'işlere baktı',
  create_project: 'proje oluşturdu',
};

const SUGGEST = [
  'Altyazı oluştur ve TikTok stilini uygula',
  'Müziği konuşmada kıs ve -12 dB yap',
  'Tüm kliplere sola kayma geçişi ekle',
  'Videonun başına beyaz manşet kartı koy',
];

export function ChatDrawer() {
  const chat = useStore(s => s.chat);
  const pid = useStore(s => s.project!.id);
  const [text, setText] = useState('');
  const [status, setStatus] = useState<{ loggedIn: boolean; cli: string | null } | null>(null);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => { if (chat.open && !status) fetch('/api/claude/status').then(r => r.json()).then(setStatus).catch(() => {}); }, [chat.open]);
  useEffect(() => { list.current?.scrollTo(0, list.current.scrollHeight); }, [chat.msgs.length]);
  if (!chat.open) return null;

  const send = async (msg: string) => {
    if (!msg.trim() || chat.busy) return;
    const s = useStore.getState();
    s.setChat(c => ({ busy: true, msgs: [...c.msgs, { role: 'user', text: msg }] }));
    setText('');
    await fetch(`/api/projects/${pid}/claude`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, session: chat.session, context: { time: s.time, selected: s.selected } }),
    });
  };

  return (
    <div className="chat">
      <div className="chat-head">
        <b>✦ Claude</b><span className="muted small">aboneliğinle · API yok</span>
        <div className="grow" />
        <button className="btn ghost sm" title="Yeni sohbet" onClick={() => useStore.getState().setChat(() => ({ msgs: [], session: null }))}>⟲</button>
        <button className="btn ghost sm" onClick={() => useStore.getState().setChat(() => ({ open: false }))}>✕</button>
      </div>
      {status && !status.loggedIn && (
        <div className="chat-warn">
          Claude Code girişi yok. Terminalde bir kez çalıştır:<br />
          <code>"{status.cli ?? '%APPDATA%\\Claude\\claude-code\\…\\claude.exe'}" login</code>
        </div>
      )}
      <div className="chat-list" ref={list}>
        {chat.msgs.length === 0 && (
          <div className="stack">
            <div className="muted small">Projeni Claude'a düzenlet. Değişiklikler anında timeline'da görünür, Ctrl+Z ile geri alınır.</div>
            {SUGGEST.map(s => <button key={s} className="preset" onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
        {chat.msgs.map((m, i) => (
          m.role === 'tool'
            ? <div key={i} className="cmsg tool">⚙ {TOOL_NAMES[m.text] ?? m.text}</div>
            : <div key={i} className={`cmsg ${m.role}`}>{m.text}</div>
        ))}
        {chat.busy && <div className="cmsg tool"><span className="spinner" /> düşünüyor…</div>}
      </div>
      <form className="chat-input" onSubmit={e => { e.preventDefault(); send(text); }}>
        <textarea className="input" rows={2} placeholder="Ne yapayım? (örn. sessizlikleri kes, B-roll ekle)" value={text}
          onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text); } }} />
        {chat.busy
          ? <button type="button" className="btn" onClick={() => fetch(`/api/projects/${pid}/claude/stop`, { method: 'POST' }).then(() => useStore.getState().setChat(() => ({ busy: false })))}>■</button>
          : <button className="btn primary">➤</button>}
      </form>
    </div>
  );
}
