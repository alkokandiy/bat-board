import React, { useState, useEffect, useRef } from 'react';
import { api } from '../utils/api.js';

export default function AlfredChatPanel() {
  const [messages, setMessages] = useState([
    { role: 'alfred', text: 'Good evening, Master Al-Kokandiy. The books are open — ask after your missions, habits, or notes, or tell me what to log.' },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

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

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1 shrink-0">
        <h1 className="text-2xl font-bold tracking-wider">ALFRED</h1>
        <p className="text-xs text-slate-400">Your butler, in the cave. Same memory as Telegram — confirm deletions with YES.</p>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto bg-dark-slate rounded border border-slate-800 p-4 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] px-4 py-2.5 rounded text-sm font-body leading-relaxed whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-electric-bat-yellow/10 border border-electric-bat-yellow/30 text-slate-100'
                  : 'bg-matte-obsidian border border-slate-800 text-slate-300'
              }`}
            >
              {m.role === 'alfred' && (
                <div className="text-[10px] font-mono uppercase tracking-widest text-electric-bat-yellow mb-1">Alfred</div>
              )}
              {m.text}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="px-4 py-2.5 rounded bg-matte-obsidian border border-slate-800 text-xs text-slate-500 font-mono animate-pulse">
              Alfred is thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="shrink-0 flex gap-3">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') send(); }}
          placeholder="Ask Alfred something..."
          maxLength={2000}
          disabled={sending}
          className="flex-1 bg-dark-slate border border-slate-800 rounded px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow transition font-body disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={sending || !input.trim()}
          className="px-6 py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded text-xs font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
        >
          SEND
        </button>
      </div>
    </div>
  );
}
