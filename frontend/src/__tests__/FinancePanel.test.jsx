import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import FinancePanel from '../components/FinancePanel';
import TransactionForm from '../components/TransactionForm';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getFinanceSettings: vi.fn(),
    getFinanceAccounts: vi.fn(),
    getFinanceCategories: vi.fn(),
    getLedger: vi.fn(),
    createTransaction: vi.fn(),
    deleteTransaction: vi.fn(),
  },
}));

const CASH = { id: 1, name: 'Cash', group: 'cash', currency: 'UZS', balance_minor: 3000000, archived: false };
const CARD = { id: 2, name: 'Card', group: 'card', currency: 'UZS', balance_minor: -200000, archived: false };
const CATEGORIES = [
  { id: 10, name: 'Food', kind: 'expense', icon: '🍜', parent_id: null },
  { id: 11, name: 'Lunch', kind: 'expense', icon: null, parent_id: 10 },
  { id: 20, name: 'Salary', kind: 'income', icon: null, parent_id: null },
];

const txn = (over = {}) => ({
  id: 1, kind: 'expense', occurred_on: '2026-11-18', amount_minor: 600000,
  currency: 'UZS', rate_to_main: 1, fee_minor: null,
  from_account_id: 1, to_account_id: null, category_id: 10,
  note: 'Orbit', description: null, created_at: '2026-11-18T10:00:00Z',
  from_account_name: 'Cash', to_account_name: null,
  category_name: 'Food', category_icon: '🍜', parent_category_name: null,
  ...over,
});

const ledger = (transactions, totals) => ({
  start: '2026-11-01', end: '2026-11-30', main_currency: 'UZS',
  totals: totals || { income_minor: 0, expense_minor: 0, net_minor: 0 },
  transactions,
});

beforeEach(() => {
  vi.clearAllMocks();
  api.getFinanceSettings.mockResolvedValue({
    finance_enabled: true, main_currency: 'UZS', period_start_day: 1,
  });
  api.getFinanceAccounts.mockResolvedValue([CASH, CARD]);
  api.getFinanceCategories.mockResolvedValue(CATEGORIES);
  api.getLedger.mockResolvedValue(ledger([txn()], {
    income_minor: 101850000, expense_minor: 136050000, net_minor: -34200000,
  }));
});

// testing-library normalises the thin thousands separator to a plain space, so
// queries here use plain spaces. The exact separator is pinned in money.test.js.
describe('the three figures at the top', () => {
  it('shows income, expense and the net for the window', async () => {
    render(<FinancePanel />);
    const totals = await screen.findByTestId('finance-totals');
    expect(within(totals).getByText('1 018 500,00')).toBeTruthy();
    expect(within(totals).getByText('1 360 500,00')).toBeTruthy();
    expect(within(totals).getByText('-342 000,00')).toBeTruthy();
  });

  it('renders a negative net as negative, never as a bare number', async () => {
    render(<FinancePanel />);
    const totals = await screen.findByTestId('finance-totals');
    expect(within(totals).getByText(/^-/)).toBeTruthy();
  });
});

describe('the daily record', () => {
  it('groups rows under the day they happened on', async () => {
    render(<FinancePanel />);
    expect(await screen.findByTestId('finance-day-2026-11-18')).toBeTruthy();
  });

  it('shows a transfer as an account-to-account move, not as spending', async () => {
    api.getLedger.mockResolvedValue(ledger([
      txn({ id: 5, kind: 'transfer', amount_minor: 31000000, category_id: null,
            category_name: null, category_icon: null, note: null,
            from_account_id: 1, to_account_id: 2,
            from_account_name: 'Cash', to_account_name: 'Card' }),
    ]));
    render(<FinancePanel />);
    const row = await screen.findByTestId('finance-row-5');
    expect(row.getAttribute('data-kind')).toBe('transfer');
    expect(row.textContent).toContain('Cash → Card');
  });

  it('shows a subcategory under its parent', async () => {
    api.getLedger.mockResolvedValue(ledger([
      txn({ id: 7, category_id: 11, category_name: 'Lunch',
            parent_category_name: 'Food', category_icon: '🍜', note: 'Somsa' }),
    ]));
    render(<FinancePanel />);
    const row = await screen.findByTestId('finance-row-7');
    expect(row.textContent).toContain('Food');
    expect(row.textContent).toContain('Lunch');
  });

  it('says so plainly when the month is empty', async () => {
    api.getLedger.mockResolvedValue(ledger([]));
    render(<FinancePanel />);
    expect(await screen.findByText(/Nothing recorded this month/i)).toBeTruthy();
  });
});

describe('moving between months', () => {
  it('refetches the ledger for the new window', async () => {
    render(<FinancePanel />);
    await waitFor(() => expect(api.getLedger).toHaveBeenCalledTimes(1));
    const first = api.getLedger.mock.calls[0][0];

    fireEvent.click(screen.getByRole('button', { name: 'Previous month' }));
    await waitFor(() => expect(api.getLedger).toHaveBeenCalledTimes(2));
    expect(api.getLedger.mock.calls[1][0]).not.toBe(first);
  });
});

