import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MissionsPanel from '../components/MissionsPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    createMission: vi.fn(),
    updateMission: vi.fn(),
    deleteMission: vi.fn(),
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
