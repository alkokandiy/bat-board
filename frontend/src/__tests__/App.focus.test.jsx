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
});