describe('the calendar', () => {
  it('leaves transfers out of a day cell', async () => {
    api.getLedger.mockResolvedValue(ledger([
      txn({ id: 9, kind: 'transfer', amount_minor: 31000000, category_id: null,
            from_account_id: 1, to_account_id: 2 }),
    ]));
    render(<FinancePanel />);
    fireEvent.click(await screen.findByTestId('finance-view-calendar'));
    const cell = await screen.findByTestId('finance-cal-2026-11-18');
    // Only the day number — a shuffle between your own pockets is not a figure.
    expect(cell.textContent.trim()).toBe('18');
  });

  it('puts the first day under its real weekday', async () => {
    render(<FinancePanel />);
    fireEvent.click(await screen.findByTestId('finance-view-calendar'));
    const first = await screen.findByTestId('finance-cal-2026-11-01');
    const column = Array.from(first.parentElement.children).indexOf(first);
    // 1 November 2026 is a Sunday: the seventh Monday-first column.
    expect(column).toBe(6);
  });
});

describe('the summary', () => {
  it('counts a card debt against net worth rather than toward it', async () => {
    render(<FinancePanel />);
    fireEvent.click(await screen.findByTestId('finance-view-summary'));
    const networth = await screen.findByTestId('finance-networth');
    // Cash 30 000,00 asset; card owes 2 000,00 → net 28 000,00.
    expect(within(networth).getByText('30 000,00')).toBeTruthy();
    expect(within(networth).getByText('2 000,00')).toBeTruthy();
    expect(within(networth).getByText('28 000,00')).toBeTruthy();
  });

  it('breaks spending down by category with a share', async () => {
    api.getLedger.mockResolvedValue(ledger([
      txn({ id: 1, amount_minor: 75000, category_name: 'Food', parent_category_name: null }),
      txn({ id: 2, amount_minor: 25000, category_name: 'Tech',
            parent_category_name: null, category_icon: '💻' }),
    ]));
    render(<FinancePanel />);
    fireEvent.click(await screen.findByTestId('finance-view-summary'));
    const breakdown = await screen.findByTestId('finance-by-category');
    expect(within(breakdown).getByText('75%')).toBeTruthy();
    expect(within(breakdown).getByText('25%')).toBeTruthy();
  });
});

describe('when there is nothing set up yet', () => {
  it('offers to set up an account instead of showing an empty ledger', async () => {
    api.getFinanceAccounts.mockResolvedValue([]);
    api.getLedger.mockResolvedValue(ledger([]));
    render(<FinancePanel />);
    expect(await screen.findByText(/add where your money sits/i)).toBeTruthy();
  });
});

describe('the transaction form', () => {
  const renderForm = (props = {}) => {
    const onSaved = vi.fn();
    render(<TransactionForm accounts={[CASH, CARD]} categories={CATEGORIES}
                            onSaved={onSaved} {...props} />);
    return { onSaved };
  };

  it('sends an expense out of an account, never into one', async () => {
    api.createTransaction.mockResolvedValue({});
    const { onSaved } = renderForm();

    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '6000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.createTransaction).toHaveBeenCalled());
    const body = api.createTransaction.mock.calls[0][0];
    expect(body.kind).toBe('expense');
    expect(body.from_account_id).toBe(1);
    expect(body.to_account_id).toBeUndefined();
    expect(onSaved).toHaveBeenCalled();
  });

  it('sends income into an account, never out of one', async () => {
    api.createTransaction.mockResolvedValue({});
    renderForm();

    fireEvent.click(screen.getByTestId('kind-income'));
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '17350' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.createTransaction).toHaveBeenCalled());
    const body = api.createTransaction.mock.calls[0][0];
    expect(body.kind).toBe('income');
    expect(body.to_account_id).toBe(1);
    expect(body.from_account_id).toBeUndefined();
  });

  it('offers no category at all on a transfer', async () => {
    renderForm();
    expect(screen.getByLabelText('Category')).toBeTruthy();
    fireEvent.click(screen.getByTestId('kind-transfer'));
    expect(screen.queryByLabelText('Category')).toBeNull();
  });

  it('converts what was typed into minor units', async () => {
    api.createTransaction.mockResolvedValue({});
    renderForm();
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '45' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.createTransaction).toHaveBeenCalled());
    expect(api.createTransaction.mock.calls[0][0].amount_minor).toBe(4500);
  });

  it('refuses to send an empty amount rather than booking zero', async () => {
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(api.createTransaction).not.toHaveBeenCalled();
  });

  it('shows the server refusal rather than failing silently', async () => {
    api.createTransaction.mockRejectedValue(new Error('A transfer has to go somewhere else'));
    renderForm();
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('A transfer has to go somewhere else')).toBeTruthy();
  });

  it('drops a chosen category when the kind changes, so a wrong pairing cannot be sent', async () => {
    api.createTransaction.mockResolvedValue({});
    renderForm();

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('kind-income'));
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.createTransaction).toHaveBeenCalled());
    expect(api.createTransaction.mock.calls[0][0].category_id).toBeNull();
  });
});
