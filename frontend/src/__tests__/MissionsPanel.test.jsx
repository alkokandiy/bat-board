import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MissionsPanel, { blankMission, byWhatIsDueFirst, currentWeek } from '../components/MissionsPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    createMission: vi.fn(),
    updateMission: vi.fn(),
    deleteMission: vi.fn(),
    logPastFocus: vi.fn(),
  },
}));

const mission = (over = {}) => ({
  id: 1,
  title: 'Finish the report',
  description: null,
  priority: 'high',
  status: 'pending',
  due_date: null,
  tags: null,
  location: null,
  notes: null,
  subtasks: null,
  is_pinned: false,
  is_dismissed: false,
  focus_minutes: 0,
  completed_focus_sessions: 0,
  ...over,
});

const renderPanel = (missions) => {
  const onRefreshMissions = vi.fn().mockResolvedValue(undefined);
  const onRefreshAccount = vi.fn().mockResolvedValue(undefined);
  render(
    <MissionsPanel
      missions={missions}
      onRefreshMissions={onRefreshMissions}
      onRefreshAccount={onRefreshAccount}
    />,
  );
  return { onRefreshMissions, onRefreshAccount };
};

describe('a mission row can be operated without guessing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.updateMission.mockResolvedValue({});
    api.createMission.mockResolvedValue({});
    api.deleteMission.mockResolvedValue({});
    api.logPastFocus.mockResolvedValue({});
  });

  // These four controls were glyph buttons with only a `title`: the
  // accessibility tree showed four unnamed buttons, so neither a screen
  // reader nor a test could tell them apart.
  it('names every action after the mission it acts on', () => {
    renderPanel([mission()]);
    for (const name of [
      /^Complete "Finish the report"$/,
      /^Edit "Finish the report"$/,
      /^Duplicate "Finish the report"$/,
      /^Won't do "Finish the report"$/,
      /^Delete "Finish the report"$/,
    ]) {
      expect(screen.getByRole('button', { name })).toBeTruthy();
    }
  });

  it('completes through the tick, and says so', async () => {
    renderPanel([mission()]);
    fireEvent.click(screen.getByRole('button', { name: /^Complete "Finish the report"$/ }));
    await waitFor(() => expect(api.updateMission).toHaveBeenCalledWith(1, { status: 'completed' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Done — "Finish the report"');
  });

  it('offers to reopen, not to complete again, once it is done', () => {
    renderPanel([mission({ status: 'completed' })]);
    fireEvent.click(screen.getByText(/^Done \(1\)$/));
    expect(screen.getByRole('button', { name: /^Reopen "Finish the report"$/ })).toBeTruthy();
  });
});

describe('the mission form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.createMission.mockResolvedValue({});
  });

  it('takes a step as typed text and stores it as JSON', async () => {
    renderPanel([]);
    fireEvent.click(screen.getByRole('button', { name: /New mission/i }));

    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Pack' } });
    const step = screen.getByLabelText('New subtask');
    fireEvent.change(step, { target: { value: 'Charge the batteries' } });
    // Enter adds the step; it must not submit the mission.
    fireEvent.keyDown(step, { key: 'Enter' });
    expect(api.createMission).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Add mission/i }));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
    expect(api.createMission.mock.calls.at(-1)[0].subtasks)
      .toBe('[{"title":"Charge the batteries","done":false}]');
  });

  it('acknowledges the save, which it previously did not', async () => {
    renderPanel([]);
    fireEvent.click(screen.getByRole('button', { name: /New mission/i }));
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Call the bank' } });
    fireEvent.click(screen.getByRole('button', { name: /Add mission/i }));
    expect(await screen.findByRole('status')).toHaveTextContent('Added "Call the bank"');
  });

  it('closes on Escape', async () => {
    renderPanel([]);
    fireEvent.click(screen.getByRole('button', { name: /New mission/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('does not reopen a completed mission on edit', async () => {
    renderPanel([mission({ status: 'completed' })]);
    fireEvent.click(screen.getByText(/^Done \(1\)$/));
    fireEvent.click(screen.getByRole('button', { name: /^Edit "Finish the report"$/ }));
    fireEvent.click(screen.getByRole('button', { name: /Save changes/i }));
    await waitFor(() => expect(api.updateMission).toHaveBeenCalled());
    expect(api.updateMission.mock.calls[0][1]).not.toHaveProperty('status');
  });
});

describe('the due filter', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hides undated missions when asked for today', () => {
    const today = new Date();
    const key = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    renderPanel([
      mission({ id: 1, title: 'Due today', due_date: `${key}T00:00:00Z` }),
      mission({ id: 2, title: 'No date' }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Today' }));
    expect(screen.getByText('Due today')).toBeTruthy();
    expect(screen.queryByText('No date')).toBeNull();
  });
});


describe('logging time without a timer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.logPastFocus.mockResolvedValue({});
    api.updateMission.mockResolvedValue({});
  });

  // "I was just working." A record that only exists if you remember to start
  // a clock beforehand is empty on exactly the days with most work in them.
  it('offers the common lengths on the row, each named', () => {
    renderPanel([mission()]);
    for (const [label, mins] of [['+15m', 15], ['+30m', 30], ['+1h', 60]]) {
      const btn = screen.getByRole('button', { name: `Log ${mins} minutes on "Finish the report"` });
      expect(btn.textContent).toBe(label);
    }
  });

  it('writes a backfilled block against that mission', async () => {
    renderPanel([mission()]);
    fireEvent.click(screen.getByRole('button', { name: /Log 30 minutes/ }));
    await waitFor(() => expect(api.logPastFocus).toHaveBeenCalledWith({ minutes: 30, mission_id: 1 }));
    expect(await screen.findByRole('status')).toHaveTextContent('Logged 30m');
  });

  it('says so when the backend refuses, rather than silently doing nothing', async () => {
    api.logPastFocus.mockRejectedValue(new Error('Blocks may not overlap.'));
    renderPanel([mission()]);
    fireEvent.click(screen.getByRole('button', { name: /Log 15 minutes/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('Blocks may not overlap.');
  });

  it('does not offer it on something already finished', () => {
    renderPanel([mission({ status: 'completed' })]);
    fireEvent.click(screen.getByText(/^Done \(1\)$/));
    expect(screen.queryByRole('button', { name: /Log 30 minutes/ })).toBeNull();
  });
});

describe('Focus on this', () => {
  const withFocus = (missions, props = {}) => {
    const onFocusOn = vi.fn();
    render(
      <MissionsPanel
        missions={missions}
        onRefreshMissions={vi.fn().mockResolvedValue(undefined)}
        onRefreshAccount={vi.fn().mockResolvedValue(undefined)}
        onFocusOn={onFocusOn}
        {...props}
      />,
    );
    return { onFocusOn };
  };

  it('offers it on an open mission', () => {
    withFocus([mission()]);
    expect(screen.getByRole('button', { name: /focus on "finish the report"/i }))
      .toBeInTheDocument();
  });

  it('hands back the mission id', () => {
    const { onFocusOn } = withFocus([mission({ id: 42 })]);
    fireEvent.click(screen.getByRole('button', { name: /focus on/i }));
    expect(onFocusOn).toHaveBeenCalledWith(42);
  });

  it('does not offer it on something already finished', () => {
    withFocus([mission({ status: 'completed' })]);
    expect(screen.queryByRole('button', { name: /focus on/i })).not.toBeInTheDocument();
  });

  it('is absent entirely when nothing is wired to it', () => {
    renderPanel([mission()]);
    expect(screen.queryByRole('button', { name: /focus on/i })).not.toBeInTheDocument();
  });
});

describe('The week is Monday to Sunday, and says so', () => {
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T00:00:00Z`;

  // Anchored to the real current week, so the test means the same thing
  // whatever day it is run on.
  const { start: monday, end: sunday, label } = currentWeek();
  const dayOfWeek = (n) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + n);
    return iso(d);
  };
  const outside = (offsetFromMonday) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + offsetFromMonday);
    return iso(d);
  };

  const board = () => [
    mission({ id: 1, title: 'Last month', due_date: outside(-30) }),
    mission({ id: 2, title: 'Sunday just gone', due_date: outside(-1) }),
    mission({ id: 3, title: 'This Monday', due_date: dayOfWeek(0) }),
    mission({ id: 4, title: 'This Sunday', due_date: dayOfWeek(6) }),
    mission({ id: 5, title: 'Next Monday', due_date: outside(7) }),
    mission({ id: 6, title: 'No date at all', due_date: null }),
  ];

  const pickWeek = () => {
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: label }));
  };

  it('says the word and the dates', () => {
    renderPanel([]);
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    expect(label).toMatch(/^This week · /);
    expect(label).toMatch(/\d+–\d+$|\d+ \w{3}–\d+ \w{3}$/);
  });

  it('starts on Monday and ends on Sunday', () => {
    expect(monday.getDay()).toBe(1);
    expect(sunday.getDay()).toBe(0);
  });

  it('includes the whole week, both ends', () => {
    pickWeek();
    expect(screen.getByText('This Monday')).toBeInTheDocument();
    expect(screen.getByText('This Sunday')).toBeInTheDocument();
  });

  it('a mission that slipped earlier THIS week is still in it', () => {
    // Which was the original complaint: Friday showing nothing while
    // Monday's work sat there undone.
    pickWeek();
    expect(screen.getByText('This Monday')).toBeInTheDocument();
  });

  it('does not reach into last week or next', () => {
    pickWeek();
    expect(screen.queryByText('Sunday just gone')).not.toBeInTheDocument();
    expect(screen.queryByText('Next Monday')).not.toBeInTheDocument();
    expect(screen.queryByText('Last month')).not.toBeInTheDocument();
  });

  it('a mission with no date is not in it', () => {
    pickWeek();
    expect(screen.queryByText('No date at all')).not.toBeInTheDocument();
  });

  it('today means today, and nothing else', () => {
    // It briefly meant "today or anything already late", which filed a
    // mission from the 15th of October under a button marked Today.
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: /^today$/i }));
    expect(screen.queryByText('Last month')).not.toBeInTheDocument();
    expect(screen.queryByText('Sunday just gone')).not.toBeInTheDocument();
    expect(screen.queryByText('This Sunday')).not.toBeInTheDocument();
  });

  it('overdue has its own button, carrying the count', () => {
    renderPanel(board());
    const chip = screen.getByRole('button', { name: /^overdue · \d+$/i });
    fireEvent.click(chip);
    expect(screen.getByText('Last month')).toBeInTheDocument();
    expect(screen.getByText('Sunday just gone')).toBeInTheDocument();
  });

  it('overdue shows only what is actually late', () => {
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: /^overdue · \d+$/i }));
    expect(screen.queryByText('This Sunday')).not.toBeInTheDocument();
    expect(screen.queryByText('Next Monday')).not.toBeInTheDocument();
    expect(screen.queryByText('No date at all')).not.toBeInTheDocument();
  });

  it('something due today is not overdue', () => {
    // The boundary: `<` not `<=`. Nothing in the shared board is due
    // today, so without this the off-by-one goes unnoticed.
    const at = (offset) => {
      const x = new Date();
      x.setDate(x.getDate() + offset);
      return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}T00:00:00Z`;
    };
    renderPanel([
      mission({ id: 1, title: 'Due today', due_date: at(0) }),
      mission({ id: 2, title: 'Due yesterday', due_date: at(-1) }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: /^overdue · 1$/i }));
    expect(screen.getByText('Due yesterday')).toBeInTheDocument();
    expect(screen.queryByText('Due today')).not.toBeInTheDocument();
  });

  it('no overdue button when nothing is late', () => {
    renderPanel([mission({ id: 1, title: 'Someday', due_date: null })]);
    expect(screen.queryByRole('button', { name: /^overdue/i })).not.toBeInTheDocument();
  });

  it('says which window is empty, not just "nothing"', () => {
    renderPanel([mission({ id: 1, title: 'Someday', due_date: null })]);
    fireEvent.click(screen.getByRole('button', { name: /^today$/i }));
    expect(screen.getByText(/nothing due today/i)).toBeInTheDocument();
  });

  it('all still means all', () => {
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: /^all$/i }));
    expect(screen.getByText('No date at all')).toBeInTheDocument();
    expect(screen.getByText('Next Monday')).toBeInTheDocument();
  });
});

