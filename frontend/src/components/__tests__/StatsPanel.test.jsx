import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StatsPanel from '../StatsPanel';
import { api } from '../../utils/api';

vi.mock('../../utils/api', () => ({
  api: {
    getFocusStats: vi.fn(),
    getFocusTrend: vi.fn(),
    getDayStats: vi.fn(),
    getFocusSessionLog: vi.fn(),
  },
}));

const statsPayload = {
  period: 'week',
  range_start: '2026-08-17',
  range_end: '2026-08-23',
  total_minutes: 340,
  total_sessions: 12,
  current_streak_days: 4,
  breakdown: [
    { type: 'mission', id: 4, name: 'Ship PHANTOM-1 auth module', minutes: 180, sessions: 5, percent: 52.9 },
    { type: 'habit', id: 2, name: 'Gym Training', minutes: 90, sessions: 3, percent: 26.5 },
    { type: 'mission', id: 7, name: 'Humo web platform bugfixes', minutes: 40, sessions: 2, percent: 11.8 },
    { type: 'none', id: null, name: 'Unassigned', minutes: 30, sessions: 2, percent: 8.8 },
  ],
  daily_heatmap: Array.from({ length: 35 }, (_, i) => ({
    date: `2026-07-${String(17 + i).padStart(2, '0')}`,
    minutes: i % 5 === 0 ? 45 : i % 3 === 0 ? 20 : i % 2 === 0 ? 10 : 0,
  })),
};

const trendPayload = {
  granularity: 'day',
  points: [
    { label: 'Mon', date: '2026-08-17', minutes: 45, sessions: 2 },
    { label: 'Tue', date: '2026-08-18', minutes: 0, sessions: 0 },
    { label: 'Wed', date: '2026-08-19', minutes: 90, sessions: 3 },
    { label: 'Thu', date: '2026-08-20', minutes: 25, sessions: 1 },
    { label: 'Fri', date: '2026-08-21', minutes: 60, sessions: 2 },
    { label: 'Sat', date: '2026-08-22', minutes: 0, sessions: 0 },
    { label: 'Sun', date: '2026-08-23', minutes: 120, sessions: 4 },
  ],
};

const dayPayload = {
  date: '2026-08-20',
  completed_count: 2,
  total_count: 3,
  completion_rate: 66.67,
  completed_not_due_today: 1,
  status_distribution: { on_time: 1, overdue: 1, uncompleted: 1 },
  type_distribution: [
    { type: 'mission', count: 2 },
    { type: 'habit', count: 1 },
  ],
  tag_distribution: [
    { tag: 'phantom-1', count: 2 },
    { tag: 'untagged', count: 1 },
  ],
};

const logPayload = {
  total: 12,
  limit: 20,
  offset: 0,
  items: [
    { id: 1, start_time: '2026-08-20T06:23:42', end_time: '2026-08-20T07:23:42', duration_minutes: 25, mission_id: 4, mission_name: 'Ship PHANTOM-1 auth module', habit_id: null, habit_name: null },
    { id: 2, start_time: '2026-08-19T06:00:00', end_time: '2026-08-19T06:30:00', duration_minutes: 30, mission_id: null, mission_name: null, habit_id: null, habit_name: null },
  ],
};

const toISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

