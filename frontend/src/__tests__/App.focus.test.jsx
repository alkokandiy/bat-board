import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import App from '../App';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getAccount: vi.fn(),
    getMissions: vi.fn(),
    getHabits: vi.fn(),
    getLogs: vi.fn(),
    refreshToken: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    login: vi.fn(),
    startFocusSession: vi.fn(),
    endFocusSession: vi.fn(),
    getWorkStatus: vi.fn(),
    getSuggestedFocusMinutes: vi.fn(),
    getActiveFocusSession: vi.fn(),
  },
}));

const goToFocusView = async () => {
  await act(async () => {
    fireEvent.click(screen.getAllByRole('button', { name: /focus/i })[0]);
  });
};

const clickEnterFocus = async () => {
  await act(async () => {
    fireEvent.click(screen.getByText('ENTER FOCUS'));
  });
};

const setSessionLength = async (minutes) => {
  await act(async () => {
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: String(minutes) } });
  });
};

describe('App focus session state machine', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'tester', points: 0, bat_level: 'Bronze' });
    api.getMissions.mockResolvedValue([]);
    api.getHabits.mockResolvedValue([]);
    api.getLogs.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.startFocusSession.mockResolvedValue({ id: 101 });
    api.endFocusSession.mockResolvedValue({});
    api.getSuggestedFocusMinutes.mockResolvedValue({ minutes: 30, basis: 'default', sessions: 0 });
    api.getActiveFocusSession.mockResolvedValue({ active: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('persists exactly one session on natural completion, with the full configured duration', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await clickEnterFocus();
    expect(api.startFocusSession).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(25 * 60 * 1000);
    });

    expect(api.startFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).toHaveBeenCalledWith(101, { duration_minutes: 25 });
  });

  it('keeps a single backend row across pause/resume cycles', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await clickEnterFocus();
    expect(api.startFocusSession).toHaveBeenCalledTimes(1);

    for (let i = 0; i < 3; i++) {
      await act(async () => {
        fireEvent.click(screen.getByText('PAUSE'));
      });
      await act(async () => {
        fireEvent.click(screen.getByText('RESUME'));
      });
    }

    expect(api.startFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).not.toHaveBeenCalled();
  });

  it('records the actual elapsed wall-clock time for a short 5-minute session', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await setSessionLength(5);
    await clickEnterFocus();
    expect(api.startFocusSession).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(5 * 60 * 1000);
    });

    expect(api.endFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).toHaveBeenCalledWith(101, { duration_minutes: 5 });
  });

  it('does not credit time spent paused', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await clickEnterFocus();

    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000);
    });
    await act(async () => {
      fireEvent.click(screen.getByText('PAUSE'));
    });
    await act(async () => {
      vi.advanceTimersByTime(60 * 60 * 1000); // an hour away from the desk
    });
    await act(async () => {
      fireEvent.click(screen.getByText('RESUME'));
    });
    await act(async () => {
      vi.advanceTimersByTime(15 * 60 * 1000);
    });

    expect(api.endFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).toHaveBeenCalledWith(101, { duration_minutes: 25 });
  });

  it('records the selected timer mode when the session starts', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await act(async () => {
      fireEvent.click(screen.getAllByTitle('Bat-Signal')[0]);
    });
    await clickEnterFocus();

    expect(api.startFocusSession).toHaveBeenCalledTimes(1);
    expect(api.startFocusSession).toHaveBeenCalledWith({ mode: 'signal' });
  });

  it('defaults to normal and keeps the mode recorded at start when switching mid-session', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await clickEnterFocus();
    expect(api.startFocusSession).toHaveBeenCalledWith({ mode: 'normal' });

    await act(async () => {
      fireEvent.click(screen.getAllByTitle('Batmobile')[0]);
    });
    await act(async () => {
      vi.advanceTimersByTime(5 * 60 * 1000);
    });
    // The session was started once, with the mode at start; nothing re-sends it.
    expect(api.startFocusSession).toHaveBeenCalledTimes(1);
    expect(api.endFocusSession).not.toHaveBeenCalledWith(101, expect.objectContaining({ mode: expect.anything() }));
  });

  it('keeps the chosen mode when entering focus mode (the timer remounts)', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    await act(async () => {
      fireEvent.click(screen.getAllByTitle('Flip Clock')[0]);
    });
    await clickEnterFocus();
    // Focus mode renders a fresh timer; the mode button state must carry over.
    await act(async () => {
      fireEvent.click(screen.getByText('PAUSE'));
    });
    expect(api.startFocusSession).toHaveBeenCalledWith({ mode: 'flip' });
  });
});