describe('The dates are worked out, never fixed', () => {
  // The whole point of the label: it has to follow the calendar, not sit
  // on whatever week it was written in.
  it.each([
    ['2026-11-13', 'This week · 9–15'],         // Friday
    ['2026-11-16', 'This week · 16–22'],        // the Monday after
    ['2026-11-23', 'This week · 23–29'],
    ['2026-11-30', 'This week · 30 Nov–6 Dec'], // over a month end
    ['2026-12-28', 'This week · 28 Dec–3 Jan'], // over a year end
    ['2027-01-04', 'This week · 4–10'],
  ])('%s reads "%s"', (day, expected) => {
    const [y, m, d] = day.split('-').map(Number);
    expect(currentWeek(new Date(y, m - 1, d)).label).toBe(expected);
  });

  it('bare days within one month, both months when it straddles', () => {
    expect(currentWeek(new Date(2026, 10, 13)).range).toBe('9–15');
    expect(currentWeek(new Date(2026, 10, 30)).range).toBe('30 Nov–6 Dec');
  });

  it('a Sunday belongs to the week it ends, not the one it precedes', () => {
    const { startKey, endKey } = currentWeek(new Date(2026, 10, 15));  // Sun 15 Nov
    expect(startKey).toBe('2026-11-09');
    expect(endKey).toBe('2026-11-15');
  });

  it('a Monday is the first day of its own week', () => {
    const { startKey, endKey } = currentWeek(new Date(2026, 10, 9));   // Mon 9 Nov
    expect(startKey).toBe('2026-11-09');
    expect(endKey).toBe('2026-11-15');
  });
});

