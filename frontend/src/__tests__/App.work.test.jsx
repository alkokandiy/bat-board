import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import App from '../App';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getAccount: vi.fn(),
    getMissions: vi.fn(),
    getHabits: vi.fn(),
    refreshToken: vi.fn(),
    logout: vi.fn(),
    getWorkStatus: vi.fn(),
    getWorkTasks: vi.fn(),
    getWorkNotes: vi.fn(),
    getWorkReport: vi.fn(),
    createWorkTask: vi.fn(),
    getCountdowns: vi.fn(),
    getAlfredProvider: vi.fn(),
    getAlfredSessions: vi.fn(),
  },
  browserTimezone: () => 'Asia/Tashkent',
}));

const ON = {
  enabled: true, chosen: true, has_data: true, configured: true,
  missing_essential: [], next_question: null,
  profile: { work_days_label: 'Mon, Tue', work_start: '09:00', work_end: '18:00' },
};

const workNav = () => screen.queryAllByRole('button', { name: /^Work$/ });

describe('the work side appears only when it is switched on', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('bat_access_token', 'test-token');
    api.getAccount.mockResolvedValue({ username: 'bruce', points: 0, bat_level: 'The Recruit' });
    api.getMissions.mockResolvedValue([]);
    api.getHabits.mockResolvedValue([]);
    api.refreshToken.mockResolvedValue({});
    api.getCountdowns.mockResolvedValue([]);
    api.getAlfredProvider.mockResolvedValue({ configured: false });
    api.getAlfredSessions.mockResolvedValue([]);
    api.getWorkTasks.mockResolvedValue([]);
    api.getWorkNotes.mockResolvedValue([]);
    api.getWorkReport.mockResolvedValue({
      period: 'today', label: 'today', minutes: 0, expected_minutes: 0, work_days: 0,
      expected_days: 0, completed: [], open_counts: { todo: 0, doing: 0, blocked: 0 },
      open_total: 0, learnings: [], reflections: [], text: 'Nothing yet.',
    });
  });

  const boot = async () => {
    await act(async () => { render(<App />); });
  };

  it('hides the Work entry and the dashboard tile when the track is off', async () => {
    api.getWorkStatus.mockResolvedValue({ ...ON, enabled: false });
    await boot();
    expect(workNav()).toHaveLength(0);
    expect(screen.queryByText(/Corporate Track/i)).toBeNull();
  });

  it('still boots the dashboard when the work status call fails', async () => {
    api.getWorkStatus.mockRejectedValue(new Error('boom'));
    await boot();
    expect(screen.getByText('BATCAVE COMMAND CENTER')).toBeTruthy();
    expect(workNav()).toHaveLength(0);
  });

  it('shows the entry and opens the panel when the track is on', async () => {
    api.getWorkStatus.mockResolvedValue(ON);
    await boot();
    expect(workNav().length).toBeGreaterThan(0);
    await act(async () => { fireEvent.click(workNav()[0]); });
    expect(screen.getByText('CORPORATE TRACK')).toBeTruthy();
  });

  it('leaves the work view cleanly if the track is switched off elsewhere', async () => {
    // On at boot, off by the time the panel reads its own status — what happens
    // when the user turns it off from Telegram, or in another tab.
    api.getWorkStatus.mockResolvedValueOnce(ON)
                     .mockResolvedValue({ ...ON, enabled: false });
    await boot();
    await act(async () => { fireEvent.click(workNav()[0]); });

    // Back on the dashboard, with no dead Work entry left behind.
    expect(screen.getByText('BATCAVE COMMAND CENTER')).toBeTruthy();
    expect(workNav()).toHaveLength(0);
    expect(screen.queryByText('CORPORATE TRACK')).toBeNull();
  });
});
