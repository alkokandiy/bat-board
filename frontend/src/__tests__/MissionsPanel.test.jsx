import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MissionsPanel, { currentWeek } from '../components/MissionsPanel';
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
    expect(api.createMission.mock.calls[0][0].subtasks)
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

  it('names the window by its dates', () => {
    renderPanel([]);
    // e.g. "9–15 Nov" — the boundaries are visible, not worked out.
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    expect(label).toMatch(/\d+–\d+ \w{3}|\d+ \w{3}–\d+ \w{3}/);
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

  it('today still means today or anything already late', () => {
    // The old overdue has to live somewhere, and this is where.
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: /^today$/i }));
    expect(screen.getByText('Last month')).toBeInTheDocument();
    expect(screen.getByText('Sunday just gone')).toBeInTheDocument();
    expect(screen.queryByText('This Sunday')).not.toBeInTheDocument();
  });

  it('all still means all', () => {
    renderPanel(board());
    fireEvent.click(screen.getByRole('button', { name: /^all$/i }));
    expect(screen.getByText('No date at all')).toBeInTheDocument();
    expect(screen.getByText('Next Monday')).toBeInTheDocument();
  });
});

describe('Naming a week that straddles two months', () => {
  it('says both months', () => {
    const { label } = currentWeek(new Date(2026, 10, 30));  // Mon 30 Nov 2026
    expect(label).toBe('30 Nov–6 Dec');
  });

  it('says one month when it fits in one', () => {
    const { label } = currentWeek(new Date(2026, 10, 13));  // Fri 13 Nov 2026
    expect(label).toBe('9–15 Nov');
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
