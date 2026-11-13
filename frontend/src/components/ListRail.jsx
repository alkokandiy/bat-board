import React, { useState } from 'react';
import {
  Archive, ArchiveRestore, Check, Inbox, Pencil, Plus, Trash2, X,
} from 'lucide-react';
import { Panel, IconButton, fieldClass } from './ui';

/**
 * The rail of lists: Inbox first (it is not a row, it is "no list yet"),
 * then the live lists in their order, then an All that clears the filter.
 *
 * `selected` is null for All, 'inbox', or a list id — the same three shapes
 * the API speaks.
 *
 * Renaming, archiving and deleting happen here rather than in a separate
 * screen, because a list is one word of metadata; but deleting always asks,
 * and the ask says where the missions go — they are refiled to the Inbox,
 * never deleted, and a control that destroys nothing must not read as if
 * it does.
 */
export default function ListRail({
  lists,
  archivedLists = [],
  counts = {},
  selected = null,
  onSelect,
  onCreate,
  onRename,
  onArchive,
  onRestore,
  onDelete,
}) {
  const [adding, setAdding] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [renamingId, setRenamingId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [confirmingId, setConfirmingId] = useState(null);
  const [error, setError] = useState(null);

  const run = async (fn) => {
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      // The server's message is meant to be read: a duplicate or empty
      // name comes back as a 400 with the reason in it.
      setError(err.message);
      return false;
    }
  };

  const submitCreate = async () => {
    const name = draftName.trim();
    if (!name) return;
    const ok = await run(() => onCreate(name));
    if (ok) { setDraftName(''); setAdding(false); }
  };

  const submitRename = async (id) => {
    const name = renameDraft.trim();
    if (!name) return;
    const ok = await run(() => onRename(id, name));
    if (ok) setRenamingId(null);
  };

  const inboxCount = counts.inbox || 0;

  const rowButton = (label, value, count, extraClass = '') => (
    <button
      type="button"
      onClick={() => onSelect(value)}
      aria-pressed={selected === value}
      className={`group w-full flex items-center justify-between gap-2 rounded-chip px-2.5 py-1.5
        text-left font-mono text-xs transition-all duration-200 ease-soft
        focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
        ${selected === value
          ? 'bg-bat-raised text-signal-self ring-1 ring-signal-self/30'
          : `text-ink-muted ring-1 ring-transparent hover:bg-bat-raised hover:text-ink ${extraClass}`}`}
    >
      <span className="truncate">{label}</span>
      {/* A zero count renders nothing: an emphatic "0" on every empty list
          is noise, and the absence of a number already says it. */}
      {count > 0 && (
        <span
          className={`shrink-0 text-[10px] tabular-nums px-1.5 py-0.5 rounded-chip
            ${selected === value
              ? 'bg-signal-self/10 text-signal-self'
              : 'bg-bat-surface text-ink-faint ring-1 ring-bat-line'}`}
        >
          {count}
        </span>
      )}
    </button>
  );

  return (
    <Panel
      title="Lists"
      meta="where things are filed"
      bodyClassName="p-2.5 space-y-0.5"
    >
      {rowButton('All', null, null)}
      {rowButton('Inbox', 'inbox', inboxCount)}

      {lists.map((list) => (
        <div key={list.id} className="relative">
          {renamingId === list.id ? (
            <div className="flex items-center gap-1 px-1 py-0.5">
              <input
                type="text"
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); submitRename(list.id); }
                  if (e.key === 'Escape') setRenamingId(null);
                }}
                autoFocus
                aria-label={`Rename list ${list.name}`}
                className={`${fieldClass} text-xs py-1`}
              />
              <IconButton label={`Save name for "${list.name}"`} onClick={() => submitRename(list.id)} icon={Check} />
              <IconButton label={`Cancel renaming "${list.name}"`} onClick={() => setRenamingId(null)} icon={X} />
            </div>
          ) : confirmingId === list.id ? (
            <div className="rounded-chip bg-bat-raised ring-1 ring-signal-late/30 px-2.5 py-2 space-y-2">
              <p className="text-[11px] leading-snug text-ink-muted">
                Delete <span className="text-ink">{list.name}</span>?
                {' '}Its missions move to the Inbox — nothing is deleted.
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={async () => {
                    setConfirmingId(null);
                    await run(() => onDelete(list.id));
                  }}
                  className="rounded-chip px-2 py-1 text-[10px] font-mono uppercase tracking-widest
                    text-signal-late ring-1 ring-signal-late/40 hover:bg-signal-late/10
                    transition-colors duration-200"
                >
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingId(null)}
                  className="px-2 py-1 text-[10px] font-mono uppercase tracking-widest text-ink-faint hover:text-ink-muted transition-colors duration-200"
                >
                  Keep
                </button>
              </div>
            </div>
          ) : (
            <div className="group flex items-center gap-1">
              <div className="flex-1 min-w-0">
                {rowButton(
                  <span className="flex items-center gap-1.5 min-w-0">
                    {list.color && (
                      <span
                        className="w-1.5 h-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: list.color }}
                        aria-hidden="true"
                      />
                    )}
                    {list.name}
                  </span>,
                  list.id,
                  list.open_missions,
                )}
              </div>
              {/* Row actions stay out of the way until the row is approached. */}
              <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
                <IconButton
                  label={`Rename "${list.name}"`}
                  onClick={() => { setRenamingId(list.id); setRenameDraft(list.name); }}
                  icon={Pencil}
                />
                <IconButton
                  label={`Archive "${list.name}"`}
                  onClick={() => run(() => onArchive(list.id))}
                  icon={Archive}
                />
                <IconButton
                  label={`Delete "${list.name}"`}
                  onClick={() => setConfirmingId(list.id)}
                  icon={Trash2}
                  tone="danger"
                />
              </div>
            </div>
          )}
        </div>
      ))}

      {adding ? (
        <div className="flex items-center gap-1 px-1 py-0.5">
          <input
            type="text"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); submitCreate(); }
              if (e.key === 'Escape') { setAdding(false); setDraftName(''); }
            }}
            autoFocus
            placeholder="New list"
            aria-label="New list name"
            className={`${fieldClass} text-xs py-1`}
          />
          <IconButton label="Save list" onClick={submitCreate} icon={Check} />
          <IconButton label="Cancel new list" onClick={() => { setAdding(false); setDraftName(''); }} icon={X} />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="w-full flex items-center gap-1.5 rounded-chip px-2.5 py-1.5
            font-mono text-xs text-ink-faint hover:text-ink hover:bg-bat-raised
            transition-all duration-200 ease-soft
            focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60"
        >
          <Plus size={12} /> Add list
        </button>
      )}

      {archivedLists.length > 0 && (
        <details className="pt-1">
          <summary className="px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint hover:text-ink-muted cursor-pointer transition-colors duration-200">
            Archived ({archivedLists.length})
          </summary>
          <div className="space-y-0.5 mt-1">
            {archivedLists.map((list) => (
              <div key={list.id} className="flex items-center gap-1">
                <span className="flex-1 min-w-0 truncate px-2.5 py-1.5 font-mono text-xs text-ink-faint line-through">
                  {list.name}
                </span>
                <IconButton label={`Restore "${list.name}"`} onClick={() => run(() => onRestore(list.id))} icon={ArchiveRestore} />
              </div>
            ))}
          </div>
        </details>
      )}

      {error && (
        <p role="alert" className="px-2.5 pt-1 text-[10px] text-signal-late">{error}</p>
      )}
    </Panel>
  );
}
