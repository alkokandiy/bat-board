import React, { useState, useEffect, useRef } from 'react';
import { Bot, Minus, X, Plus, MessageSquare, Settings } from 'lucide-react';
import { api } from '../utils/api.js';

const PROVIDERS = ['gemini', 'anthropic', 'openai', 'deepseek', 'kimi'];
const MODEL_HINTS = {
  gemini: 'gemini-3.1-flash-lite',
  anthropic: 'claude-sonnet-5',
  openai: 'gpt-5.6',
  deepseek: 'deepseek-chat',
  kimi: 'kimi-k3',
};

/**
 * Floating Alfred companion: present on every tab, bottom-right.
 * Multi-session chat: session list sidebar, new chat, load messages.
 * Conversation state persists across tab switches while mounted.
 */
export default function AlfredWidget() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [providerStatus, setProviderStatus] = useState(null);
  const [provProvider, setProvProvider] = useState('gemini');
  const [provModel, setProvModel] = useState('');
  const [provKey, setProvKey] = useState('');
  const [provTest, setProvTest] = useState(null); // {ok, message, fingerprint}
  const [provBusy, setProvBusy] = useState(false);
  const bottomRef = useRef(null);
  const loadedRef = useRef(false);

  // Load sessions on mount
  useEffect(() => {
    if (!open || loadedRef.current) return;
    loadedRef.current = true;
    (async () => {
      try {
        const s = await api.getAlfredSessions();
        setSessions(s);
        if (s.length > 0) {
          await selectSession(s[0].id);
        } else {
          const created = await api.createAlfredSession('New conversation');
          setSessions([{ id: created.id, title: created.title, updated_at: new Date().toISOString() }]);
          setActiveSessionId(created.id);
          setMessages([{ role: 'alfred', text: 'Good evening, Master Al-Kokandiy. The books are open — what shall we log?' }]);
        }
      } catch {
        setMessages([{ role: 'alfred', text: 'Good evening, Master Al-Kokandiy. The books are open — what shall we log?' }]);
      }
    })();
  }, [open]);

  useEffect(() => {
    if (open && !minimized) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending, open, minimized]);

  const selectSession = async (id) => {
    setActiveSessionId(id);
    setShowSidebar(false);
    try {
      const msgs = await api.getAlfredSessionMessages(id);
      setMessages(msgs.map(m => ({ role: m.role === 'assistant' ? 'alfred' : 'user', text: m.content })));
    } catch {
      setMessages([]);
    }
  };

  const newChat = async () => {
    try {
      const created = await api.createAlfredSession('New conversation');
      setSessions(prev => [{ id: created.id, title: created.title, updated_at: new Date().toISOString() }, ...prev]);
      await selectSession(created.id);
    } catch {}
  };

  const loadProviderStatus = async () => {
    try {
      setProviderStatus(await api.getAlfredProvider());
    } catch {
      setProviderStatus(null);
    }
  };

  const openSettings = async () => {
    setShowSettings(v => !v);
    setProvTest(null);
    await loadProviderStatus();
  };

  const provFingerprint = `${provProvider}|${provModel.trim()}|${provKey.trim()}`;
  const testPassedCurrent = provTest?.ok && provTest?.fingerprint === provFingerprint;

  const testProvider = async () => {
    if (!provModel.trim() || !provKey.trim() || provBusy) return;
    setProvBusy(true);
    setProvTest(null);
    try {
      const res = await api.testAlfredProvider(provProvider, provModel.trim(), provKey.trim());
      setProvTest({ ...res, fingerprint: provFingerprint });
    } catch (err) {
      setProvTest({ ok: false, message: err.message, fingerprint: provFingerprint });
    } finally {
      setProvBusy(false);
    }
  };

  const saveProvider = async () => {
    if (!testPassedCurrent || provBusy) return;
    setProvBusy(true);
    try {
      const res = await api.saveAlfredProvider(provProvider, provModel.trim(), provKey.trim());
      setProviderStatus(res);
      setProvKey('');
      setProvTest(null);
    } catch (err) {
      setProvTest({ ok: false, message: err.message, fingerprint: provFingerprint });
    } finally {
      setProvBusy(false);
    }
  };

  const removeProvider = async () => {
    if (provBusy) return;
    setProvBusy(true);
    try {
      setProviderStatus(await api.deleteAlfredProvider());
    } catch {} finally {
      setProvBusy(false);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending || !activeSessionId) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text }]);
    setSending(true);
    try {
      const res = await api.sendAlfredMessage(text, activeSessionId);
      setMessages(prev => [...prev, { role: 'alfred', text: res.reply }]);
      // Refresh session list (title may have been auto-set)
      const s = await api.getAlfredSessions();
      setSessions(s);
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

  const activeSession = sessions.find(s => s.id === activeSessionId);

  return (
    <div className="fixed bottom-6 right-6 z-50 w-[22rem] max-w-[calc(100vw-3rem)] h-[28rem] max-h-[calc(100vh-6rem)] bg-dark-slate border border-slate-800 rounded-xl shadow-2xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-matte-obsidian">
        <div className="flex items-center gap-2 text-electric-bat-yellow">
          <Bot size={16} />
          <span className="text-xs font-mono tracking-widest">ALFRED</span>
          {activeSession && (
            <span className="text-[10px] text-slate-500 font-body truncate max-w-[120px]">
              {activeSession.title}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowSidebar(!showSidebar)} title="Conversations" className="p-1.5 text-slate-500 hover:text-electric-bat-yellow transition">
            <MessageSquare size={14} />
          </button>
          <button onClick={openSettings} title="Model settings" className="p-1.5 text-slate-500 hover:text-electric-bat-yellow transition">
            <Settings size={14} />
          </button>
          <button onClick={() => setMinimized(true)} title="Minimize" className="p-1.5 text-slate-500 hover:text-slate-200 transition">
            <Minus size={14} />
          </button>
          <button onClick={() => setOpen(false)} title="Dismiss" className="p-1.5 text-slate-500 hover:text-red-400 transition">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Session sidebar */}
      {showSidebar && (
        <div className="shrink-0 border-b border-slate-800 bg-matte-obsidian max-h-[10rem] overflow-y-auto">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-[10px] font-mono text-slate-500 tracking-widest">CONVERSATIONS</span>
            <button onClick={newChat} className="p-1 text-electric-bat-yellow hover:brightness-110 transition" title="New chat">
              <Plus size={12} />
            </button>
          </div>
          {sessions.map(s => (
            <button
              key={s.id}
              onClick={() => selectSession(s.id)}
              className={`w-full text-left px-3 py-1.5 text-[12px] font-body transition ${
                s.id === activeSessionId
                  ? 'bg-electric-bat-yellow/10 text-electric-bat-yellow'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
              }`}
            >
              <div className="truncate">{s.title || 'Untitled'}</div>
              <div className="text-[10px] text-slate-600">{new Date(s.updated_at).toLocaleDateString()}</div>
            </button>
          ))}
        </div>
      )}

      {/* Provider settings */}
      {showSettings && (
        <div className="shrink-0 border-b border-slate-800 bg-matte-obsidian px-3 py-2.5 space-y-2 max-h-[16rem] overflow-y-auto">
          <span className="text-[10px] font-mono text-slate-500 tracking-widest">MODEL SETTINGS</span>
          {providerStatus?.configured ? (
            <div className="space-y-2">
              <div className="text-[12px] font-body text-slate-300">
                {providerStatus.provider} · <span className="text-slate-500">{providerStatus.model_name}</span>
              </div>
              <div className="text-[11px] font-body text-slate-600">Key stored — never shown again.</div>
              <button
                onClick={removeProvider}
                disabled={provBusy}
                className="px-3 py-1.5 border border-red-400/40 text-red-400 rounded-lg text-[11px] font-mono tracking-widest hover:bg-red-400/10 transition disabled:opacity-50"
              >
                REMOVE
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <select
                value={provProvider}
                onChange={e => { setProvProvider(e.target.value); setProvTest(null); }}
                className="w-full bg-dark-slate border border-slate-800 rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-electric-bat-yellow font-body"
              >
                {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <input
                type="text"
                value={provModel}
                onChange={e => setProvModel(e.target.value)}
                placeholder={MODEL_HINTS[provProvider]}
                className="w-full bg-dark-slate border border-slate-800 rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow font-body"
              />
              <input
                type="password"
                value={provKey}
                onChange={e => setProvKey(e.target.value)}
                placeholder="API key"
                autoComplete="off"
                className="w-full bg-dark-slate border border-slate-800 rounded-lg px-2.5 py-1.5 text-[12px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow font-body"
              />
              {provTest && (
                <div className={`text-[11px] font-body ${provTest.ok ? 'text-green-400' : 'text-red-400'}`}>
                  {provTest.ok ? '✓ ' : '✗ '}{provTest.message}
                </div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={testProvider}
                  disabled={provBusy || !provModel.trim() || !provKey.trim()}
                  className="px-3 py-1.5 border border-slate-700 text-slate-300 rounded-lg text-[11px] font-mono tracking-widest hover:border-electric-bat-yellow transition disabled:opacity-50"
                >
                  TEST
                </button>
                <button
                  onClick={saveProvider}
                  disabled={!testPassedCurrent || provBusy}
                  title={testPassedCurrent ? 'Save tested key' : 'Test the key first'}
                  className="px-3 py-1.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded-lg text-[11px] font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
                >
                  SAVE
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
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

      {/* Input */}
      <div className="shrink-0 flex gap-2 p-3 border-t border-slate-800">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') send(); }}
          placeholder="Ask Alfred..."
          maxLength={2000}
          disabled={sending || !activeSessionId}
          className="flex-1 bg-matte-obsidian border border-slate-800 rounded-lg px-3 py-2 text-[13px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow transition font-body disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={sending || !input.trim() || !activeSessionId}
          className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded-lg text-[11px] font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
        >
          SEND
        </button>
      </div>
    </div>
  );
}
