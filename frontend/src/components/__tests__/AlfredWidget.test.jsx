import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import AlfredWidget from '../AlfredWidget';
import { api } from '../../utils/api';

vi.mock('../../utils/api', () => ({
  api: {
    getAlfredSessions: vi.fn(),
    getAlfredSessionMessages: vi.fn(),
    createAlfredSession: vi.fn(),
    renameAlfredSession: vi.fn(),
    deleteAlfredSession: vi.fn(),
    sendAlfredMessage: vi.fn(),
    getAlfredProvider: vi.fn(),
  },
}));

const account = { username: 'bruce', alfred_address: 'Master Wayne' };

async function openConversations() {
  render(<AlfredWidget account={account} />);
  await act(async () => {
    fireEvent.click(screen.getByTitle('Summon Alfred'));
  });
  await act(async () => {
    fireEvent.click(screen.getByTitle('Conversations'));
  });
}

describe('AlfredWidget conversations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn(); // not implemented in jsdom
    api.getAlfredSessions.mockResolvedValue([
      { id: 1, title: 'Gotham plans', updated_at: '2026-10-01T09:00:00Z' },
      { id: 2, title: 'Arkham notes', updated_at: '2026-09-30T09:00:00Z' },
    ]);
    api.getAlfredSessionMessages.mockResolvedValue([]);
    api.deleteAlfredSession.mockResolvedValue(null);
    api.renameAlfredSession.mockImplementation(async (id, title) => ({ id, title }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('greets the user by their own form of address', async () => {
    await openConversations();
    expect(screen.getByText(/Master Wayne\. The books are open/)).toBeInTheDocument();
  });

  it('deletes a conversation and moves to the next one', async () => {
    await openConversations();
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Delete Gotham plans'));
    });
    expect(api.deleteAlfredSession).toHaveBeenCalledWith(1);
    expect(screen.queryByText('Gotham plans')).not.toBeInTheDocument();
    expect(api.getAlfredSessionMessages).toHaveBeenLastCalledWith(2);
  });

  it('does nothing when the delete is not confirmed', async () => {
    window.confirm.mockReturnValue(false);
    await openConversations();
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Delete Gotham plans'));
    });
    expect(api.deleteAlfredSession).not.toHaveBeenCalled();
  });

  it('renames a conversation inline', async () => {
    await openConversations();
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Rename Arkham notes'));
    });
    const input = screen.getByDisplayValue('Arkham notes');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Asylum intel' } });
      fireEvent.submit(input.closest('form'));
    });
    expect(api.renameAlfredSession).toHaveBeenCalledWith(2, 'Asylum intel');
    expect(screen.getByText('Asylum intel')).toBeInTheDocument();
  });
});
