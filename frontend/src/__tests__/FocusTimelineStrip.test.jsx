import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import FocusTimelineStrip from '../components/FocusTimelineStrip';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getFocusDay: vi.fn(),
  },
}));

const session = (over = {}) => ({
  id: 1,
  type: 'mission',
  name: 'Read Kahf surah',
  start_minute: 540,
  end_minute: 585,
  minutes: 45,
  mode: null,
  logged_manually: false,
  running: false,
  ...over,
});

const focusDay = (over = {}) => ({
  date: '2026-11-20',
  now_minute: null,
  total_minutes: 0,
  sessions: [],
  ...over,
});

const renderStrip = (day = '2026-11-20') => render(<FocusTimelineStrip day={day} />);

beforeEach(() => {
  vi.clearAllMocks();
  api.getFocusDay.mockResolvedValue(focusDay());
});

describe('placing a focus block on the day', () => {
  it('positions and sizes a block from its start and end minutes', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({
      total_minutes: 45,
      sessions: [session({ id: 7, start_minute: 540, end_minute: 585, minutes: 45 })],
    }));
    renderStrip();

    const block = await screen.findByTestId('focus-block-7');
    expect(block.style.left).toBe('37.5%');
    expect(block.style.width).toBe('3.125%');
  });

  it('keeps a very short session visible without changing its stated duration', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({
      total_minutes: 3,
      sessions: [session({ id: 8, start_minute: 600, end_minute: 603, minutes: 3 })],
    }));
    renderStrip();

    const block = await screen.findByTestId('focus-block-8');
    expect(block.style.minWidth).toBe('3px');
    expect(block.getAttribute('title')).toContain('3m');
  });

  it('names the block and its duration in the tooltip and accessible label', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({
      total_minutes: 80,
      sessions: [session({ id: 9, name: 'Deep work', start_minute: 60, end_minute: 140, minutes: 80 })],
    }));
    renderStrip();

    const block = await screen.findByTestId('focus-block-9');
    expect(block.getAttribute('title')).toBe('Deep work · 1h 20m');
    expect(block.getAttribute('aria-label')).toContain('Deep work · 1h 20m');
  });
});

describe('the now marker', () => {
  it('draws no now line when the server says it is not today', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({ now_minute: null }));
    renderStrip();

    await screen.findByTestId('focus-track');
    expect(screen.queryByTestId('now-line')).toBeNull();
  });

  it('draws a now line when now_minute is a number', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({ now_minute: 845 }));
    renderStrip();

    const line = await screen.findByTestId('now-line');
    expect(line.style.left).toBe(`${(845 / 1440) * 100}%`);
  });
});

describe('a day with nothing logged', () => {
  it('still renders the track and every hour tick', async () => {
    api.getFocusDay.mockResolvedValue(focusDay({ sessions: [], total_minutes: 0 }));
    renderStrip();

    await screen.findByTestId('focus-track');
    expect(screen.getAllByTestId('focus-hour-tick')).toHaveLength(24);
    expect(screen.getByTestId('focus-empty')).toBeTruthy();
  });
});

describe('when the day cannot be loaded', () => {
  it('shows a message instead of an empty box', async () => {
    api.getFocusDay.mockRejectedValue(new Error('focus day unavailable'));
    renderStrip();

    expect(await screen.findByText('focus day unavailable')).toBeTruthy();
  });
});
