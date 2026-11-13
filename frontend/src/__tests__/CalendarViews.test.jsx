import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import TimelineView from '../components/TimelineView';
import AgendaView from '../components/AgendaView';
import { addDays, startOfWeek, weekOf } from '../utils/calendarDays';

/**
 * Day, 3 Days and Week are one component with a different column count,
 * because seven separate calendar views would be seven places for the
 * same off-by-one. Agenda is the other shape: only what exists, in the
 * order it happens.
 */

const BASE = new Date(2026, 10, 13);          // Friday 13 November 2026
const at = (dayOffset, h, m = 0) =>
  new Date(2026, 10, 13 + dayOffset, h, m).toISOString();

const EVENTS = [
  { id: 1, title: 'Standup', start_time: at(0, 9), end_time: at(0, 9, 30) },
  { id: 2, title: 'Project call', start_time: at(0, 14), end_time: at(0, 15) },
  { id: 3, title: 'Tomorrow thing', start_time: at(1, 10), end_time: at(1, 11) },
];
const MISSIONS = { 0: [{ id: 7, title: 'Pay the invoice' }] };

const sameDay = (a, b) => a.toDateString() === b.toDateString();
const eventsForDay = (d) => EVENTS.filter((e) => sameDay(new Date(e.start_time), d));
const missionsForDay = (d) =>
  MISSIONS[Math.round((d - BASE) / 86400000)] || [];

const renderTimeline = (count, over = {}) => {
  const props = {
    days: count === 7
      ? weekOf(BASE)
      : Array.from({ length: count }, (_, i) => addDays(BASE, i)),
    events: EVENTS,
    eventsForDay,
    missionsForDay,
    onEditEvent: vi.fn(),
    onAddEvent: vi.fn(),
    onOpenDay: vi.fn(),
    ...over,
  };
  render(<TimelineView {...props} />);
  return props;
};

beforeEach(() => vi.clearAllMocks());

describe('One timeline, any number of days', () => {
  it('draws one column per day', () => {
    renderTimeline(3);
    // One "open this day" button per column.
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(3);
  });

  it('a single day is the same component with one column', () => {
    renderTimeline(1);
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(1);
  });

  it('a week is Monday to Sunday, not the next seven days', () => {
    // BASE is a Friday. A rolling week would start there.
    const days = weekOf(BASE);
    expect(days).toHaveLength(7);
    expect(days[0].getDay()).toBe(1);
    expect(days[6].getDay()).toBe(0);
    expect(days[0].getDate()).toBe(9);
  });

  it('puts an event in the hour it starts', () => {
    renderTimeline(1);
    expect(screen.getByRole('button', { name: 'Edit "Standup"' })).toBeTruthy();
    // 09:00 is taken, so it is no longer an empty add target.
    expect(screen.queryByRole('button', { name: /at 09:00/i })).toBeNull();
    expect(screen.getByRole('button', { name: /at 10:00/i })).toBeTruthy();
  });

  it('shows the time range on the block', () => {
    renderTimeline(1);
    expect(screen.getByText('09:00–09:30')).toBeTruthy();
  });

  it('keeps each day to its own column', () => {
    renderTimeline(3);
    // Tomorrow's event is present, today's too — and neither is duplicated.
    expect(screen.getAllByRole('button', { name: 'Edit "Tomorrow thing"' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Edit "Standup"' })).toHaveLength(1);
  });

  it('an empty hour adds an event at that day and hour', () => {
    const { onAddEvent, days } = renderTimeline(3);
    fireEvent.click(screen.getByRole('button', {
      name: new RegExp(`Add an event on ${days[1].toLocaleDateString()} at 11:00`),
    }));
    expect(onAddEvent).toHaveBeenCalledWith(days[1], 11);
  });

  it('an event opens for editing', () => {
    const { onEditEvent } = renderTimeline(1);
    fireEvent.click(screen.getByRole('button', { name: 'Edit "Standup"' }));
    expect(onEditEvent).toHaveBeenCalledWith(EVENTS[0]);
  });

  it('missions sit above the clock, not inside an hour', () => {
    renderTimeline(1);
    const due = screen.getByTitle(/Mission due: Pay the invoice/i);
    expect(due).toBeTruthy();
  });

  it('no due strip at all when nothing is due', () => {
    renderTimeline(1, { missionsForDay: () => [] });
    expect(screen.queryByText('Due')).toBeNull();
  });

  it('the day heading opens that day', () => {
    const { onOpenDay, days } = renderTimeline(3);
    fireEvent.click(screen.getByRole('button', {
      name: `Open ${days[2].toLocaleDateString()}`,
    }));
    expect(onOpenDay).toHaveBeenCalledWith(days[2]);
  });
});

describe('Agenda shows only what exists', () => {
  const renderAgenda = (over = {}) => {
    const props = {
      from: BASE,
      eventsForDay,
      missionsForDay,
      onEditEvent: vi.fn(),
      onFocusOn: vi.fn(),
      onOpenDay: vi.fn(),
      ...over,
    };
    render(<AgendaView {...props} />);
    return props;
  };

  it('leaves out days with nothing in them', () => {
    renderAgenda();
    // The 13th and 14th have things; the 15th onward do not.
    expect(screen.getByText('13')).toBeTruthy();
    expect(screen.getByText('14')).toBeTruthy();
    expect(screen.queryByText('16')).toBeNull();
  });

  it('orders a day by time', () => {
    renderAgenda();
    const labels = screen.getAllByRole('button', { name: /^Edit "/ })
      .map((b) => b.getAttribute('aria-label'));
    expect(labels).toEqual(['Edit "Standup"', 'Edit "Project call"', 'Edit "Tomorrow thing"']);
  });

  it('a mission can be focused straight from the agenda', () => {
    const { onFocusOn } = renderAgenda();
    fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    expect(onFocusOn).toHaveBeenCalledWith(7);
  });

  it('says so when there is nothing ahead at all', () => {
    renderAgenda({ eventsForDay: () => [], missionsForDay: () => [] });
    expect(screen.getByText(/nothing in the next 30 days/i)).toBeTruthy();
  });

  it('an event opens for editing', () => {
    const { onEditEvent } = renderAgenda();
    fireEvent.click(screen.getByRole('button', { name: 'Edit "Standup"' }));
    expect(onEditEvent).toHaveBeenCalledWith(EVENTS[0]);
  });
});

describe('Week arithmetic', () => {
  it('a Monday is the first day of its own week', () => {
    expect(startOfWeek(new Date(2026, 10, 9)).getDate()).toBe(9);
  });

  it('a Sunday belongs to the week it ends', () => {
    expect(startOfWeek(new Date(2026, 10, 15)).getDate()).toBe(9);
  });

  it('crosses a month boundary without losing a day', () => {
    const days = weekOf(new Date(2026, 11, 2));   // Wed 2 Dec 2026
    expect(days[0].getDate()).toBe(30);
    expect(days[0].getMonth()).toBe(10);
    expect(days[6].getDate()).toBe(6);
    expect(days[6].getMonth()).toBe(11);
  });
});
