import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import DayView from '../components/DayView';

/**
 * DayView on its own terms.
 *
 * CalendarPanel happens to hand it events already sorted, which means its
 * own ordering is invisible through that route — a mutation removing the
 * sort left every integration test green. A component's contract should
 * hold whoever calls it, so it is tested directly here.
 */

const DAY = new Date(2026, 10, 10);
const at = (h, m = 0) => new Date(2026, 10, 10, h, m).toISOString();

const renderDay = (over = {}) => {
  const props = {
    day: DAY,
    events: [],
    missions: [],
    onClose: vi.fn(),
    onEditEvent: vi.fn(),
    onAddEvent: vi.fn(),
    onFocusOn: vi.fn(),
    onRescheduleMission: vi.fn(),
    ...over,
  };
  render(<DayView {...props} />);
  return props;
};

beforeEach(() => vi.clearAllMocks());

describe('Ordering', () => {
  it('puts events in time order whatever order it is given them', () => {
    renderDay({
      events: [
        { id: 2, title: 'Later', start_time: at(9, 45) },
        { id: 1, title: 'Earlier', start_time: at(9, 5) },
      ],
    });
    const labels = screen.getAllByRole('button', { name: /^Edit "/ })
      .map((b) => b.getAttribute('aria-label'));
    expect(labels).toEqual(['Edit "Earlier"', 'Edit "Later"']);
  });

  it('files an event under the hour it starts in', () => {
    renderDay({ events: [{ id: 1, title: 'Call', start_time: at(14, 30) }] });
    // 14:00 has the event, so it is no longer an empty add target.
    expect(screen.queryByRole('button', { name: /add an event at 14:00/i })).toBeNull();
    expect(screen.getByRole('button', { name: /add an event at 13:00/i })).toBeTruthy();
  });
});

describe('What each thing offers', () => {
  it('an event opens for editing', () => {
    const e = { id: 1, title: 'Standup', start_time: at(9) };
    const { onEditEvent } = renderDay({ events: [e] });
    fireEvent.click(screen.getByRole('button', { name: 'Edit "Standup"' }));
    expect(onEditEvent).toHaveBeenCalledWith(e);
  });

  it('a mission can be focused', () => {
    const { onFocusOn } = renderDay({ missions: [{ id: 7, title: 'Pay the invoice' }] });
    fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    expect(onFocusOn).toHaveBeenCalledWith(7);
  });

  it('a mission can be moved to another day', () => {
    const { onRescheduleMission } = renderDay({
      missions: [{ id: 7, title: 'Pay the invoice' }],
    });
    fireEvent.click(screen.getByRole('button', { name: /move "pay the invoice"/i }));
    fireEvent.change(screen.getByLabelText(/new date for "pay the invoice"/i),
      { target: { value: '2026-12-01' } });
    expect(onRescheduleMission).toHaveBeenCalledWith(7, '2026-12-01');
  });

  it('an empty hour is where a new event goes', () => {
    const { onAddEvent } = renderDay();
    fireEvent.click(screen.getByRole('button', { name: /add an event at 14:00/i }));
    expect(onAddEvent).toHaveBeenCalledWith(DAY, 14);
  });

  it('the header button adds at nine, the ordinary working hour', () => {
    const { onAddEvent } = renderDay();
    fireEvent.click(screen.getByRole('button', { name: /^event$/i }));
    expect(onAddEvent).toHaveBeenCalledWith(DAY, 9);
  });

  it('offers no focus action when nothing is wired to it', () => {
    renderDay({ missions: [{ id: 7, title: 'Pay the invoice' }], onFocusOn: undefined });
    expect(screen.queryByRole('button', { name: /focus on/i })).toBeNull();
    expect(screen.getByText('Due this day')).toBeTruthy();
  });
});

describe('A day with nothing and a day with plenty', () => {
  it('still shows the hours when the day is empty', () => {
    renderDay();
    expect(screen.queryByText('Due this day')).toBeNull();
    expect(screen.getByRole('button', { name: /add an event at 00:00/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /add an event at 23:00/i })).toBeTruthy();
  });

  it('shows all of them, however many there are', () => {
    renderDay({
      events: Array.from({ length: 9 }, (_, i) => ({
        id: i + 1, title: `Event ${i + 1}`, start_time: at(8 + i),
      })),
      missions: Array.from({ length: 4 }, (_, i) => ({ id: 100 + i, title: `Mission ${i + 1}` })),
    });
    expect(screen.getAllByRole('button', { name: /^Edit "/ })).toHaveLength(9);
    expect(screen.getAllByRole('button', { name: /^Move "/ })).toHaveLength(4);
  });

  it('counts what is in the day', () => {
    renderDay({
      events: [{ id: 1, title: 'One', start_time: at(9) }],
      missions: [{ id: 7, title: 'Pay the invoice' }],
    });
    const dialog = screen.getByRole('dialog', { name: /day view/i });
    expect(within(dialog).getByText(/1 event · 1 due/i)).toBeTruthy();
  });
});

describe('Getting out', () => {
  it('closes on Escape', () => {
    const { onClose } = renderDay();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('closes on a click outside, but not on one inside', () => {
    const { onClose } = renderDay({ events: [{ id: 1, title: 'Standup', start_time: at(9) }] });
    fireEvent.click(screen.getByRole('dialog', { name: /day view/i }));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('presentation'));
    expect(onClose).toHaveBeenCalled();
  });
});
