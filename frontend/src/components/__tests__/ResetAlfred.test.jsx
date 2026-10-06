import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, within } from '@testing-library/react';
import ProfileSettings from '../ProfileSettings';
import { api } from '../../utils/api';

vi.mock('../../utils/api', () => ({
  api: {
    getTelegramLinkStatus: vi.fn(),
    resetAlfred: vi.fn(),
    updateAccount: vi.fn(),
    getAdminMe: vi.fn(),
  },
  browserTimezone: () => 'Asia/Tashkent',
}));

const account = { username: 'bruce', points: 0, bat_level: 'The Recruit', timezone: 'Asia/Tashkent' };

describe('Reset Alfred confirmation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getTelegramLinkStatus.mockResolvedValue({ linked: false });
    api.resetAlfred.mockResolvedValue({ sessions: 2, messages: 6, memory_notes: 0 });
    api.getAdminMe.mockResolvedValue({ is_admin: false });
  });

  async function openConfirm() {
    render(<ProfileSettings account={account} onRefreshAccount={vi.fn()} />);
    await act(async () => {
      fireEvent.click(screen.getByText('RESET ALFRED'));
    });
    return screen.getByRole('alertdialog');
  }

  it('lists what is deleted and kept, and deletes nothing until confirmed', async () => {
    const dialog = await openConfirm();
    expect(within(dialog).getByText(/All Alfred conversations/)).toBeInTheDocument();
    expect(within(dialog).getByText("Alfred's memory notes about you")).toBeInTheDocument();
    expect(within(dialog).getByText('Your AI model key and settings')).toBeInTheDocument();
    expect(api.resetAlfred).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(within(dialog).getByText('CANCEL'));
    });
    expect(api.resetAlfred).not.toHaveBeenCalled();
  });

  it('moves memory to the deleted list when the box is ticked', async () => {
    render(<ProfileSettings account={account} onRefreshAccount={vi.fn()} />);
    fireEvent.click(screen.getByLabelText(/Also erase everything Alfred remembers/));
    await act(async () => {
      fireEvent.click(screen.getByText('RESET ALFRED'));
    });
    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText(/Everything Alfred remembers about you/)).toBeInTheDocument();
    expect(within(dialog).queryByText("Alfred's memory notes about you")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(within(dialog).getByText('DELETE PERMANENTLY'));
    });
    expect(api.resetAlfred).toHaveBeenCalledWith(true);
  });
});