describe('StatsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getFocusStats.mockResolvedValue(statsPayload);
    api.getFocusTrend.mockResolvedValue(trendPayload);
    api.getDayStats.mockResolvedValue(dayPayload);
    api.getFocusSessionLog.mockResolvedValue(logPayload);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders header, stat tiles, totals, heatmap, and breakdown', async () => {
    render(<StatsPanel />);

    expect(await screen.findByText('FOCUS STATS')).toBeInTheDocument();
    expect(screen.getByText('Where the deep work actually goes.')).toBeInTheDocument();

    expect(screen.getByText("Today's Sessions")).toBeInTheDocument();
    expect(screen.getByText("Today's Focus")).toBeInTheDocument();
    expect(screen.getByText('Total Sessions')).toBeInTheDocument();
    expect(screen.getByText('Total Focus Duration')).toBeInTheDocument();
    expect(screen.getAllByText('12').length).toBeGreaterThan(0);
    expect(screen.getAllByText('5h 40m').length).toBeGreaterThan(0);

    await waitFor(() => expect(screen.getByText('4 days')).toBeInTheDocument());
    expect(api.getFocusStats).toHaveBeenCalledWith('week');

    const cells = document.querySelectorAll('div[title*="min"]');
    expect(cells.length).toBe(35);

    expect(screen.getAllByText('Ship PHANTOM-1 auth module').length).toBeGreaterThan(0);
    expect(screen.getByText('Gym Training')).toBeInTheDocument();
    expect(screen.getAllByText('Unassigned').length).toBeGreaterThan(0);
  });

  it('renders the recent focus curve and refetches on granularity change', async () => {
    render(<StatsPanel />);

    expect(await screen.findByText('RECENT FOCUS CURVE')).toBeInTheDocument();
    expect(api.getFocusTrend).toHaveBeenCalledWith('day');
    expect(document.querySelector('svg path')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('trend-gran-week'));
    await waitFor(() => expect(api.getFocusTrend).toHaveBeenCalledWith('week'));
  });

  it('shows an empty message for a flat all-zero trend', async () => {
    api.getFocusTrend.mockResolvedValue({
      granularity: 'day',
      points: trendPayload.points.map((p) => ({ ...p, minutes: 0, sessions: 0 })),
    });

    render(<StatsPanel />);
    expect(await screen.findByText('No sessions yet this period')).toBeInTheDocument();
  });

  it('refetches stats when the period toggle changes', async () => {
    render(<StatsPanel />);
    await screen.findByText('4 days');

    fireEvent.click(screen.getByTestId('period-month'));
    await waitFor(() => expect(api.getFocusStats).toHaveBeenCalledWith('month'));
  });

  it('renders empty state when no breakdown exists', async () => {
    api.getFocusStats.mockResolvedValue({ ...statsPayload, breakdown: [], total_minutes: 0, total_sessions: 0, current_streak_days: 0 });
    api.getFocusSessionLog.mockResolvedValue({ total: 0, limit: 20, offset: 0, items: [] });

    render(<StatsPanel />);
    await screen.findByText('0m');
    expect(screen.getByText('No completed focus sessions in this period.')).toBeInTheDocument();
  });

  it('DAY tab shows date navigator, completed rate, status donut, and type/tag toggle', async () => {
    render(<StatsPanel />);
    fireEvent.click(screen.getByTestId('stats-tab-day'));

    expect(await screen.findByText('Completed')).toBeInTheDocument();
    expect(api.getDayStats).toHaveBeenCalledWith(toISODate(new Date()));
    expect(screen.getByText('Today')).toBeInTheDocument();

    expect(screen.getByTestId('day-completed').textContent).toContain('2 / 3');
    expect(screen.getByTestId('day-rate').textContent).toContain('66.67%');
    expect(screen.getByText('+1 completed early / overdue-cleared')).toBeInTheDocument();
    expect(screen.getByText('On Time')).toBeInTheDocument();
    expect(screen.getByText('Overdue')).toBeInTheDocument();
    expect(screen.getByText('Uncompleted')).toBeInTheDocument();

    expect(screen.getByText('Classified Completion Statistics')).toBeInTheDocument();
    expect(screen.getByText('Mission')).toBeInTheDocument();
    expect(screen.getByText('Habit')).toBeInTheDocument();

    fireEvent.click(screen.getByText('TAG'));
    expect(screen.getByText('phantom-1')).toBeInTheDocument();
    expect(screen.getByText('untagged')).toBeInTheDocument();
  });

  it('DAY tab navigates dates and calls the API with the new date', async () => {
    render(<StatsPanel />);
    fireEvent.click(screen.getByTestId('stats-tab-day'));
    await screen.findByText('Completed');

    fireEvent.click(screen.getByText('←'));
    const yesterday = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate() - 1);
    await waitFor(() => expect(api.getDayStats).toHaveBeenCalledWith(toISODate(yesterday)));
    expect(screen.queryByText('Today')).not.toBeInTheDocument();
  });

  it('DAY tab shows empty message when nothing is scheduled', async () => {
    api.getDayStats.mockResolvedValue({
      date: toISODate(new Date()),
      completed_count: 0,
      total_count: 0,
      completion_rate: 0.0,
      status_distribution: { on_time: 0, overdue: 0, uncompleted: 0 },
      type_distribution: [],
      tag_distribution: [],
    });

    render(<StatsPanel />);
    fireEvent.click(screen.getByTestId('stats-tab-day'));
    expect(await screen.findByText('Nothing scheduled this day.')).toBeInTheDocument();
  });

  it('RECORDS tab groups sessions by date', async () => {
    render(<StatsPanel />);
    fireEvent.click(screen.getByTestId('stats-tab-records'));

    expect(await screen.findByText('AUG 20')).toBeInTheDocument();
    expect(screen.getByText('AUG 19')).toBeInTheDocument();
    expect(
      screen.getByText((content, el) => el.tagName === 'SPAN' && content.includes('06:23') && content.includes('25m')),
    ).toBeInTheDocument();
    expect(screen.getByText('Ship PHANTOM-1 auth module')).toBeInTheDocument();
    expect(
      screen.getByText((content, el) => el.tagName === 'SPAN' && content.includes('06:00') && content.includes('30m')),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Unassigned').length).toBeGreaterThan(0);
    expect(screen.getByText('Showing 2 of 12 sessions')).toBeInTheDocument();
  });
});