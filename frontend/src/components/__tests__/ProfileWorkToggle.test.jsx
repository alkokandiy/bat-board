import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import ProfileSettings from '../ProfileSettings';
import { api } from '../../utils/api';

vi.mock('../../utils/api', () => ({
  api: {
    getTelegramLinkStatus: vi.fn(),
    resetAlfred: vi.fn(),
    updateAccount: vi.fn(),
    getAdminMe: vi.fn(),
    getWorkStatus: vi.fn(),
    setWorkEnabled: vi.fn(),
  },
  browserTimezone: () => 'Asia/Tashkent',
}));

const account = { username: 'bruce', points: 0, bat_level: 'The Recruit', timezone: 'Asia/Tashkent' };

const renderSettings = async (props = {}) => {
  const onWorkEnabledChange = vi.fn();
  await act(async () => {
    render(<ProfileSettings account={account} onRefreshAccount={vi.fn()}
                            onWorkEnabledChange={onWorkEnabledChange} {...props} />);
  });
  return { onWorkEnabledChange };
};

describe('the work track switch in Profile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getTelegramLinkStatus.mockResolvedValue({ linked: false });
    api.getAdminMe.mockResolvedValue({ is_admin: false });
    api.getWorkStatus.mockResolvedValue({ enabled: false, has_data: false });
  });

  it('offers to turn work on when it is off', async () => {
    await renderSettings({ workEnabled: false });
    expect(screen.getByRole('button', { name: /TURN WORK ON/ })).toBeTruthy();
    expect(screen.getByText('CURRENTLY OFF')).toBeTruthy();
  });

  it('turns it on and tells the app, so the sidebar follows immediately', async () => {
    api.setWorkEnabled.mockResolvedValue({ enabled: true, has_data: false });
    const { onWorkEnabledChange } = await renderSettings({ workEnabled: false });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /TURN WORK ON/ }));
    });
    expect(api.setWorkEnabled).toHaveBeenCalledWith(true);
    expect(onWorkEnabledChange).toHaveBeenCalledWith(true);
  });

  it('promises the data back when there is data to keep', async () => {
    api.getWorkStatus.mockResolvedValue({ enabled: true, has_data: true });
    await renderSettings({ workEnabled: true });
    expect(screen.getByRole('button', { name: /TURN WORK OFF/ })).toBeTruthy();
    expect(screen.getByText(/returns exactly as it was/i)).toBeTruthy();
  });

  it('surfaces a failed switch instead of lying about the state', async () => {
    api.setWorkEnabled.mockRejectedValue(new Error('Network down'));
    const { onWorkEnabledChange } = await renderSettings({ workEnabled: false });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /TURN WORK ON/ }));
    });
    expect(screen.getByText('Network down')).toBeTruthy();
    expect(onWorkEnabledChange).not.toHaveBeenCalled();
    expect(screen.getByText('CURRENTLY OFF')).toBeTruthy();
  });
});
