import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { api } from '../utils/api';
import { Button, EmptyState, IconButton, Panel } from './ui';
import TransactionForm from './TransactionForm';
import { formatMinor, monthWindow, toDateString } from '../utils/money';

/**
 * The ledger screen: one month, four ways of looking at it.
 *
 * Daily is the record, Calendar is the shape of the month, Monthly is the year
 * at a glance, Summary is where the money sits. The three figures at the top —
 * in, out, and the difference — never move, because they are the question the
 * screen exists to answer.
 *
 * Transfers appear in Daily so the record is complete, and are excluded from
 * every total, because moving your own money between your own pockets is
 * neither earning nor spending.
 */

const VIEWS = [
  { id: 'daily', label: 'Daily' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'monthly', label: 'Monthly' },
  { id: 'summary', label: 'Summary' },
];

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const SHORT_DAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const GROUP_LABELS = {
  cash: 'Cash', bank: 'Accounts', card: 'Card', savings: 'Savings',
  investment: 'Investments', loan: 'Loans', insurance: 'Insurance', other: 'Other',
};
// What a positive balance means you owe rather than hold.
const LIABILITY_GROUPS = ['card', 'loan'];

const monthLabel = (y, m) =>
  new Date(y, m, 1).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });

// Monday-first index, derived from the date itself rather than from a row's
// position, which is only right when a month happens to start on a Monday.
const weekdayIndex = (dateStr) => {
  const d = new Date(`${dateStr}T00:00:00`);
  return (d.getDay() + 6) % 7;
};

export default function FinancePanel({ onRefreshAccount }) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [monthIndex, setMonthIndex] = useState(today.getMonth());
  const [view, setView] = useState('daily');
  const [adding, setAdding] = useState(false);

  const [settings, setSettings] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [ledger, setLedger] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const startDay = settings?.period_start_day || 1;
  const window = useMemo(
    () => monthWindow(year, monthIndex, startDay),
    [year, monthIndex, startDay],
  );
  const currency = settings?.main_currency || accounts[0]?.currency || '';

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, a, c, l] = await Promise.all([
        api.getFinanceSettings(),
        api.getFinanceAccounts(),
        api.getFinanceCategories(),
        api.getLedger(window.start, window.end),
      ]);
      setSettings(s);
      setAccounts(a);
      setCategories(c);
      setLedger(l);
    } catch (err) {
      setError(err.message || 'The ledger would not load.');
    } finally {
      setLoading(false);
    }
  }, [window.start, window.end]);

  useEffect(() => { load(); }, [load]);

  const step = (delta) => {
    const next = new Date(year, monthIndex + delta, 1);
    setYear(next.getFullYear());
    setMonthIndex(next.getMonth());
  };

  const totals = ledger?.totals || { income_minor: 0, expense_minor: 0, net_minor: 0 };
  const transactions = ledger?.transactions || [];

  const handleSaved = async () => {
    setAdding(false);
    await load();
    onRefreshAccount?.();
  };

  const handleDelete = async (id) => {
    await api.deleteTransaction(id);
    await load();
  };

  if (loading) {
    return <Panel title="MONEY"><div className="py-10 text-center font-mono text-xs text-ink-faint">
      OPENING THE LEDGER...
    </div></Panel>;
  }

  if (!accounts.length && !adding) {
    return (
      <Panel title="MONEY" bodyClassName="p-4">
        <EmptyState action={<Button tone="primary" onClick={() => setAdding(true)}>Set up an account</Button>}>
          Nothing to track yet — add where your money sits
        </EmptyState>
        {error && <p className="mt-3 text-[11px] text-signal-late">{error}</p>}
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <Panel
        title="MONEY"
        action={
          <Button tone="primary" size="sm" onClick={() => setAdding((v) => !v)}>
            <Plus size={14} /> {adding ? 'Close' : 'Add'}
          </Button>
        }
        bodyClassName="p-0"
      >
        {/* Month navigation */}
        <div className="flex items-center justify-center gap-4 px-4 py-3 border-b border-white/[0.04]">
          <IconButton label="Previous month" icon={ChevronLeft} size={16} onClick={() => step(-1)} />
          <span data-testid="finance-month"
                className="font-mono text-sm uppercase tracking-widest text-ink">
            {monthLabel(year, monthIndex)}
          </span>
          <IconButton label="Next month" icon={ChevronRight} size={16} onClick={() => step(1)} />
        </div>

        {/* The three figures. They never move. */}
        <div data-testid="finance-totals"
             className="grid grid-cols-3 divide-x divide-white/[0.04] border-b border-white/[0.04]">
          <Figure label="Income" value={totals.income_minor} currency={currency} tone="in" />
          <Figure label="Exp." value={totals.expense_minor} currency={currency} tone="out" />
          <Figure label="Total" value={totals.net_minor} currency={currency} tone="net" />
        </div>

        <div className="flex gap-1 px-2 pt-2 overflow-x-auto">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setView(v.id)}
              aria-pressed={view === v.id}
              data-testid={`finance-view-${v.id}`}
              className={`px-3 py-2 text-[11px] font-mono uppercase tracking-widest whitespace-nowrap
                border-b-2 transition-colors ${view === v.id
                  ? 'border-signal-late text-ink'
                  : 'border-transparent text-ink-faint hover:text-ink-muted'}`}
            >
              {v.label}
            </button>
          ))}
        </div>

        <div className="p-3">
          {adding && (
            <div className="mb-4 rounded-tile bg-bat-surface ring-1 ring-bat-line p-3">
              <TransactionForm
                accounts={accounts}
                categories={categories}
                onSaved={handleSaved}
                onCancel={() => setAdding(false)}
              />
            </div>
          )}

          {error && <p className="mb-3 text-[11px] text-signal-late">{error}</p>}

          {view === 'daily' && (
            <DailyView rows={transactions} currency={currency} onDelete={handleDelete} />
          )}
          {view === 'calendar' && (
            <CalendarView rows={transactions} year={year} monthIndex={monthIndex}
                          window={window} currency={currency} />
          )}
          {view === 'monthly' && (
            <MonthlyView rows={transactions} window={window} currency={currency} />
          )}
          {view === 'summary' && (
            <SummaryView accounts={accounts} rows={transactions} currency={currency} />
          )}
        </div>
      </Panel>
    </div>
  );
}

