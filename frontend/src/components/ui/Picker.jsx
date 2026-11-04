import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Search } from 'lucide-react';

/**
 * A chooser that can cope with a long list.
 *
 * This replaced a native `<select>` with `<optgroup>`s. The browser draws that
 * one itself, so none of this project's styling reached it: it opened as a
 * white-and-blue operating-system list, in the OS font, ignoring every token.
 * With thirty-odd missions in it the list also ran the full height of the
 * screen and off the bottom, and there was no way to search it — finding one
 * mission meant reading thirty titles, several of them a sentence long.
 *
 * The open list is rendered through a PORTAL rather than as a child. Panel
 * clips its contents (`overflow-hidden`, so children cannot escape its
 * rounded corners), which cut the list down to the three rows that happened
 * to fit inside the panel — a scrolling list trapped in a box too short to
 * scroll it. Nesting is the wrong relationship for an overlay: it has to be
 * measured against the viewport and owe nothing to whatever it was declared
 * inside.
 *
 * Built rather than installed, because one combobox does not justify a
 * dependency, and the keyboard and ARIA behaviour here is about sixty lines.
 */

// Below this many options a search box is noise — it costs a row of chrome
// and a keystroke to filter five things you can already see.
const SEARCH_FROM = 8;

// How tall the floating list may get, and how far it sits off the trigger.
const MAX_PANEL = 320;
const GAP = 4;
const SEARCH_ROW = 37;

