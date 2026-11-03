import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Pin, Plus, Trash2 } from 'lucide-react';
import { api } from '../utils/api.js';
import { migrateOnce } from '../utils/migrateLocalStorage.js';
import { PageHeader, Button, EmptyState, IconButton, Segmented, fieldClass } from './ui';

const LEGACY_KEY = 'bat_notes';
const MIGRATED_FLAG = 'bat_notes_migrated';

function fromServer(n) {
  return {
    id: n.id,
    title: n.title || '',
    body: n.body || '',
    category: n.category || '',
    pinned: !!n.is_pinned,
    createdAt: n.created_at,
    updatedAt: n.updated_at,
  };
}

// Empty strings, not null: the API treats null as "leave unchanged", so
// clearing a note's body or category was never saved.
function toPayload(note) {
  return {
    title: note.title || '',
    body: note.body || '',
    category: note.category || '',
    is_pinned: !!note.pinned,
  };
}

export default function NotesPanel() {
  const [notes, setNotes] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('edited');
  // 'mine' = your own notes; 'alfred' = Alfred's private memory, kept separate
  const [scope, setScope] = useState('mine');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const notesRef = useRef(notes);
  useEffect(() => { notesRef.current = notes; }, [notes]);

  const pendingRef = useRef({}); // noteId -> timeout id for debounced PUT
  const sfRef = useRef(null);
  const migratedRef = useRef(false);   // legacy import runs once, not per scope
  const titleRef = useRef(null);

  const flushAll = useCallback(() => {
    const timers = pendingRef.current;
    Object.keys(timers).forEach((key) => {
      clearTimeout(timers[key]);
      const id = Number(key);
      const note = notesRef.current.find(n => n.id === id);
      if (note) api.updateNote(id, toPayload(note)).catch(() => {});
    });
    pendingRef.current = {};
  }, []);

  // One-time legacy migration, then load from the API.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!migratedRef.current) {
          migratedRef.current = true;
          await migrateOnce({
            legacyKey: LEGACY_KEY,
            flagKey: MIGRATED_FLAG,
            toPayload: (n) => ({
              title: n.title || '',
              body: n.body || null,
              category: n.category || null,
              is_pinned: !!n.pinned,
            }),
            upload: (payload) => api.createNote(payload),
          });
        }
      } catch {
        // Migration failed partway: flag not set, retries next load.
        // Fall through to loading whatever the server already has.
      }
      try {
        const data = await api.getNotes('', '', scope);
        if (!cancelled) setNotes((data || []).map(fromServer));
      } catch {
        // Offline/backend down: keep empty list rather than crashing.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [scope]);

  const flushPending = useCallback((id) => {
    const timers = pendingRef.current;
    if (id && timers[id]) {
      clearTimeout(timers[id]);
      delete timers[id];
      const note = notesRef.current.find(n => n.id === id);
      if (note) api.updateNote(id, toPayload(note)).catch(() => {});
    }
  }, []);

  // Flush every debounced save on unmount (e.g. switching tabs right after
  // typing); pending edits were silently discarded.
  useEffect(() => () => {
    flushAll();
    if (sfRef.current) clearTimeout(sfRef.current);
  }, [flushAll]);

  const selectedNote = useMemo(() => notes.find(n => n.id === selectedId) || null, [notes, selectedId]);

  const allTags = useMemo(() => {
    const s = new Set();
    notes.forEach(n => { if (n.category) s.add(n.category); });
    return [...s].sort();
  }, [notes]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let res = notes;
    if (q) res = res.filter(n => (n.title || '').toLowerCase().includes(q) || (n.body || '').toLowerCase().includes(q));
    return [...res].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      if (sortBy === 'title') return (a.title || '').localeCompare(b.title || '');
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

  const scheduleSave = useCallback((id, updated) => {
    const timers = pendingRef.current;
    if (timers[id]) clearTimeout(timers[id]);
    timers[id] = setTimeout(async () => {
      delete pendingRef.current[id];
      setSaving(true);
      try {
        const saved = await api.updateNote(id, toPayload(updated));
        // Take only server metadata: replacing the content with the response
        // dropped anything typed while the request was in flight.
        setNotes(prev => prev.map(n => (n.id === id ? { ...n, updatedAt: saved.updated_at } : n)));
      } catch {
        // Keep optimistic local state on failure; next edit retries.
      } finally {
        if (sfRef.current) clearTimeout(sfRef.current);
        sfRef.current = setTimeout(() => setSaving(false), 1500);
      }
    }, 800);
  }, []);

  const updateField = useCallback((field, value) => {
    setNotes(prev => {
      const next = prev.map(n =>
        n.id === selectedId ? { ...n, [field]: value, updatedAt: new Date().toISOString() } : n
      );
      const updated = next.find(n => n.id === selectedId);
      if (updated) scheduleSave(selectedId, updated);
      return next;
    });
  }, [selectedId, scheduleSave]);

  const handleNew = useCallback(async () => {
    try {
      const created = await api.createNote({ title: '', body: null, category: null, is_pinned: false });
      const note = fromServer(created);
      setNotes(prev => [note, ...prev]);
      setSelectedId(note.id);
      setSearch('');
      // A ref, not a placeholder lookup: the focus silently stopped working
      // the moment anybody reworded the placeholder.
      requestAnimationFrame(() => titleRef.current?.focus());
    } catch {
      // Backend unreachable: no silent local-only note.
    }
  }, []);

  const handleDelete = useCallback((id, title) => {
    if (!confirm(`Delete "${title || 'Untitled'}"?`)) return;
    if (pendingRef.current[id]) { clearTimeout(pendingRef.current[id]); delete pendingRef.current[id]; }
    setNotes(prev => prev.filter(n => n.id !== id));
    setSelectedId(prev => (prev === id ? null : prev));
    api.deleteNote(id).catch(() => {});
  }, []);

  const handleSelect = useCallback((id) => {
    flushPending(selectedId);
    setSelectedId(id);
  }, [flushPending, selectedId]);

  // Switching scope throws the list away and loads another, so anything still
  // sitting in the 800ms debounce goes now rather than after the swap.
  const handleScope = useCallback((next) => {
    if (next === scope) return;
    flushAll();
    setScope(next);
    setSelectedId(null);
  }, [flushAll, scope]);

  const togglePin = useCallback(async () => {
    if (!selectedId || !selectedNote) return;
    const next = !selectedNote.pinned;
    setNotes(prev => prev.map(n => (n.id === selectedId ? { ...n, pinned: next } : n)));
    try {
      const saved = await api.updateNote(selectedId, { is_pinned: next });
      setNotes(prev => prev.map(n => (n.id === selectedId ? fromServer(saved) : n)));
    } catch {
      setNotes(prev => prev.map(n => (n.id === selectedId ? { ...n, pinned: !next } : n)));
    }
  }, [selectedId, selectedNote]);

  const hasNotes = notes.length > 0;
  const hasResults = filtered.length > 0;
  const pinnedCount = notes.filter((n) => n.pinned).length;

  // Which set is on screen, and how much of it — "NOTES" alone said neither.
  const noteStats = [
    { label: scope === 'alfred' ? "of Alfred's" : 'notes', value: notes.length },
    ...(pinnedCount ? [{ label: 'pinned', value: pinnedCount, tone: 'self' }] : []),
  ];

  return (
    <div className="h-full flex flex-col bg-bat-bg">
      <div className="shrink-0 px-6 pt-5 pb-3 border-b border-white/[0.04]">
        <PageHeader
          title="NOTES"
          stats={noteStats}
          action={<Button tone="self" onClick={handleNew}><Plus size={13} /> New note</Button>}
        />
      </div>

      <div className="flex-1 min-h-0 flex gap-gutter p-4">
        <aside className="w-80 shrink-0 flex flex-col rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile overflow-hidden">
          <div className="shrink-0 p-3 border-b border-white/[0.04] space-y-2">
            <Segmented
              label="Whose notes"
              value={scope}
              onChange={handleScope}
              options={[{ value: 'mine', label: 'Mine' }, { value: 'alfred', label: "Alfred's" }]}
            />
            <input
              type="text" placeholder="Search notes..." value={search}
              onChange={e => setSearch(e.target.value)}
              aria-label="Search notes"
              className={`${fieldClass} text-sm`}
            />
            <select
              value={sortBy} onChange={e => setSortBy(e.target.value)}
              aria-label="Sort notes"
              className={`${fieldClass} text-xs cursor-pointer`}
            >
              <option value="edited">Last edited</option>
              <option value="created">Created</option>
              <option value="title">Title</option>
            </select>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading ? (
              <div className="p-6 text-center text-xs font-mono uppercase tracking-[0.14em] text-ink-faint">Loading...</div>
            ) : !hasNotes ? (
              // This was a Batman quote. A quote is not an empty state: it
              // told you neither what was missing nor what to do about it.
              <EmptyState compact>
                {scope === 'alfred' ? 'Alfred has written nothing yet' : 'No notes yet'}
              </EmptyState>
            ) : !hasResults ? (
              <EmptyState compact>Nothing matches "{search}"</EmptyState>
            ) : filtered.map(note => (
              <div
                key={note.id} onClick={() => handleSelect(note.id)}
                className={`group relative rounded-tile px-3 py-2.5 cursor-pointer ring-1
                  transition-all duration-200 ease-soft ${
                  selectedId === note.id
                    ? 'bg-bat-raised ring-signal-self/40'
                    : 'bg-transparent ring-transparent hover:bg-bat-raised/60 hover:ring-bat-line'
                }`}
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      {note.pinned && <Pin size={10} className="text-signal-self shrink-0" aria-label="Pinned" />}
                      <span className={`text-sm truncate ${selectedId === note.id ? 'text-signal-self' : 'text-ink'}`}>
                        {note.title || 'Untitled'}
                      </span>
                    </div>
                    <div className="text-[11px] text-ink-faint truncate mt-0.5">
                      {note.body ? note.body.replace(/\n/g, ' ') : 'Empty'}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {note.category && (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-chip bg-bat-surface ring-1 ring-bat-line text-ink-muted">
                          {note.category}
                        </span>
                      )}
                      <span className="text-[9px] font-mono text-ink-faint">
                        {note.updatedAt ? new Date(note.updatedAt).toLocaleDateString([], { month: 'short', day: 'numeric' }) : ''}
                      </span>
                    </div>
                  </div>
                  {/* This was opacity-0 until hover, with no accessible name.
                      On a touch screen there is no hover, so the note simply
                      could not be deleted — which is exactly what was
                      reported. It is always there now, and it says so. */}
                  <IconButton
                    label={`Delete "${note.title || 'Untitled'}"`}
                    icon={Trash2}
                    tone="danger"
                    size={12}
                    className="opacity-70 group-hover:opacity-100 shrink-0"
                    onClick={e => { e.stopPropagation(); handleDelete(note.id, note.title); }}
                  />
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="flex-1 min-w-0 flex flex-col rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile overflow-hidden">
          {!selectedNote ? (
            <div className="flex-1 flex items-center justify-center p-6">
              <EmptyState action={<Button tone="self" onClick={handleNew}><Plus size={13} /> New note</Button>}>
                Pick a note, or start one
              </EmptyState>
            </div>
          ) : (
            <>
              <div className="shrink-0 p-5 pb-2">
                <input
                  ref={titleRef}
                  type="text" placeholder="Title"
                  value={selectedNote.title}
                  onChange={e => updateField('title', e.target.value)}
                  aria-label="Note title"
                  className="w-full text-xl font-display text-ink bg-transparent border-none outline-none placeholder-ink-faint tracking-wide"
                />
              </div>

              <div className="flex-1 px-5 pb-2">
                <textarea
                  placeholder="Start writing..."
                  value={selectedNote.body}
                  onChange={e => updateField('body', e.target.value)}
                  aria-label="Note body"
                  className="w-full h-full text-sm text-ink-muted bg-transparent border-none outline-none resize-none leading-relaxed placeholder-ink-faint"
                />
              </div>

              <div className="shrink-0 border-t border-white/[0.04] px-5 py-3 flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <input
                    type="text" placeholder="Tag" value={selectedNote.category}
                    onChange={e => updateField('category', e.target.value)}
                    list="note-tags"
                    aria-label="Tag"
                    className={`${fieldClass} w-28 text-xs`}
                  />
                  <datalist id="note-tags">
                    {allTags.map(t => <option key={t} value={t} />)}
                  </datalist>
                  <Button
                    size="sm"
                    onClick={togglePin}
                    aria-pressed={selectedNote.pinned}
                    className={selectedNote.pinned ? 'text-signal-self ring-signal-self/40' : ''}
                  >
                    <Pin size={11} /> {selectedNote.pinned ? 'Pinned' : 'Pin'}
                  </Button>
                  {/* Deleting used to be possible only from the list, and
                      only on hover — not from the note you were reading. */}
                  <IconButton
                    label={`Delete "${selectedNote.title || 'Untitled'}"`}
                    icon={Trash2}
                    tone="danger"
                    onClick={() => handleDelete(selectedNote.id, selectedNote.title)}
                  />
                </div>

                <div className="flex items-center gap-3 text-[10px] font-mono text-ink-faint tabular-nums">
                  <span>{counts.words} words</span>
                  <span>{counts.chars} chars</span>
                  {selectedNote.updatedAt && (
                    <span>
                      {new Date(selectedNote.updatedAt).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                  )}
                  {saving && <span role="status" className="text-signal-good">Saved</span>}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