function Figure({ label, value, currency, tone }) {
  const colour = tone === 'in' ? 'text-sky-400'
    : tone === 'out' ? 'text-signal-late'
    : value < 0 ? 'text-signal-late' : 'text-ink';
  return (
    <div className="px-3 py-3 text-center">
      <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">{label}</div>
      <div className={`mt-1 font-mono text-sm tabular-nums ${colour}`}>
        {formatMinor(value, currency)}
      </div>
    </div>
  );
}

/** The record, grouped by the day it happened on. */
function DailyView({ rows, currency, onDelete }) {
  const days = useMemo(() => {
    const byDay = new Map();
    for (const row of rows) {
      if (!byDay.has(row.occurred_on)) byDay.set(row.occurred_on, []);
      byDay.get(row.occurred_on).push(row);
    }
    return [...byDay.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [rows]);

  if (!days.length) return <EmptyState compact>Nothing recorded this month</EmptyState>;

  return (
    <div className="space-y-4" data-testid="finance-daily">
      {days.map(([date, items]) => {
        const income = items.filter((i) => i.kind === 'income')
          .reduce((t, i) => t + i.amount_minor * (i.rate_to_main || 1), 0);
        const expense = items.filter((i) => i.kind === 'expense')
          .reduce((t, i) => t + i.amount_minor * (i.rate_to_main || 1), 0);
        const d = new Date(`${date}T00:00:00`);

        return (
          <div key={date} data-testid={`finance-day-${date}`}>
            <div className="flex items-center gap-2 px-1 py-2 border-b border-white/[0.06]">
              <span className="font-mono text-lg tabular-nums text-ink">{d.getDate()}</span>
              <span className="rounded-chip bg-bat-raised px-1.5 py-0.5 text-[9px] font-mono
                uppercase tracking-widest text-ink-muted">
                {SHORT_DAY[d.getDay()]}
              </span>
              <span className="ml-auto font-mono text-[11px] tabular-nums text-sky-400">
                {formatMinor(Math.round(income), currency)}
              </span>
              <span className="font-mono text-[11px] tabular-nums text-signal-late">
                {formatMinor(Math.round(expense), currency)}
              </span>
            </div>

            {items.map((row) => <Row key={row.id} row={row} currency={currency} onDelete={onDelete} />)}
          </div>
        );
      })}
    </div>
  );
}

function Row({ row, currency, onDelete }) {
  const transfer = row.kind === 'transfer';
  const amountColour = transfer ? 'text-ink-muted'
    : row.kind === 'income' ? 'text-sky-400' : 'text-signal-late';

  return (
    <div className="group flex items-center gap-3 px-1 py-2.5 border-b border-white/[0.03]"
         data-testid={`finance-row-${row.id}`} data-kind={row.kind}>
      <div className="w-24 shrink-0 min-w-0">
        <div className="truncate text-[11px] text-ink-muted">
          {transfer ? 'Transfer' : `${row.category_icon || ''} ${row.parent_category_name || row.category_name || 'Other'}`.trim()}
        </div>
        {!transfer && row.parent_category_name && (
          <div className="truncate text-[10px] text-ink-faint">{row.category_name}</div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-ink">
          {transfer
            ? `${row.from_account_name} → ${row.to_account_name}`
            : (row.note || row.category_name || '—')}
        </div>
        <div className="truncate text-[11px] text-ink-faint">
          {transfer ? '' : (row.from_account_name || row.to_account_name || '')}
        </div>
      </div>

      <div className={`shrink-0 font-mono text-sm tabular-nums ${amountColour}`}>
        {formatMinor(row.amount_minor, row.currency || currency)}
      </div>

      <button
        type="button"
        onClick={() => onDelete(row.id)}
        aria-label={`Delete ${row.note || 'this record'}`}
        className="shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100
          text-ink-faint hover:text-signal-late transition-opacity"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

/** The shape of the month: what came in, what went out, on which days. */
function CalendarView({ rows, window, currency }) {
  const byDay = useMemo(() => {
    const map = new Map();
    for (const row of rows) {
      if (row.kind === 'transfer') continue;   // not earning, not spending
      const entry = map.get(row.occurred_on) || { income: 0, expense: 0 };
      const amount = row.amount_minor * (row.rate_to_main || 1);
      if (row.kind === 'income') entry.income += amount; else entry.expense += amount;
      map.set(row.occurred_on, entry);
    }
    return map;
  }, [rows]);

  // Built from the window, so a month that starts on payday still draws right.
  const days = useMemo(() => {
    const out = [];
    const cursor = new Date(`${window.start}T00:00:00`);
    const last = new Date(`${window.end}T00:00:00`);
    while (cursor <= last) {
      out.push(toDateString(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }, [window.start, window.end]);

  const blanks = days.length ? weekdayIndex(days[0]) : 0;

  return (
    <div data-testid="finance-calendar">
      <div className="grid grid-cols-7 gap-px mb-px">
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-center text-[9px] font-mono uppercase tracking-widest text-ink-faint py-1">
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px">
        {Array.from({ length: blanks }, (_, i) => <div key={`b-${i}`} aria-hidden="true" />)}
        {days.map((date) => {
          const entry = byDay.get(date);
          const net = entry ? entry.income - entry.expense : 0;
          return (
            <div key={date} data-testid={`finance-cal-${date}`}
                 className="min-h-[58px] rounded-[4px] bg-bat-surface/40 p-1 text-right">
              <div className="text-[10px] font-mono tabular-nums text-ink-muted">
                {Number(date.slice(8, 10))}
              </div>
              {entry?.income > 0 && (
                <div className="text-[9px] font-mono tabular-nums text-sky-400 truncate">
                  {formatMinor(Math.round(entry.income), currency)}
                </div>
              )}
              {entry?.expense > 0 && (
                <div className="text-[9px] font-mono tabular-nums text-signal-late truncate">
                  {formatMinor(Math.round(entry.expense), currency)}
                </div>
              )}
              {entry && entry.income > 0 && entry.expense > 0 && (
                <div className="text-[9px] font-mono tabular-nums text-ink truncate">
                  {formatMinor(Math.round(net), currency)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** The month broken into its weeks, which is where a bad week shows up. */
function MonthlyView({ rows, window, currency }) {
  const weeks = useMemo(() => {
    const out = [];
    const cursor = new Date(`${window.start}T00:00:00`);
    const last = new Date(`${window.end}T00:00:00`);

    while (cursor <= last) {
      const start = new Date(cursor);
      const end = new Date(cursor);
      end.setDate(end.getDate() + 6);
      if (end > last) end.setTime(last.getTime());

      const s = toDateString(start);
      const e = toDateString(end);
      let income = 0; let expense = 0;
      for (const row of rows) {
        if (row.occurred_on < s || row.occurred_on > e) continue;
        const amount = row.amount_minor * (row.rate_to_main || 1);
        if (row.kind === 'income') income += amount;
        else if (row.kind === 'expense') expense += amount;
      }
      out.push({ s, e, income: Math.round(income), expense: Math.round(expense) });
      cursor.setDate(cursor.getDate() + 7);
    }
    return out;
  }, [rows, window.start, window.end]);

  const fmt = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;

  return (
    <div className="divide-y divide-white/[0.04]" data-testid="finance-monthly">
      {weeks.map((w) => {
        const net = w.income - w.expense;
        return (
          <div key={w.s} data-testid={`finance-week-${w.s}`}
               className={`flex items-center gap-3 px-2 py-3 ${net < 0 ? 'bg-signal-late/[0.07]' : ''}`}>
            <span className="font-mono text-[11px] tabular-nums text-ink-muted">
              {fmt(w.s)} ~ {fmt(w.e)}
            </span>
            <span className="ml-auto font-mono text-[11px] tabular-nums text-sky-400">
              {formatMinor(w.income, currency)}
            </span>
            <span className="w-28 text-right font-mono text-[11px] tabular-nums text-signal-late">
              {formatMinor(w.expense, currency)}
            </span>
            <span className={`w-28 text-right font-mono text-[11px] tabular-nums
              ${net < 0 ? 'text-signal-late' : 'text-ink'}`}>
              {formatMinor(net, currency)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Where the money sits, and what it is doing. */
function SummaryView({ accounts, rows, currency }) {
  const groups = useMemo(() => {
    const map = new Map();
    for (const a of accounts) {
      if (!map.has(a.group)) map.set(a.group, []);
      map.get(a.group).push(a);
    }
    return [...map.entries()];
  }, [accounts]);

  // A card balance is money owed, not money held — so it counts against the
  // total rather than toward it. A net worth that adds up your debts is a lie.
  const assets = accounts
    .filter((a) => !LIABILITY_GROUPS.includes(a.group))
    .reduce((t, a) => t + a.balance_minor, 0);
  const liabilities = accounts
    .filter((a) => LIABILITY_GROUPS.includes(a.group))
    .reduce((t, a) => t + Math.max(0, -a.balance_minor), 0);

  const byCategory = useMemo(() => {
    const map = new Map();
    for (const row of rows) {
      if (row.kind !== 'expense') continue;
      const name = row.parent_category_name || row.category_name || 'Unknown';
      const icon = row.category_icon || '';
      const current = map.get(name) || { total: 0, icon };
      current.total += row.amount_minor * (row.rate_to_main || 1);
      map.set(name, current);
    }
    const total = [...map.values()].reduce((t, c) => t + c.total, 0);
    return [...map.entries()]
      .map(([name, c]) => ({ name, icon: c.icon, total: Math.round(c.total),
                             share: total ? Math.round((c.total / total) * 100) : 0 }))
      .sort((a, b) => b.total - a.total);
  }, [rows]);

  return (
    <div className="space-y-5" data-testid="finance-summary">
      <div className="grid grid-cols-3 gap-2" data-testid="finance-networth">
        <Figure label="Assets" value={assets} currency={currency} tone="in" />
        <Figure label="Liabilities" value={liabilities} currency={currency} tone="out" />
        <Figure label="Net" value={assets - liabilities} currency={currency} tone="net" />
      </div>

      {groups.map(([group, list]) => (
        <div key={group}>
          <div className="px-1 pb-1 text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">
            {GROUP_LABELS[group] || group}
          </div>
          {list.map((a) => (
            <div key={a.id} data-testid={`finance-account-${a.id}`}
                 className="flex items-center gap-3 px-1 py-2 border-b border-white/[0.03]">
              <span className="truncate text-sm text-ink">{a.name}</span>
              <span className="ml-auto font-mono text-sm tabular-nums text-ink">
                {a.currency} {formatMinor(a.balance_minor, a.currency)}
              </span>
            </div>
          ))}
        </div>
      ))}

      {byCategory.length > 0 && (
        <div data-testid="finance-by-category">
          <div className="px-1 pb-1 text-[10px] font-mono uppercase tracking-[0.14em] text-ink-faint">
            Where it went
          </div>
          {byCategory.map((c) => (
            <div key={c.name} className="flex items-center gap-3 px-1 py-2 border-b border-white/[0.03]">
              <span className="w-10 shrink-0 rounded-chip bg-bat-raised px-1.5 py-0.5 text-center
                text-[10px] font-mono tabular-nums text-ink-muted">{c.share}%</span>
              <span className="truncate text-sm text-ink">{c.icon} {c.name}</span>
              <span className="ml-auto font-mono text-sm tabular-nums text-ink">
                {formatMinor(c.total, currency)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
