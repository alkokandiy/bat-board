import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import HabitDetailPanel from '../components/HabitDetailPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getHabitHistory: vi.fn(),
  },
}));

const currentMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

const buildDays = (month, states = {}) => {
  const [year, m] = month.split('-').map(Number);
  const total = new Date(year, m, 0).getDate();
  return Array.from({ length: total }, (_, i) => {
    const date = `${month}-${String(i + 1).padStart(2, '0')}`;
    const state = states[date] || 'not_due';
    return { date, state, count: state === 'done' ? 1 : 0 };
  });
};

const history = (over = {}) => ({
  habit_id: 3,
  name: '1 hour of thm training',
  month: '2026-11',
  days: buildDays('2026-11'),
  due_so_far: 12,
  done_this_month: 9,
  rested_this_month: 2,
  missed_this_month: 3,
  check_in_rate: 75,
  total_check_ins: 41,
  streak: 4,
  best_streak: 11,
  ...over,
});

const renderPanel = (over = {}, props = {}) => {
  api.getHabitHistory.mockResolvedValue(history(over));
  const onClose = vi.fn();
  render(<HabitDetailPanel habitId={3} habitName="1 hour of thm training" onClose={onClose} {...props} />);
  return { onClose };
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getHabitHistory.mockResolvedValue(history());
});

describe('the month grid', () => {
  it('puts the first of the month under its real weekday, not the first column', async () => {
    renderPanel();
    const first = await screen.findByTestId('habit-day-2026-11-01');
    const column = Array.from(first.parentElement.children).indexOf(first);
    // 1 November 2026 is a Sunday, so it sits in the seventh Monday-first column.
    expect(column).toBe(6);
  });
});

describe('the five day states', () => {
  it('renders each state with its own marker so none can be confused', async () => {
    renderPanel({
      days: buildDays('2026-11', {
        '2026-11-01': 'done',
        '2026-11-02': 'rested',
        '2026-11-03': 'missed',
        '2026-11-04': 'not_due',
        '2026-11-05': 'upcoming',
      }),
    });

    expect((await screen.findByTestId('habit-day-2026-11-01')).getAttribute('data-state')).toBe('done');
    expect(screen.getByTestId('habit-day-2026-11-02').getAttribute('data-state')).toBe('rested');
    expect(screen.getByTestId('habit-day-2026-11-03').getAttribute('data-state')).toBe('missed');
    expect(screen.getByTestId('habit-day-2026-11-04').getAttribute('data-state')).toBe('not_due');
    expect(screen.getByTestId('habit-day-2026-11-05').getAttribute('data-state')).toBe('upcoming');
  });

  it('shows a rest as neutral, never as a failure or a miss', async () => {
    renderPanel({ days: buildDays('2026-11', { '2026-11-02': 'rested' }) });

    const rested = await screen.findByTestId('habit-day-2026-11-02');
    expect(rested.className).not.toMatch(/signal-late/);
    expect(rested.className).not.toMatch(/signal-self/);
    expect(rested.textContent).not.toMatch(/miss|fail|skip/i);
  });

  it('keeps a missed day visually distinct from a rest', async () => {
    renderPanel({
      days: buildDays('2026-11', {
        '2026-11-02': 'rested',
        '2026-11-03': 'missed',
      }),
    });

    const rested = await screen.findByTestId('habit-day-2026-11-02');
    const missed = screen.getByTestId('habit-day-2026-11-03');
    expect(rested.className).not.toBe(missed.className);
    expect(missed.className).toMatch(/signal-late/);
  });

  it('names all five states in the legend', async () => {
    renderPanel();
    const legend = await screen.findByTestId('habit-legend');
    for (const label of ['Done', 'Rested', 'Missed', 'Not due', 'Upcoming']) {
      expect(legend.textContent).toContain(label);
    }
  });
});

describe('the figures', () => {
  it('renders a missing check-in rate as a dash, never as zero percent', async () => {
    renderPanel({ check_in_rate: null });
    expect(await screen.findByText('—')).toBeTruthy();
    expect(screen.queryByText('0%')).toBeNull();
  });

  it('shows the rate when the server has one', async () => {
    renderPanel({ check_in_rate: 75 });
    expect(await screen.findByText('75%')).toBeTruthy();
  });

  it('shows the month figures it was given', async () => {
    renderPanel({ done_this_month: 9, streak: 4, best_streak: 11, total_check_ins: 41 });
    const figures = await screen.findByTestId('habit-figures');
    expect(within(figures).getByText('9')).toBeTruthy();
    expect(within(figures).getByText('4')).toBeTruthy();
    expect(within(figures).getByText('11')).toBeTruthy();
    expect(within(figures).getByText('41')).toBeTruthy();
  });
});

describe('month navigation', () => {
  it('cannot page forward past the current month', async () => {
    renderPanel();
    await waitFor(() => expect(api.getHabitHistory).toHaveBeenCalled());
    const callsAfterLoad = api.getHabitHistory.mock.calls.length;

    const next = screen.getByRole('button', { name: 'Next month' });
    expect(next).toBeDisabled();

    fireEvent.click(next);
    await waitFor(() => expect(api.getHabitHistory).toHaveBeenCalledTimes(callsAfterLoad));
  });

  it('refetches when moving to the previous month', async () => {
    renderPanel();
    await waitFor(() => expect(api.getHabitHistory).toHaveBeenCalledWith(3, currentMonth()));

    fireEvent.click(screen.getByRole('button', { name: 'Previous month' }));
    await waitFor(() => expect(api.getHabitHistory).toHaveBeenCalledTimes(2));
    expect(api.getHabitHistory.mock.calls[1][0]).toBe(3);
    expect(api.getHabitHistory.mock.calls[1][1]).not.toBe(currentMonth());
  });
});

describe('when the record cannot be loaded', () => {
  it('shows a message instead of an empty box', async () => {
    api.getHabitHistory.mockRejectedValue(new Error('history unavailable'));
    render(<HabitDetailPanel habitId={3} habitName="1 hour of thm training" onClose={vi.fn()} />);

    expect(await screen.findByText('history unavailable')).toBeTruthy();
  });
});

describe('closing the panel', () => {
  it('calls onClose', () => {
    const { onClose } = renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Close habit history' }));
    expect(onClose).toHaveBeenCalled();
  });
});
