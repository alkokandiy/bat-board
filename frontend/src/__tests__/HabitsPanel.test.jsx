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
    restHabit: vi.fn(),
    unrestHabit: vi.fn(),
  },
}));

// The server never sends last_completed without the matching progress, so
// neither does this: a fixture that did would be testing a payload that
// cannot happen, and the panel trusts done_this_period over the date.
const habit = (over = {}) => ({
  done_this_period: over.last_completed ? 1 : 0,
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
  times_target: 1,
  resting_today: false,
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

describe('Three times a week', () => {
  it('shows how far through the week they are', () => {
    renderPanel([habit({
      frequency: 'weekly', schedule_label: 'once a week',
      times_target: 3, done_this_period: 2,
    })]);
    expect(screen.getByText(/2 of 3 this week/i)).toBeInTheDocument();
  });

  it('says nothing extra for an ordinary habit', () => {
    renderPanel([habit()]);
    expect(screen.queryByText(/of 1 today/i)).not.toBeInTheDocument();
  });

  it('two of three is not a kept week', () => {
    renderPanel([habit({
      frequency: 'weekly', times_target: 3, done_this_period: 2,
    })]);
    expect(screen.getByRole('button', { name: /check in/i })).toBeInTheDocument();
  });

  it('three of three is', () => {
    renderPanel([habit({
      frequency: 'weekly', times_target: 3, done_this_period: 3,
    })]);
    expect(screen.queryByRole('button', { name: /check in/i })).not.toBeInTheDocument();
  });

  it('submits a count and no weekdays, never both', async () => {
    api.createHabit.mockResolvedValue({ name: 'Gym' });
    renderPanel([]);
    fireEvent.change(screen.getByPlaceholderText(/fifty press-ups/i),
      { target: { value: 'Gym' } });
    fireEvent.change(screen.getByLabelText(/how often/i),
      { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: /n times a week/i }));
    fireEvent.change(screen.getByLabelText(/how many times a week/i),
      { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /^start tracking$/i }));

    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    const sent = api.createHabit.mock.calls[0][0];
    expect(sent.times_per_period).toBe(3);
    expect(sent.weekdays).toBeNull();
  });

  it('drops days already picked when you change your mind', async () => {
    // The real path to sending both: tick Monday, decide you would rather
    // say "three times", submit. The server returns 400 for that, and
    // rightly — naming the days already says how many.
    api.createHabit.mockResolvedValue({ name: 'Gym' });
    renderPanel([]);
    fireEvent.change(screen.getByPlaceholderText(/fifty press-ups/i),
      { target: { value: 'Gym' } });
    fireEvent.change(screen.getByLabelText(/how often/i),
      { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: /^mon$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^thu$/i }));
    fireEvent.click(screen.getByRole('button', { name: /n times a week/i }));
    fireEvent.change(screen.getByLabelText(/how many times a week/i),
      { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: /^start tracking$/i }));

    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    const sent = api.createHabit.mock.calls[0][0];
    expect(sent.times_per_period).toBe(3);
    expect(sent.weekdays).toBeNull();
  });

  it('and drops a count already typed when you change back', async () => {
    api.createHabit.mockResolvedValue({ name: 'Gym' });
    renderPanel([]);
    fireEvent.change(screen.getByPlaceholderText(/fifty press-ups/i),
      { target: { value: 'Gym' } });
    fireEvent.change(screen.getByLabelText(/how often/i),
      { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: /n times a week/i }));
    fireEvent.change(screen.getByLabelText(/how many times a week/i),
      { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /certain days/i }));
    fireEvent.click(screen.getByRole('button', { name: /^mon$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^start tracking$/i }));

    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    const sent = api.createHabit.mock.calls[0][0];
    expect(sent.weekdays).toBe('0');
    expect(sent.times_per_period).toBeNull();
  });

  it('still submits weekdays and no count in the other mode', async () => {
    api.createHabit.mockResolvedValue({ name: 'Gym' });
    renderPanel([]);
    fireEvent.change(screen.getByPlaceholderText(/fifty press-ups/i),
      { target: { value: 'Gym' } });
    fireEvent.change(screen.getByLabelText(/how often/i),
      { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: /^mon$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^start tracking$/i }));

    await waitFor(() => expect(api.createHabit).toHaveBeenCalled());
    const sent = api.createHabit.mock.calls[0][0];
    expect(sent.weekdays).toBe('0');
    expect(sent.times_per_period).toBeNull();
  });
});

