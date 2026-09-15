import React, { useState, useEffect, useRef } from 'react';
import { Bot, Minus, X } from 'lucide-react';
import { api } from '../utils/api.js';

/**
 * Floating Alfred companion: present on every tab, bottom-right.
 * Open via the launcher, minimize to a pill, quit to close.
 * Conversation state persists across tab switches while mounted.
 */
export default function AlfredWidget() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState([
    { role: 'alfred', text: 'Good evening, Master Al-Kokandiy. The books are open — what shall we log?' },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open && !minimized) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending, open, minimized]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setSending(true);
    try {
      const res = await api.sendAlfredMessage(text);
      setMessages(prev => [...prev, { role: 'alfred', text: res.reply }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'alfred', text: `The line went dead: ${err.message}` }]);
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => { setOpen(true); setMinimized(false); }}
        title="Summon Alfred"
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-electric-bat-yellow text-matte-obsidian flex items-center justify-center shadow-lg hover:brightness-110 transition"
      >
        <Bot size={26} />
      </button>
    );
  }

  if (minimized) {
    return (
      <button
        onClick={() => setMinimized(false)}
        className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-full bg-dark-slate border border-electric-bat-yellow/40 text-electric-bat-yellow text-xs font-mono tracking-widest hover:border-electric-bat-yellow transition flex items-center gap-2"
      >
        <Bot size={16} /> ALFRED
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-[22rem] max-w-[calc(100vw-3rem)] h-[28rem] max-h-[calc(100vh-6rem)] bg-dark-slate border border-slate-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
      <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-matte-obsidian">
        <div className="flex items-center gap-2 text-electric-bat-yellow">
          <Bot size={16} />
          <span className="text-xs font-mono tracking-widest">ALFRED</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setMinimized(true)} title="Minimize" className="p-1.5 text-slate-500 hover:text-slate-200 transition">
            <Minus size={14} />
          </button>
          <button onClick={() => setOpen(false)} title="Dismiss" className="p-1.5 text-slate-500 hover:text-red-400 transition">
            <X size={14} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] px-3 py-2 rounded-lg text-[13px] font-body leading-relaxed whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-electric-bat-yellow/10 border border-electric-bat-yellow/30 text-slate-100'
                  : 'bg-matte-obsidian border border-slate-800 text-slate-300'
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="px-3 py-2 rounded-lg bg-matte-obsidian border border-slate-800 text-[11px] text-slate-500 font-mono animate-pulse">
              Alfred is thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 flex gap-2 p-3 border-t border-slate-800">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') send(); }}
          placeholder="Ask Alfred..."
          maxLength={2000}
          disabled={sending}
          className="flex-1 bg-matte-obsidian border border-slate-800 rounded-lg px-3 py-2 text-[13px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow transition font-body disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={sending || !input.trim()}
          className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded-lg text-[11px] font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
        >
          SEND
        </button>
      </div>
    </div>
  );
}
