import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import HabitsPanel from '../components/HabitsPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    createHabit: vi.fn(),
    updateHabit: vi.fn(),
    deleteHabit: vi.fn(),
    checkInHabit: vi.fn(),
  },
}));

const habit = (over = {}) => ({
  id: 1,
  name: 'Fifty press-ups',
  description: null,
  cue: null,
  minimum_viable: null,
  frequency: 'daily',
  due_today: true,
  schedule_label: 'every day',
  streak: 0,
  best_streak: 0,
  adherence_done: 0,
  adherence_window: 14,
  last_completed: null,
  focus_minutes: 0,
  target_date: null,
  ...over,
});

const renderPanel = (habits) => {
  const onRefreshHabits = vi.fn().mockResolvedValue(undefined);
  const onRefreshAccount = vi.fn().mockResolvedValue(undefined);
  render(
    <HabitsPanel habits={habits} onRefreshHabits={onRefreshHabits} onRefreshAccount={onRefreshAccount} />,
  );
  return { onRefreshHabits, onRefreshAccount };
};

beforeEach(() => {
  vi.clearAllMocks();
  api.createHabit.mockResolvedValue({});
  api.updateHabit.mockResolvedValue({});
  api.deleteHabit.mockResolvedValue({});
  api.checkInHabit.mockResolvedValue({ name: 'Fifty press-ups' });
});

describe('the honest measure leads', () => {
  // The screen used to show only the consecutive run, plus an "ON FIRE" badge
  // above three — the chain framing this codebase bans, and the reason one
  // blameless missed day reads as total failure.
  it('shows recent adherence, not only the streak', () => {
    renderPanel([habit({ adherence_done: 9, streak: 2, best_streak: 11 })]);
    expect(screen.getByText('9 of your last 14')).toBeTruthy();
    expect(screen.getByText('2 in a row')).toBeTruthy();
    expect(screen.getByText('best 11')).toBeTruthy();
  });

  it('has no "on fire" badge any more', () => {
    renderPanel([habit({ streak: 9 })]);
    expect(screen.queryByText(/on fire/i)).toBeNull();
  });

  it('keeps the best run visible when the current one is gone', () => {
    renderPanel([habit({ streak: 0, best_streak: 31 })]);
    expect(screen.getByText('best 31')).toBeTruthy();
    expect(screen.queryByText('0 in a row')).toBeNull();
  });
});

describe('keeping a habit', () => {
  it('checks in and says so', async () => {
    renderPanel([habit()]);
    fireEvent.click(screen.getByRole('button', { name: /check in/i }));
    await waitFor(() => expect(api.checkInHabit).toHaveBeenCalledWith(1));
    expect(await screen.findByRole('status')).toHaveTextContent('Kept "Fifty press-ups"');
  });

  // Kept habits used to disappear from the screen altogether, so you could
  // see only what you had not done.
  it('still shows what was already kept today', () => {
    renderPanel([habit({ last_completed: new Date().toISOString() })]);
    expect(screen.getByText(/^Kept \(1\)$/)).toBeTruthy();
    expect(screen.getByText('Fifty press-ups')).toBeTruthy();
  });

  it('offers no second check-in for one already kept', () => {
    renderPanel([habit({ last_completed: new Date().toISOString() })]);
    expect(screen.queryByRole('button', { name: /check in/i })).toBeNull();
  });

  it('counts a weekly habit kept three days ago as kept', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86400000).toISOString();
    renderPanel([habit({ frequency: 'weekly', last_completed: threeDaysAgo })]);
    expect(screen.getByText(/^Kept \(1\)$/)).toBeTruthy();
  });
});