describe('Focus on this, from the mission list', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'tester', points: 0, bat_level: 'Bronze' });
    api.getMissions.mockResolvedValue([
      { id: 9, title: 'Pay the invoice', priority: 'high', status: 'pending',
        is_pinned: false, is_dismissed: false, focus_minutes: 0 },
    ]);
    api.getHabits.mockResolvedValue([]);
    api.getLogs.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.startFocusSession.mockResolvedValue({ id: 101 });
    api.endFocusSession.mockResolvedValue({});
    api.getSuggestedFocusMinutes.mockResolvedValue({ minutes: 30, basis: 'default', sessions: 0 });
    api.getActiveFocusSession.mockResolvedValue({ active: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  const goToMissions = async () => {
    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: /missions/i })[0]);
    });
  };

  it('lands on the timer with that mission already the target', async () => {
    // The whole point: choosing what to work on and starting to work on it
    // were two screens apart, and the gap is where the intention went.
    render(<App />);
    await act(async () => {});
    await goToMissions();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    });

    // The focus screen, and the target already chosen.
    expect(screen.getByRole('button', { name: /focus target/i }))
      .toHaveTextContent('Pay the invoice');
  });

  it('replaces a habit target rather than holding both', async () => {
    // "One target per session — a mission or a habit" is stated on the
    // screen. Setting the mission without clearing the habit would send
    // both ids and quietly break that promise.
    api.getHabits.mockResolvedValue([
      { id: 3, name: 'Fifty press-ups', frequency: 'daily', streak: 0,
        best_streak: 0, due_today: true, times_target: 1, done_this_period: 0 },
    ]);
    render(<App />);
    await act(async () => {});
    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: /focus/i })[0]);
    });

    // Choose the habit as the target first.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus target/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: /fifty press-ups/i }));
    });
    expect(screen.getByRole('button', { name: /focus target/i }))
      .toHaveTextContent('Fifty press-ups');

    // Now pick a mission from the list instead.
    await goToMissions();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('ENTER FOCUS'));
    });

    const sent = api.startFocusSession.mock.calls[0][0];
    expect(sent.mission_id).toBe(9);
    expect(sent.habit_id).toBeUndefined();
  });

  it('starts the session against that mission', async () => {
    render(<App />);
    await act(async () => {});
    await goToMissions();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('ENTER FOCUS'));
    });
    expect(api.startFocusSession).toHaveBeenCalledWith(
      expect.objectContaining({ mission_id: 9 }),
    );
  });

});

describe('Focus on this, from the habit list', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'tester', points: 0, bat_level: 'Bronze' });
    api.getMissions.mockResolvedValue([
      { id: 9, title: 'Pay the invoice', priority: 'high', status: 'pending',
        is_pinned: false, is_dismissed: false, focus_minutes: 0 },
    ]);
    api.getHabits.mockResolvedValue([
      { id: 3, name: 'Fifty press-ups', frequency: 'daily', streak: 0, best_streak: 0,
        due_today: true, times_target: 1, done_this_period: 0, resting_today: false,
        adherence_done: 0, adherence_window: 14, focus_minutes: 0 },
    ]);
    api.getLogs.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.startFocusSession.mockResolvedValue({ id: 101 });
    api.endFocusSession.mockResolvedValue({});
    api.getSuggestedFocusMinutes.mockResolvedValue({ minutes: 30, basis: 'default', sessions: 0 });
    api.getActiveFocusSession.mockResolvedValue({ active: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  const goTo = async (name) => {
    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name })[0]);
    });
  };

  it('lands on the timer with that habit already the target', async () => {
    render(<App />);
    await act(async () => {});
    await goTo(/habits/i);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "fifty press-ups"/i }));
    });
    expect(screen.getByRole('button', { name: /focus target/i }))
      .toHaveTextContent('Fifty press-ups');
  });

  it('starts the session against that habit', async () => {
    render(<App />);
    await act(async () => {});
    await goTo(/habits/i);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "fifty press-ups"/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('ENTER FOCUS'));
    });
    const sent = api.startFocusSession.mock.calls[0][0];
    expect(sent.habit_id).toBe(3);
    expect(sent.mission_id).toBeUndefined();
  });

  it('replaces a mission target rather than holding both', async () => {
    // The mirror of the mission case. "One target per session" has to hold
    // whichever direction you switch.
    render(<App />);
    await act(async () => {});
    await goTo(/missions/i);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    });
    await goTo(/habits/i);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /focus on "fifty press-ups"/i }));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('ENTER FOCUS'));
    });
    const sent = api.startFocusSession.mock.calls[0][0];
    expect(sent.habit_id).toBe(3);
    expect(sent.mission_id).toBeUndefined();
  });
});