describe('The order of the list', () => {
  const d = (offset) => {
    const x = new Date();
    x.setDate(x.getDate() + offset);
    return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}T00:00:00Z`;
  };
  const m = (over) => mission({ priority: 'medium', ...over });
  const order = (list) => [...list].sort(byWhatIsDueFirst).map((x) => x.title);

  it('puts what is late above what is merely important', () => {
    // The screenshot: a HIGH with no date sat first, and a MEDIUM that was
    // a month overdue sat third. Late beats a label.
    expect(order([
      m({ id: 1, title: 'High, no date', priority: 'high' }),
      m({ id: 2, title: 'Overdue', due_date: d(-30) }),
    ])).toEqual(['Overdue', 'High, no date']);
  });

  it('orders dated missions soonest first', () => {
    expect(order([
      m({ id: 1, title: 'Next week', due_date: d(7) }),
      m({ id: 2, title: 'Overdue', due_date: d(-3) }),
      m({ id: 3, title: 'Tomorrow', due_date: d(1) }),
      m({ id: 4, title: 'Today', due_date: d(0) }),
    ])).toEqual(['Overdue', 'Today', 'Tomorrow', 'Next week']);
  });

  it('sinks everything undated below everything dated', () => {
    expect(order([
      m({ id: 1, title: 'Critical someday', priority: 'critical' }),
      m({ id: 2, title: 'Low, due next year', priority: 'low', due_date: d(300) }),
    ])).toEqual(['Low, due next year', 'Critical someday']);
  });

  it('uses priority to break a tie on the same day', () => {
    expect(order([
      m({ id: 1, title: 'Low today', priority: 'low', due_date: d(0) }),
      m({ id: 2, title: 'Critical today', priority: 'critical', due_date: d(0) }),
      m({ id: 3, title: 'Medium today', priority: 'medium', due_date: d(0) }),
    ])).toEqual(['Critical today', 'Medium today', 'Low today']);
  });

  it('orders the undated pile by priority too', () => {
    expect(order([
      m({ id: 1, title: 'Low', priority: 'low' }),
      m({ id: 2, title: 'High', priority: 'high' }),
    ])).toEqual(['High', 'Low']);
  });

  it('falls back to newest, so the order never wobbles', () => {
    expect(order([
      m({ id: 1, title: 'Older' }),
      m({ id: 2, title: 'Newer' }),
    ])).toEqual(['Newer', 'Older']);
  });

  it('a pin outranks everything, including something overdue', () => {
    expect(order([
      m({ id: 1, title: 'Overdue', due_date: d(-30) }),
      m({ id: 2, title: 'Pinned, no date', is_pinned: true }),
    ])).toEqual(['Pinned, no date', 'Overdue']);
  });

  it('and the pins are themselves in due order', () => {
    expect(order([
      m({ id: 1, title: 'Pinned, later', is_pinned: true, due_date: d(5) }),
      m({ id: 2, title: 'Pinned, overdue', is_pinned: true, due_date: d(-5) }),
    ])).toEqual(['Pinned, overdue', 'Pinned, later']);
  });

  it('says what the order is, on the panel', () => {
    renderPanel([m({ id: 1, title: 'Anything' })]);
    expect(screen.getByText(/soonest first/i)).toBeInTheDocument();
  });

  it('renders the whole board in that order', () => {
    renderPanel([
      m({ id: 1, title: 'High no date', priority: 'high' }),
      m({ id: 2, title: 'Overdue medium', due_date: d(-10) }),
      m({ id: 3, title: 'Due today', due_date: d(0) }),
    ]);
    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(titles.slice(0, 3)).toEqual(['Overdue medium', 'Due today', 'High no date']);
  });
});

describe('A new mission starts dated today', () => {
  // This suite's clearAllMocks lives in another describe, so these would
  // otherwise read calls recorded by earlier tests.
  beforeEach(() => vi.clearAllMocks());

  const todayKey = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  // The LAST one in the document: this suite renders repeatedly without
  // auto-cleanup, so an earlier test's form is still in the body and a
  // plain querySelector returns that one instead.
  const dueInput = () => {
    const all = document.querySelectorAll('input[type="date"]');
    return all[all.length - 1];
  };

  const openNew = () => {
    renderPanel([]);
    fireEvent.click(screen.getByRole('button', { name: /new mission/i }));
  };

  it('prefills Due with today', () => {
    // Like priority defaults to medium. A field left empty by default is a
    // field usually left empty — 31 of 44 missions had no date at all.
    openNew();
    expect(dueInput().value).toBe(todayKey());
  });

  it('saves that date without the user touching it', async () => {
    api.createMission.mockResolvedValue({});
    openNew();
    fireEvent.change(screen.getByLabelText(/what is it/i), { target: { value: 'Pay the invoice' } });
    fireEvent.click(screen.getByRole('button', { name: /^add mission$/i }));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
    expect(api.createMission.mock.calls.at(-1)[0].due_date).toBe(`${todayKey()}T00:00:00Z`);
  });

  it('can still be cleared, for a mission with no date', async () => {
    api.createMission.mockResolvedValue({});
    openNew();
    fireEvent.change(screen.getByLabelText(/what is it/i), { target: { value: 'Someday' } });
    fireEvent.change(dueInput(), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^add mission$/i }));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
    expect(api.createMission.mock.calls.at(-1)[0].due_date).toBeNull();
  });

  it('and can be changed before saving', async () => {
    api.createMission.mockResolvedValue({});
    openNew();
    fireEvent.change(screen.getByLabelText(/what is it/i), { target: { value: 'Later' } });
    fireEvent.change(dueInput(), { target: { value: '2027-03-01' } });
    fireEvent.click(screen.getByRole('button', { name: /^add mission$/i }));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
    expect(api.createMission.mock.calls.at(-1)[0].due_date).toBe('2027-03-01T00:00:00Z');
  });

  it('EDITING an undated mission does not quietly date it', () => {
    // The default belongs to new missions only. Opening an old undated one
    // and pressing save must not silently give it today.
    renderPanel([mission({ id: 5, title: 'No date', due_date: null })]);
    fireEvent.click(screen.getByRole('button', { name: /edit "no date"/i }));
    expect(dueInput().value).toBe('');
  });

  it('editing a dated mission still shows its own date', () => {
    renderPanel([mission({ id: 6, title: 'Dated', due_date: '2026-12-25T00:00:00Z' })]);
    fireEvent.click(screen.getByRole('button', { name: /edit "dated"/i }));
    expect(dueInput().value).toBe('2026-12-25');
  });

  it('the default is today, not a fixed day', () => {
    expect(blankMission(new Date(2027, 2, 9)).due_date).toBe('2027-03-09');
    expect(blankMission(new Date(2026, 11, 31)).due_date).toBe('2026-12-31');
  });

  it('and the other defaults are unchanged', () => {
    const fresh = blankMission();
    expect(fresh.priority).toBe('medium');
    expect(fresh.title).toBe('');
  });
});