describe('the delete control', () => {
  it('names the habit it would remove', () => {
    renderPanel([habit()]);
    expect(screen.getByRole('button', { name: 'Delete "Fifty press-ups"' })).toBeTruthy();
  });

  it('asks before removing the history with it', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPanel([habit()]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Fifty press-ups"' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.deleteHabit).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe('the form', () => {
  it('creates with the trigger, which is the point of it', async () => {
    renderPanel([]);
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Stretch' } });
    fireEvent.change(screen.getByLabelText(/^Trigger/), { target: { value: 'After the kettle' } });
    fireEvent.click(screen.getByRole('button', { name: /start tracking/i }));
    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    expect(api.createHabit.mock.calls[0][0]).toMatchObject({
      name: 'Stretch',
      cue: 'After the kettle',
      frequency: 'daily',
    });
  });

  it('says nothing is tracked rather than shouting it in caps', () => {
    renderPanel([]);
    expect(screen.getByText('Nothing tracked yet')).toBeTruthy();
  });
});


describe('the bad-day version', () => {
  // A target repeatedly missed is a target set too high for the days it has
  // to survive. Doing the small version still starts the cue and closes the
  // reward, which is the loop being built.
  // The form's own label uses the same words, deliberately — so count the
  // occurrences rather than matching the phrase and hoping.
  const badDayMentions = () => screen.getAllByText(/On a bad day/).length;

  it('is shown on the row when there is one', () => {
    renderPanel([habit({ minimum_viable: 'five of them' })]);
    expect(screen.getByText('five of them')).toBeTruthy();
    expect(badDayMentions()).toBe(2);        // the field label, and the row
  });

  it('is not invented when there is none', () => {
    renderPanel([habit()]);
    expect(badDayMentions()).toBe(1);        // the field label only
  });

  it('can be set when creating the habit', async () => {
    renderPanel([]);
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Run' } });
    fireEvent.change(screen.getByLabelText(/^On a bad day/), { target: { value: 'put the shoes on' } });
    fireEvent.click(screen.getByRole('button', { name: /start tracking/i }));
    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    expect(api.createHabit.mock.calls[0][0].minimum_viable).toBe('put the shoes on');
  });

  it('counts the ones still missing it, so the gap is visible', () => {
    renderPanel([habit({ id: 1 }), habit({ id: 2, minimum_viable: 'one page' })]);
    expect(screen.getByText(/with no bad-day version/)).toBeTruthy();
  });
});


describe('saying which days a habit is for', () => {
  // "If i choose every week, it's just guess? which day of the week?"
  // It was: nothing in the record knew, so a weekly habit sat in "still to
  // keep" all seven days until ticked once.
  it('offers a day picker once the schedule needs one', () => {
    renderPanel([]);
    expect(screen.queryByRole('button', { name: 'Mon' })).toBeNull();
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'weekly' } });
    // A labelled group, not a <label> wrapping seven buttons — inside one,
    // every button reports the same accessible name.
    expect(screen.getByRole('group', { name: 'Which days' })).toBeTruthy();
    for (const d of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      expect(screen.getByRole('button', { name: d })).toBeTruthy();
    }
  });

  it('sends the chosen days', async () => {
    renderPanel([]);
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Gym' } });
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mon' }));
    fireEvent.click(screen.getByRole('button', { name: 'Thu' }));
    fireEvent.click(screen.getByRole('button', { name: /start tracking/i }));
    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    expect(api.createHabit.mock.calls[0][0].weekdays).toBe('0,3');
  });

  it('asks for a date when the habit is monthly', () => {
    renderPanel([]);
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'monthly' } });
    expect(screen.getByLabelText(/^Which date/)).toBeTruthy();
  });

  it('asks for a number of days when the habit is an interval', async () => {
    renderPanel([]);
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Plants' } });
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'interval' } });
    fireEvent.change(screen.getByLabelText(/^Every how many days/), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /start tracking/i }));
    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    expect(api.createHabit.mock.calls[0][0].interval_days).toBe(3);
  });

  it('shows the schedule on the row instead of a bare frequency word', () => {
    renderPanel([habit({ frequency: 'weekly', schedule_label: 'every Mon, Thu' })]);
    expect(screen.getByText('every Mon, Thu')).toBeTruthy();
  });

  it('keeps a habit that is not due today out of "still to keep"', () => {
    renderPanel([habit({ due_today: false, schedule_label: 'every Mon, Thu' })]);
    expect(screen.getByText(/^Not due today \(1\)$/)).toBeTruthy();
    expect(screen.getByText('All kept — come back tomorrow')).toBeTruthy();
  });

  it('still shows an unscheduled habit as due, so nothing vanishes', () => {
    renderPanel([habit()]);
    expect(screen.queryByText(/^Not due today/)).toBeNull();
    expect(screen.getByRole('button', { name: /check in/i })).toBeTruthy();
  });
});