describe('Picking the clock back up after a reload or a re-login', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'tester', points: 0, bat_level: 'Bronze' });
    api.getMissions.mockResolvedValue([
      { id: 9, title: 'Pay the invoice', priority: 'high', status: 'pending',
        is_pinned: false, is_dismissed: false, focus_minutes: 0 },
    ]);
    api.getHabits.mockResolvedValue([]);
    api.getLogs.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.startFocusSession.mockResolvedValue({ id: 101 });
    api.endFocusSession.mockResolvedValue({});
    api.getSuggestedFocusMinutes.mockResolvedValue({ minutes: 30, basis: 'default', sessions: 0 });
    api.getActiveFocusSession.mockResolvedValue({ active: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  const running = (over = {}) => ({
    active: true, id: 77, planned_minutes: 25,
    elapsed_seconds: 360, remaining_seconds: 25 * 60 - 360,
    mission_id: null, habit_id: null, mode: 'normal', ...over,
  });

  it('comes back running, with the time that is actually left', async () => {
    api.getActiveFocusSession.mockResolvedValue(running());
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    // 25 minutes planned, six gone: nineteen left, not twenty-five.
    // getAllBy: the big digits and the REMAINING line both say it.
    expect(screen.getAllByText(/19:00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/25:00/)).toBeNull();
  });

  it('restores the length too, so the progress bar is not frozen', async () => {
    // The bar is drawn from timeLeft over length. Restoring one without the
    // other left it stuck at full while the digits counted down — which is
    // exactly what a re-login looked like.
    api.getActiveFocusSession.mockResolvedValue(running());
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    expect(screen.getByRole('spinbutton').value).toBe('25');
    expect(screen.getByText(/24% · 19:00 REMAINING/i)).toBeTruthy();
  });

  it('remembers what the session was on', async () => {
    api.getActiveFocusSession.mockResolvedValue(running({ mission_id: 9 }));
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    expect(screen.getByRole('button', { name: /focus target/i }))
      .toHaveTextContent('Pay the invoice');
  });

  it('credits the time that really elapsed, not what this tab watched', async () => {
    // The tab was shut for six of the twenty-five minutes. When the clock
    // runs out, the whole session must be logged — not the nineteen this
    // tab happened to be present for.
    api.getActiveFocusSession.mockResolvedValue(running());
    render(<App />);
    await act(async () => {});
    await goToFocusView();

    await act(async () => {
      vi.advanceTimersByTime(19 * 60 * 1000);
    });

    expect(api.endFocusSession).toHaveBeenCalledWith(77, { duration_minutes: 25 });
  });

  it('starts no session of its own when one is already running', async () => {
    api.getActiveFocusSession.mockResolvedValue(running());
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    expect(api.startFocusSession).not.toHaveBeenCalled();
  });

  it('boots normally when nothing is running', async () => {
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    expect(screen.getByText('ENTER FOCUS')).toBeTruthy();
  });

  it('still boots if the lookup fails', async () => {
    api.getActiveFocusSession.mockRejectedValue(new Error('down'));
    render(<App />);
    await act(async () => {});
    await goToFocusView();
    expect(screen.getByText('ENTER FOCUS')).toBeTruthy();
  });
});

describe('Staying signed in', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'tester', points: 0, bat_level: 'Bronze' });
    api.getMissions.mockResolvedValue([]);
    api.getHabits.mockResolvedValue([]);
    api.getLogs.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.getSuggestedFocusMinutes.mockResolvedValue({ minutes: 30, basis: 'default', sessions: 0 });
    api.getActiveFocusSession.mockResolvedValue({ active: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  const becomeVisible = async () => {
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
  };

  it('refreshes when the tab is looked at again', async () => {
    // An interval is throttled in a background tab and does not run at all
    // while the machine sleeps, so a tab left open overnight came back with
    // a token that expired hours ago.
    render(<App />);
    await act(async () => {});
    api.refreshToken.mockClear();
    await act(async () => { vi.advanceTimersByTime(6 * 60 * 1000); });
    await becomeVisible();
    expect(api.refreshToken).toHaveBeenCalledTimes(1);
  });

  it('does not refresh on every tab switch', async () => {
    // /auth/refresh allows ten a minute; switching tabs is constant.
    render(<App />);
    await act(async () => {});
    api.refreshToken.mockClear();
    await act(async () => { vi.advanceTimersByTime(6 * 60 * 1000); });
    await becomeVisible();
    await becomeVisible();
    await becomeVisible();
    expect(api.refreshToken).toHaveBeenCalledTimes(1);
  });

  it('ignores the tab being hidden', async () => {
    render(<App />);
    await act(async () => {});
    api.refreshToken.mockClear();
    await act(async () => { vi.advanceTimersByTime(6 * 60 * 1000); });
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(api.refreshToken).not.toHaveBeenCalled();
  });

  it('a failed refresh does not take the board down', async () => {
    api.refreshToken.mockRejectedValue(new Error('expired'));
    render(<App />);
    await act(async () => {});
    await act(async () => { vi.advanceTimersByTime(6 * 60 * 1000); });
    await becomeVisible();
    expect(screen.queryByText(/BOOT CRITICAL ERROR/i)).toBeNull();
  });
});
