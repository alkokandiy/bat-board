import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import CountdownSection, { endOfWeek } from '../components/CountdownSection';
import { api } from '../utils/api.js';

vi.mock('../utils/api.js', () => ({
  api: {
    getCountdowns: vi.fn(),
    createCountdown: vi.fn(),
    deleteCountdown: vi.fn(),
  },
}));

vi.mock('../utils/migrateLocalStorage.js', () => ({
  migrateOnce: vi.fn().mockResolvedValue(undefined),
}));

const settle = async () => {
  await waitFor(() => expect(api.getCountdowns).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getCountdowns.mockResolvedValue([]);
  api.createCountdown.mockResolvedValue({ id: 1, title: 'Thesis', target_date: '2027-01-01T00:00:00Z' });
  api.deleteCountdown.mockResolvedValue({});
});

afterEach(() => vi.useRealTimers());

describe('end of week', () => {
  // `date + (7 - getDay())` pointed at NEXT Sunday when today WAS Sunday, so
  // "end of week" read as seven days away on the very day it was due.
  it('is today when today is Sunday', () => {
    const sunday = new Date(2026, 10, 8, 10, 0); // 8 Nov 2026 is a Sunday
    expect(sunday.getDay()).toBe(0);
    const end = endOfWeek(sunday);
    expect(end.getDate()).toBe(8);
    expect(end.getHours()).toBe(23);
  });

  it('is the coming Sunday from a Monday', () => {
    const monday = new Date(2026, 10, 2, 10, 0);
    expect(monday.getDay()).toBe(1);
    expect(endOfWeek(monday).getDate()).toBe(8);
  });

  it('is the coming Sunday from a Saturday', () => {
    const saturday = new Date(2026, 10, 7, 10, 0);
    expect(endOfWeek(saturday).getDate()).toBe(8);
  });
});

describe('the default tiles', () => {
  // These were coloured with `text-${color}`, which Tailwind strips from the
  // stylesheet because the whole class name is never in the source. Two of
  // the three rendered with no colour at all.
  it('colour their labels with class names that can survive the build', async () => {
    render(<CountdownSection />);
    await settle();
    for (const label of ['End of week', 'End of month', 'End of year']) {
      const el = screen.getByText(label);
      expect(el.className).not.toMatch(/text-\$\{/);
      expect(el.className).toMatch(/text-signal-(self|work|warn|late)/);
    }
  });
});

describe('a personal goal', () => {
  it('can be added, and names its own delete', async () => {
    api.getCountdowns.mockResolvedValue([]);
    render(<CountdownSection />);
    await settle();

    fireEvent.change(screen.getByLabelText('What for'), { target: { value: 'Thesis' } });
    fireEvent.change(screen.getByLabelText('When'), { target: { value: '2027-01-01T09:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(api.createCountdown).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: 'Delete "Thesis"' })).toBeTruthy();
  });

  // Adding used to swallow the failure whole: you typed it, pressed Add, and
  // nothing happened and nothing was said.
  it('says so when it could not be saved', async () => {
    api.createCountdown.mockRejectedValue(new Error('Backend unreachable'));
    render(<CountdownSection />);
    await settle();

    fireEvent.change(screen.getByLabelText('What for'), { target: { value: 'Thesis' } });
    fireEvent.change(screen.getByLabelText('When'), { target: { value: '2027-01-01T09:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(await screen.findByText('Backend unreachable')).toBeTruthy();
  });

  it('is removed on delete', async () => {
    api.getCountdowns.mockResolvedValue([
      { id: 7, title: 'Thesis', target_date: '2027-01-01T00:00:00Z' },
    ]);
    render(<CountdownSection />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Thesis"' }));
    await waitFor(() => expect(api.deleteCountdown).toHaveBeenCalledWith(7));
    expect(screen.queryByText('Thesis')).toBeNull();
  });

  it('says "done" once the date has passed, and offers to clear it', async () => {
    api.getCountdowns.mockResolvedValue([
      { id: 8, title: 'Last year', target_date: '2020-01-01T00:00:00Z' },
    ]);
    render(<CountdownSection />);
    await settle();
    expect(screen.getByText('Done')).toBeTruthy();
    expect(screen.getByRole('button', { name: /clear it/i })).toBeTruthy();
  });

  it('does not shout an empty state in capitals', async () => {
    render(<CountdownSection />);
    await settle();
    expect(screen.getByText('Nothing of your own counting down')).toBeTruthy();
    expect(screen.queryByText(/NO PERSONAL GOALS CONFIGURED/)).toBeNull();
  });
});

describe('the clock', () => {
  // Thirteen tiles meant thirteen setIntervals, each re-rendering alone.
  it('ticks once for the whole screen', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const spy = vi.spyOn(globalThis, 'setInterval');
    api.getCountdowns.mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => ({
        id: i + 1, title: `Goal ${i + 1}`, target_date: '2027-01-01T00:00:00Z',
      })));
    render(<CountdownSection />);
    await settle();
    // Three defaults plus six goals, and one timer between them.
    expect(spy.mock.calls.filter(([, ms]) => ms === 1000).length).toBe(1);
    spy.mockRestore();
  });
});
