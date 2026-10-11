import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import WorkPanel from '../WorkPanel';
import DashboardLayout from '../DashboardLayout';
import { api } from '../../utils/api';

vi.mock('../../utils/api', () => ({
  api: {
    getWorkStatus: vi.fn(),
    setWorkEnabled: vi.fn(),
    updateWorkProfile: vi.fn(),
    getWorkTasks: vi.fn(),
    createWorkTask: vi.fn(),
    updateWorkTask: vi.fn(),
    completeWorkTask: vi.fn(),
    deleteWorkTask: vi.fn(),
    getWorkNotes: vi.fn(),
    createWorkNote: vi.fn(),
    getWorkReport: vi.fn(),
  },
}));

const CONFIGURED = {
  enabled: true,
  chosen: true,
  has_data: true,
  configured: true,
  missing_essential: [],
  next_question: null,
  profile: {
    employer: 'Wayne Enterprises',
    work_days: '0,1,2,3,4',
    work_days_label: 'Mon, Tue, Wed, Thu, Fri',
    work_start: '09:00',
    work_end: '18:00',
  },
};

const task = (over = {}) => ({
  id: 1, title: 'Ship the invoice', detail: null, status: 'todo', project: 'Finance',
  due_date: null, focus_minutes: 0, created_at: '2026-10-10T08:00:00Z',
  updated_at: '2026-10-10T08:00:00Z', completed_at: null, ...over,
});

const REPORT = {
  period: 'today', label: 'Saturday, 10 October', minutes: 95, expected_minutes: 480,
  work_days: 1, expected_days: 1, completed: [], open_counts: { todo: 1, doing: 0, blocked: 0 },
  open_total: 1, learnings: [], reflections: [],
  text: 'Work — today.\n\nWas today worth the hours, sir?',
};

const renderPanel = async (props = {}) => {
  await act(async () => { render(<WorkPanel {...props} />); });
};

describe('WorkPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getWorkStatus.mockResolvedValue(CONFIGURED);
    api.getWorkTasks.mockResolvedValue([task()]);
    api.getWorkNotes.mockResolvedValue([]);
    api.getWorkReport.mockResolvedValue(REPORT);
  });

  it('shows the board, the schedule and the no-points rule', async () => {
    await renderPanel();
    expect(screen.getByText('Ship the invoice')).toBeTruthy();
    expect(screen.getByText(/Wayne Enterprises/)).toBeTruthy();
    expect(screen.getByText(/Mon, Tue, Wed, Thu, Fri/)).toBeTruthy();
    expect(screen.getByText(/NO BAT POINTS/)).toBeTruthy();
  });

  it('says so plainly instead of rendering an empty board when the track is off', async () => {
    api.getWorkStatus.mockResolvedValue({ ...CONFIGURED, enabled: false });
    await renderPanel();
    expect(screen.getByText(/work track is switched off/i)).toBeTruthy();
    expect(screen.getByText(/Nothing of yours was deleted/i)).toBeTruthy();
    expect(api.getWorkTasks).not.toHaveBeenCalled();   // no doomed calls
  });

  it('reports the switch state up so the sidebar can follow it', async () => {
    const onStatusChange = vi.fn();
    api.getWorkStatus.mockResolvedValue({ ...CONFIGURED, enabled: false });
    await renderPanel({ onStatusChange });
    expect(onStatusChange).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false }),
    );
  });

  it('adds a task from one field', async () => {
    api.createWorkTask.mockResolvedValue(task({ id: 2, title: 'Review the deck', project: null }));
    await renderPanel();
    fireEvent.change(screen.getByPlaceholderText(/What does the job need/i),
                     { target: { value: 'Review the deck' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Add work task' }));
    });
    expect(api.createWorkTask).toHaveBeenCalledWith({ title: 'Review the deck', project: null });
    expect(screen.getByText('Review the deck')).toBeTruthy();
  });

  it('moves a task between columns without reloading the board', async () => {
    api.updateWorkTask.mockResolvedValue(task({ status: 'blocked' }));
    await renderPanel();
    await act(async () => {
      fireEvent.change(screen.getByDisplayValue('To do'), { target: { value: 'blocked' } });
    });
    expect(api.updateWorkTask).toHaveBeenCalledWith(1, { status: 'blocked' });
    expect(api.getWorkTasks).toHaveBeenCalledTimes(1);      // the initial load only
  });

  it('offers the schedule setup in one step when it is missing', async () => {
    api.getWorkStatus.mockResolvedValue({
      ...CONFIGURED, configured: false, missing_essential: ['work_days'],
      next_question: 'Which days do you work?',
      profile: { ...CONFIGURED.profile, work_days: null, work_days_label: '' },
    });
    api.updateWorkProfile.mockResolvedValue(CONFIGURED);
    await renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Mon' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tue' }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /SAVE SCHEDULE/ }));
    });
    expect(api.updateWorkProfile).toHaveBeenCalledWith(expect.objectContaining({
      work_days: '0,1', work_start: '09:00', work_end: '18:00',
    }));
  });

  it('keeps a reflection against the report', async () => {
    api.createWorkNote.mockResolvedValue({ id: 9, kind: 'reflection', content: 'Worth it',
                                           created_at: '2026-10-10T18:00:00Z' });
    await renderPanel();
    expect(screen.getByText(/Was today worth the hours/)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText(/Your answer/i), { target: { value: 'Worth it' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /SAVE REFLECTION/ }));
    });
    expect(api.createWorkNote).toHaveBeenCalledWith({ content: 'Worth it', kind: 'reflection' });
  });
});

describe('the Work entry in the shell', () => {
  it('is absent while the track is off and present when it is on', () => {
    const { rerender } = render(
      <DashboardLayout account={{ username: 'bruce' }} currentView="missions" workEnabled={false}>
        <div />
      </DashboardLayout>,
    );
    expect(screen.queryAllByRole('button', { name: /^Work$/ })).toHaveLength(0);

    rerender(
      <DashboardLayout account={{ username: 'bruce' }} currentView="missions" workEnabled>
        <div />
      </DashboardLayout>,
    );
    expect(screen.getAllByRole('button', { name: /^Work$/ }).length).toBeGreaterThan(0);
  });
});