export default function Picker({
  label,
  value,
  onChange,
  groups = [],
  emptyOption = null,
  placeholder = 'Choose…',
  disabled = false,
  id,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [box, setBox] = useState(null);
  const wrapRef = useRef(null);
  const panelRef = useRef(null);
  const listRef = useRef(null);
  const searchRef = useRef(null);

  // One flat list of what is actually selectable right now, in the order it
  // appears, so the arrow keys and the rendering can never disagree about
  // which row is which.
  const flat = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (text) => !q || String(text || '').toLowerCase().includes(q);
    const out = [];
    if (emptyOption && match(emptyOption.label)) out.push({ ...emptyOption, group: null });
    groups.forEach((g) => {
      (g.options || []).filter((o) => match(o.label))
        .forEach((o) => out.push({ ...o, group: g.label }));
    });
    return out;
  }, [groups, emptyOption, query]);

  const selected = flat.find((o) => o.value === value)
    || (emptyOption && emptyOption.value === value ? emptyOption : null)
    || groups.flatMap((g) => g.options || []).find((o) => o.value === value);

  const total = groups.reduce((n, g) => n + (g.options || []).length, 0);
  const searchable = total >= SEARCH_FROM;

  // Position against the VIEWPORT, and open upwards when there is more room
  // up there — otherwise a control low on the page drops its list off the
  // bottom of the window, which is half of what went wrong here.
  const place = () => {
    const el = wrapRef.current;
    if (!el || typeof el.getBoundingClientRect !== 'function') return;
    const r = el.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - GAP;
    const above = r.top - GAP;
    const downwards = below >= 240 || below >= above;
    setBox({
      left: r.left,
      width: r.width,
      top: downwards ? r.bottom + GAP : undefined,
      bottom: downwards ? undefined : window.innerHeight - r.top + GAP,
      maxHeight: Math.max(160, Math.min(MAX_PANEL, downwards ? below : above)),
    });
  };

  useLayoutEffect(() => {
    if (!open) return undefined;
    place();
    // Scrolling or resizing moves the trigger, and a fixed overlay does not
    // follow it on its own.
    const onMove = () => place();
    window.addEventListener('scroll', onMove, true);
    window.addEventListener('resize', onMove);
    return () => {
      window.removeEventListener('scroll', onMove, true);
      window.removeEventListener('resize', onMove);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Close on a click anywhere else. The list is portalled out of this
  // subtree, so "elsewhere" means neither the trigger nor the floating panel
  // — containment alone would close it the instant an option was hit.
  // mousedown, not click: a drag starting outside and ending inside would
  // otherwise leave it open.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      const inTrigger = wrapRef.current && wrapRef.current.contains(e.target);
      const inPanel = panelRef.current && panelRef.current.contains(e.target);
      if (!inTrigger && !inPanel) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  useEffect(() => {
    if (!open) { setQuery(''); return; }
    const i = flat.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
    if (searchable && searchRef.current) searchRef.current.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Keep the highlighted row on screen; without this, holding Down walks the
  // selection out of the visible part of the list.
  useEffect(() => {
    const node = listRef.current?.querySelector(`[data-idx="${active}"]`);
    if (node?.scrollIntoView) node.scrollIntoView({ block: 'nearest' });
  }, [active, open]);

  const choose = (option) => {
    onChange(option.value);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (disabled) return;
    if (!open) {
      if (['Enter', ' ', 'ArrowDown'].includes(e.key)) { e.preventDefault(); setOpen(true); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, flat.length - 1)); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); return; }
    if (e.key === 'Home') { e.preventDefault(); setActive(0); return; }
    if (e.key === 'End') { e.preventDefault(); setActive(flat.length - 1); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (flat[active]) choose(flat[active]);
    }
  };

  const listHeight = box
    ? Math.max(120, box.maxHeight - (searchable ? SEARCH_ROW : 0))
    : 256;

  const panel = (
    <div
      ref={panelRef}
      // No onKeyDown here. A React portal still bubbles events up the REACT
      // tree, not the DOM one, so a handler here AND on the wrapper below
      // fires twice for one keypress — every ArrowDown moved two rows.
      style={box ? {
        position: 'fixed',
        left: box.left,
        width: box.width,
        top: box.top,
        bottom: box.bottom,
      } : undefined}
      className="z-[1000] rounded-tile bg-bat-surface ring-1 ring-bat-line-strong shadow-lift overflow-hidden"
    >
      {searchable && (
        <div className="flex items-center gap-2 border-b border-bat-line px-2.5 py-2">
          <Search size={12} className="shrink-0 text-ink-faint" />
          <input
            ref={searchRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
            placeholder="Search"
            aria-label={`Search ${label}`}
            className="w-full bg-transparent font-mono text-xs text-ink
              placeholder:text-ink-faint focus:outline-none"
          />
        </div>
      )}

      {/* A bounded height, because the whole point is that it stops covering
          the screen when there are thirty of them. */}
      <div
        ref={listRef}
        role="listbox"
        aria-label={label}
        style={{ maxHeight: listHeight }}
        className="max-h-80 overflow-y-auto py-1"
      >
        {flat.length === 0 && (
          <p className="px-3 py-3 font-mono text-[11px] text-ink-faint">Nothing matches that.</p>
        )}
        {flat.map((o, i) => {
          const showHeading = o.group && (i === 0 || flat[i - 1].group !== o.group);
          const on = i === active;
          const isSelected = o.value === value;
          return (
            <React.Fragment key={`${o.group || ''}:${o.value}`}>
              {showHeading && (
                <div className="px-3 pt-2 pb-1 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
                  {o.group}
                </div>
              )}
              <button
                type="button"
                data-idx={i}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(o)}
                title={o.label}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-left
                  font-mono text-xs transition-colors duration-150 ease-soft
                  ${on ? 'bg-bat-raised text-ink' : 'text-ink-muted'}
                  ${isSelected ? 'text-signal-self' : ''}`}
              >
                <Check
                  size={11}
                  className={`shrink-0 ${isSelected ? 'text-signal-self' : 'opacity-0'}`}
                />
                <span className="truncate">{o.label}</span>
              </button>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="relative" ref={wrapRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        className={`w-full flex items-center justify-between gap-2 rounded-chip
          bg-bat-raised ring-1 ring-bat-line px-3 py-2 text-left font-mono text-xs
          transition-all duration-200 ease-soft
          focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:ring-bat-line-strong'}
          ${selected && selected.value ? 'text-ink' : 'text-ink-faint'}`}
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-ink-faint transition-transform duration-200 ease-soft ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (typeof document !== 'undefined' ? createPortal(panel, document.body) : panel)}
    </div>
  );
}
