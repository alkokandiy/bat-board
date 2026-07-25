import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';

const STORAGE_KEY = 'bat_notes';

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 9);
}

function freshNote() {
  const now = new Date().toISOString();
  return { id: uid(), title: '', body: '', category: '', pinned: false, createdAt: now, updatedAt: now };
}

function load(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; }
}

function save(key, data) {
  localStorage.setItem(key, JSON.stringify(data));
}

export default function NotesPanel() {
  const [notes, setNotes] = useState(() => load(STORAGE_KEY));
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('edited');
  const [saving, setSaving] = useState(false);

  const notesRef = useRef(notes);
  useEffect(() => { notesRef.current = notes; }, [notes]);

  const dbRef = useRef(null);
  const sfRef = useRef(null);
  const titleRef = useRef(null);

  const selectedNote = useMemo(() => notes.find(n => n.id === selectedId) || null, [notes, selectedId]);

  const allTags = useMemo(() => {
    const s = new Set();
    notes.forEach(n => { if (n.category) s.add(n.category); });
    return [...s].sort();
  }, [notes]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let res = notes;
    if (q) res = res.filter(n => n.title.toLowerCase().includes(q) || n.body.toLowerCase().includes(q));
    return [...res].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      if (sortBy === 'title') return a.title.localeCompare(b.title);
      if (sortBy === 'created') return new Date(b.createdAt) - new Date(a.createdAt);
      return new Date(b.updatedAt) - new Date(a.updatedAt);
    });
  }, [notes, search, sortBy]);

  const counts = useMemo(() => {
    if (!selectedNote) return { chars: 0, words: 0 };
    const b = selectedNote.body || '';
    const chars = b.length;
    const words = b.trim() ? b.trim().split(/\s+/).length : 0;
    return { chars, words };
  }, [selectedNote]);

  const scheduleSave = useCallback((updated) => {
    if (dbRef.current) clearTimeout(dbRef.current);
    dbRef.current = setTimeout(() => {
      save(STORAGE_KEY, updated);
      setSaving(true);
      if (sfRef.current) clearTimeout(sfRef.current);
      sfRef.current = setTimeout(() => setSaving(false), 1500);
    }, 800);
  }, []);

  const updateField = useCallback((field, value) => {
    setNotes(prev => {
      const next = prev.map(n =>
        n.id === selectedId ? { ...n, [field]: value, updatedAt: new Date().toISOString() } : n
      );
      scheduleSave(next);
      return next;
    });
  }, [selectedId, scheduleSave]);

  const handleNew = useCallback(() => {
    const note = freshNote();
    setNotes(prev => { const next = [note, ...prev]; save(STORAGE_KEY, next); return next; });
    setSelectedId(note.id);
    setSearch('');
    requestAnimationFrame(() => titleRef.current?.focus());
  }, []);

  const handleDelete = useCallback((id) => {
    if (!confirm('Delete this note?')) return;
    setNotes(prev => { const next = prev.filter(n => n.id !== id); save(STORAGE_KEY, next); return next; });
    if (selectedId === id) setSelectedId(null);
  }, [selectedId]);

  const handleSelect = useCallback((id) => {
    if (dbRef.current) { clearTimeout(dbRef.current); dbRef.current = null; save(STORAGE_KEY, notesRef.current); }
    setSelectedId(id);
  }, []);

  const togglePin = useCallback(() => {
    if (!selectedId) return;
    updateField('pinned', !selectedNote?.pinned);
  }, [selectedId, selectedNote, updateField]);

  const hasNotes = notes.length > 0;
  const hasResults = filtered.length > 0;

  return (
    <div className="h-full flex flex-col bg-[#08080f]">
      <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-[#1e1e2e]">
        <h1 className="text-2xl tracking-wider text-slate-100 font-display">NOTES</h1>
        <button onClick={handleNew} className="px-5 py-2 bg-[#f5c518] text-[#08080f] font-bold rounded-lg hover:brightness-110 transition font-body text-sm tracking-wider">
          + New Note
        </button>
      </div>

      <div className="flex-1 min-h-0 flex gap-4 p-4">
        <aside className="w-80 shrink-0 flex flex-col bg-[#0d0d18] rounded-[10px] border border-[#1e1e2e] overflow-hidden">
          <div className="shrink-0 p-3 border-b border-[#1e1e2e] space-y-2">
            <input
              type="text" placeholder="Search notes..." value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-[#08080f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-[#f5c518] transition font-body"
            />
            <select
              value={sortBy} onChange={e => setSortBy(e.target.value)}
              className="w-full bg-[#08080f] border border-[#1e1e2e] rounded-lg px-3 py-1.5 text-xs text-slate-400 focus:outline-none focus:border-[#f5c518] transition font-body cursor-pointer"
            >
              <option value="edited">Last Edited</option>
              <option value="created">Created</option>
              <option value="title">Title</option>
            </select>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {!hasNotes ? (
              <div className="p-6 text-center text-sm text-slate-500 italic font-body leading-relaxed">
                &ldquo;The night is darkest just before the dawn.&rdquo;
              </div>
            ) : !hasResults ? (
              <div className="p-6 text-center text-sm text-slate-500 font-body">No notes match your search.</div>
            ) : filtered.map(note => (
              <div
                key={note.id} onClick={() => handleSelect(note.id)}
                className={`group relative rounded-lg px-3 py-2.5 cursor-pointer transition-all duration-150 border ${
                  selectedId === note.id
                    ? 'bg-[#1a1a2e] border-[#f5c518]/40'
                    : 'bg-transparent border-transparent hover:bg-[#1a1a2e]/50 hover:border-[#1e1e2e]'
                }`}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      {note.pinned && <span className="text-[#f5c518] text-[10px]">&#9733;</span>}
                      <span className={`text-sm truncate font-body ${selectedId === note.id ? 'text-[#f5c518]' : 'text-slate-200'}`}>
                        {note.title || 'Untitled'}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 truncate mt-0.5 font-body">
                      {note.body ? note.body.replace(/\n/g, ' ') : 'No content'}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {note.category && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#1e1e2e] text-slate-400 font-body">{note.category}</span>
                      )}
                      <span className="text-[9px] text-slate-600 font-body">
                        {new Date(note.updatedAt).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); handleDelete(note.id); }}
                    className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition text-xs px-1 py-1"
                  >&#x2715;</button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="flex-1 min-w-0 flex flex-col bg-[#0d0d18] rounded-[10px] border border-[#1e1e2e] overflow-hidden">
          {!selectedNote ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-3">
                <div className="text-4xl text-slate-700 font-display">&#x270E;</div>
                <p className="text-sm text-slate-500 italic font-body">Select a note or create a new one</p>
              </div>
            </div>
          ) : (
            <>
              <div className="shrink-0 p-5 pb-2">
                <input
                  ref={titleRef} type="text" placeholder="Note title..."
                  value={selectedNote.title}
                  onChange={e => updateField('title', e.target.value)}
                  className="w-full text-xl font-display text-slate-100 bg-transparent border-none outline-none placeholder-slate-600 tracking-wide"
                />
              </div>

              <div className="flex-1 px-5 pb-2">
                <textarea
                  placeholder="Start writing..."
                  value={selectedNote.body}
                  onChange={e => updateField('body', e.target.value)}
                  className="w-full h-full text-sm text-slate-300 bg-transparent border-none outline-none resize-none font-body leading-relaxed placeholder-slate-600"
                />
              </div>

              <div className="shrink-0 border-t border-[#1e1e2e] px-5 py-3 flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <input
                      type="text" placeholder="Tag..." value={selectedNote.category}
                      onChange={e => updateField('category', e.target.value)}
                      list="note-tags"
                      className="w-28 bg-[#08080f] border border-[#1e1e2e] rounded-lg px-2.5 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-[#f5c518] transition font-body"
                    />
                    <datalist id="note-tags">
                      {allTags.map(t => <option key={t} value={t} />)}
                    </datalist>
                  </div>
                  <button
                    onClick={togglePin}
                    className={`text-sm px-2 py-1 rounded-lg transition font-body ${
                      selectedNote.pinned ? 'text-[#f5c518] bg-[#f5c518]/10' : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {selectedNote.pinned ? '\u2605 Pinned' : '\u2606 Pin'}
                  </button>
                </div>

                <div className="flex items-center gap-4 text-[11px] text-slate-500 font-body">
                  <span>{counts.words} words</span>
                  <span>{counts.chars} chars</span>
                  <span className="text-slate-600">|</span>
                  <span className="text-[10px] text-slate-600">
                    {new Date(selectedNote.updatedAt).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                  {saving && (
                    <span className="text-[#f5c518] text-[10px] font-medium transition-opacity">Saved &#10003;</span>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