describe('Resting is not failing', () => {
  it('says so on the row', () => {
    renderPanel([habit({ resting_today: true })]);
    expect(screen.getByText(/resting today/i)).toBeInTheDocument();
  });

  it('never calls it skipping', () => {
    renderPanel([habit({ resting_today: true })]);
    expect(document.body.textContent).not.toMatch(/skip/i);
  });

  it('still offers the check-in, because they may change their mind', () => {
    renderPanel([habit({ resting_today: true })]);
    expect(screen.getByRole('button', { name: /check in/i })).toBeInTheDocument();
  });

  it('takes a rest day', async () => {
    api.restHabit.mockResolvedValue({ resting: true });
    const { onRefreshHabits } = renderPanel([habit({ id: 7 })]);
    fireEvent.click(screen.getByRole('button', { name: /take a rest day/i }));
    await waitFor(() => expect(api.restHabit).toHaveBeenCalledWith(7, {}));
    await waitFor(() => expect(onRefreshHabits).toHaveBeenCalled());
  });

  it('comes back off one', async () => {
    api.unrestHabit.mockResolvedValue({ was_resting: true });
    renderPanel([habit({ id: 9, resting_today: true })]);
    fireEvent.click(screen.getByRole('button', { name: /back on/i }));
    await waitFor(() => expect(api.unrestHabit).toHaveBeenCalledWith(9));
  });

  it('reports a failure rather than swallowing it', async () => {
    api.restHabit.mockRejectedValue(new Error('nope'));
    renderPanel([habit({ id: 3 })]);
    fireEvent.click(screen.getByRole('button', { name: /take a rest day/i }));
    expect(await screen.findByText(/nope/i)).toBeInTheDocument();
  });
});

describe('Focus on this', () => {
  const withFocus = (habits, props = {}) => {
    const onFocusOn = vi.fn();
    const onRefreshHabits = vi.fn().mockResolvedValue(undefined);
    render(
      <HabitsPanel
        habits={habits}
        onRefreshHabits={onRefreshHabits}
        onRefreshAccount={vi.fn().mockResolvedValue(undefined)}
        onFocusOn={onFocusOn}
        {...props}
      />,
    );
    return { onFocusOn, onRefreshHabits };
  };

  it('hands back the habit id', () => {
    const { onFocusOn } = withFocus([habit({ id: 12 })]);
    fireEvent.click(screen.getByRole('button', { name: /focus on "fifty press-ups"/i }));
    expect(onFocusOn).toHaveBeenCalledWith(12);
  });

  it('is there on a habit that is not due today', () => {
    // Three groups render HabitRow. Missing the prop on one of them would
    // make the button vanish from a whole section, silently.
    withFocus([habit({ due_today: false })]);
    expect(screen.getByRole('button', { name: /focus on/i })).toBeInTheDocument();
  });

  it('is there on one already kept today', () => {
    withFocus([habit({ last_completed: new Date().toISOString() })]);
    expect(screen.getByRole('button', { name: /focus on/i })).toBeInTheDocument();
  });

  it('is absent when nothing is wired to it', () => {
    renderPanel([habit()]);
    expect(screen.queryByRole('button', { name: /focus on/i })).not.toBeInTheDocument();
  });

  // The calendar chip was made to mean "focus" and stopped meaning anything
  // else. These two say that did not happen here.
  it('did not take over the check-in', async () => {
    api.checkInHabit.mockResolvedValue({ name: 'Fifty press-ups' });
    const { onFocusOn } = withFocus([habit({ id: 12 })]);
    fireEvent.click(screen.getByRole('button', { name: /check in/i }));
    await waitFor(() => expect(api.checkInHabit).toHaveBeenCalledWith(12));
    expect(onFocusOn).not.toHaveBeenCalled();
  });

  it('did not take over the rest day', async () => {
    api.restHabit.mockResolvedValue({ resting: true });
    const { onFocusOn } = withFocus([habit({ id: 12 })]);
    fireEvent.click(screen.getByRole('button', { name: /take a rest day/i }));
    await waitFor(() => expect(api.restHabit).toHaveBeenCalledWith(12, {}));
    expect(onFocusOn).not.toHaveBeenCalled();
  });
});

describe('Time spent on a habit', () => {
  it('shows what went into it this period', () => {
    renderPanel([habit({ focus_minutes_period: 26, frequency: 'daily' })]);
    expect(screen.getByText('26m today')).toBeInTheDocument();
  });

  it('says it in the habit\'s own period, not always "today"', () => {
    renderPanel([habit({ focus_minutes_period: 45, frequency: 'weekly' })]);
    expect(screen.getByText('45m this week')).toBeInTheDocument();
  });

  it('shows nothing when nothing has gone into it yet', () => {
    renderPanel([habit({ focus_minutes_period: 0, focus_minutes: 0 })]);
    expect(screen.queryByText(/m today/)).not.toBeInTheDocument();
  });

  it('keeps the lifetime total, but says which is which', () => {
    // Both on the row would be two bare numbers that look like a
    // contradiction; the labels are what stop that.
    renderPanel([habit({ focus_minutes_period: 26, focus_minutes: 500 })]);
    expect(screen.getByText('26m today')).toBeInTheDocument();
    expect(screen.getByText('500m all told')).toBeInTheDocument();
  });

  it('a period total with no lifetime total still shows', () => {
    renderPanel([habit({ focus_minutes_period: 12, focus_minutes: 0 })]);
    expect(screen.getByText('12m today')).toBeInTheDocument();
    expect(screen.queryByText(/all told/)).not.toBeInTheDocument();
  });
});
