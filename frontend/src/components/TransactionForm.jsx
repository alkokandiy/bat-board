import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../utils/api';
import { Button, Field, fieldClass } from './ui';
import { parseToMinor, toDateString } from '../utils/money';

/**
 * Recording one movement of money.
 *
 * Three shapes behind one form, because that is what the ledger allows and
 * nothing else: income lands in an account, an expense leaves one, a transfer
 * does both and has no category. The fields rearrange rather than the rules
 * bending — the server refuses a wrong shape either way, and a form that lets
 * you build one only teaches you it is allowed.
 */

const KINDS = [
  { value: 'income', label: 'Income' },
  { value: 'expense', label: 'Expense' },
  { value: 'transfer', label: 'Transfer' },
];

export default function TransactionForm({ accounts = [], categories = [], onSaved, onCancel }) {
  const [kind, setKind] = useState('expense');
  const [amount, setAmount] = useState('');
  const [occurredOn, setOccurredOn] = useState(() => toDateString(new Date()));
  const [accountId, setAccountId] = useState('');
  const [toAccountId, setToAccountId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [note, setNote] = useState('');
  const [fee, setFee] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const live = useMemo(() => accounts.filter((a) => !a.archived), [accounts]);

  // The category list follows the kind, so an income category can never be
  // sitting selected when the form flips to an expense.
  const forKind = useMemo(
    () => categories.filter((c) => c.kind === kind),
    [categories, kind],
  );

  useEffect(() => { setCategoryId(''); }, [kind]);

  useEffect(() => {
    if (!accountId && live.length) setAccountId(String(live[0].id));
  }, [live, accountId]);

  // The currency is the account's, never a choice — otherwise a UZS row can be
  // labelled USD and every total that trusts the label is wrong.
  const currency = useMemo(() => {
    const id = kind === 'income' ? accountId : accountId;
    const found = live.find((a) => String(a.id) === String(id));
    return found?.currency || '';
  }, [live, accountId, kind]);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);

    const amountMinor = parseToMinor(amount, currency);
    if (amountMinor === null || amountMinor <= 0) {
      setError('Put in an amount.');
      return;
    }

    const body = {
      kind,
      amount_minor: amountMinor,
      occurred_on: occurredOn,
      note: note.trim() || null,
    };
    if (kind === 'expense') {
      body.from_account_id = Number(accountId) || null;
      body.category_id = categoryId ? Number(categoryId) : null;
    } else if (kind === 'income') {
      body.to_account_id = Number(accountId) || null;
      body.category_id = categoryId ? Number(categoryId) : null;
    } else {
      body.from_account_id = Number(accountId) || null;
      body.to_account_id = Number(toAccountId) || null;
      const feeMinor = fee.trim() ? parseToMinor(fee, currency) : null;
      if (feeMinor) body.fee_minor = feeMinor;
    }

    setSaving(true);
    try {
      await api.createTransaction(body);
      setAmount('');
      setNote('');
      setFee('');
      onSaved?.();
    } catch (err) {
      setError(err.message || 'That would not save.');
    } finally {
      setSaving(false);
    }
  };

  const swap = () => {
    setAccountId(toAccountId);
    setToAccountId(accountId);
  };

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="transaction-form">
      <div className="grid grid-cols-3 gap-2">
        {KINDS.map((k) => (
          <button
            key={k.value}
            type="button"
            onClick={() => setKind(k.value)}
            aria-pressed={kind === k.value}
            data-testid={`kind-${k.value}`}
            className={`rounded-chip px-3 py-2 text-[11px] font-mono font-bold uppercase tracking-widest
              transition-all ring-1 ${kind === k.value
                ? 'bg-signal-self/15 text-signal-self ring-signal-self'
                : 'bg-bat-surface text-ink-muted ring-bat-line hover:text-ink'}`}
          >
            {k.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Date">
          <input type="date" value={occurredOn} aria-label="Date"
                 onChange={(e) => setOccurredOn(e.target.value)} className={fieldClass} />
        </Field>
        <Field label={currency ? `Amount (${currency})` : 'Amount'}>
          <input
            type="text" inputMode="decimal" value={amount} aria-label="Amount"
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0" className={fieldClass}
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label={kind === 'income' ? 'Into' : kind === 'transfer' ? 'From' : 'Account'}>
          <select value={accountId} aria-label={kind === 'transfer' ? 'From' : 'Account'}
                  onChange={(e) => setAccountId(e.target.value)} className={fieldClass}>
            {live.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </Field>

        {kind === 'transfer' ? (
          <Field label="To">
            <div className="flex gap-2">
              <select value={toAccountId} aria-label="To"
                      onChange={(e) => setToAccountId(e.target.value)} className={fieldClass}>
                <option value="">—</option>
                {live.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <Button tone="ghost" size="sm" onClick={swap} aria-label="Swap from and to">⇅</Button>
            </div>
          </Field>
        ) : (
          <Field label="Category">
            <select value={categoryId} aria-label="Category"
                    onChange={(e) => setCategoryId(e.target.value)} className={fieldClass}>
              <option value="">—</option>
              {forKind.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.icon ? `${c.icon} ` : ''}{c.name}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>

      {kind === 'transfer' && (
        <Field label={`Fee${currency ? ` (${currency})` : ''}`}
               hint="What the move itself cost. It leaves the sending side.">
          <input type="text" inputMode="decimal" value={fee} aria-label="Fee"
                 onChange={(e) => setFee(e.target.value)} placeholder="0" className={fieldClass} />
        </Field>
      )}

      <Field label="Note">
        <input type="text" value={note} aria-label="Note" maxLength={200}
               onChange={(e) => setNote(e.target.value)}
               placeholder="Taxi, Orbit, Abed…" className={fieldClass} />
      </Field>

      {error && (
        <div role="alert" className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2
          text-[11px] text-signal-late">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <Button type="submit" tone="primary" size="md" disabled={saving}>
          {saving ? 'Saving' : 'Save'}
        </Button>
        {onCancel && <Button tone="ghost" size="md" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
