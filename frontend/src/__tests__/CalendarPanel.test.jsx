import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import CalendarPanel from '../components/CalendarPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getCalendarEvents: vi.fn(),
    getMissions: vi.fn(),
    createCalendarEvent: vi.fn(),
    updateCalendarEvent: vi.fn(),
    deleteCalendarEvent: vi.fn(),
    updateMission: vi.fn(),
  },
}));

// A fixed day inside the month under test, so the grid is predictable.
const iso = (day, hour = 10, month = 11, year = 2026) =>
  new Date(year, month - 1, day, hour, 0).toISOString();

const event = (over = {}) => ({
  id: 1,
  title: 'Dentist',
  description: null,
  start_time: iso(10),
  end_time: null,
  color: '#eab308',
  mission_id: null,
  ...over,
});

const settle = async () => {
  await waitFor(() => expect(api.getCalendarEvents).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.setSystemTime(new Date(2026, 10, 3, 9, 0));
  api.getCalendarEvents.mockResolvedValue([event()]);
  api.getMissions.mockResolvedValue([]);
  api.createCalendarEvent.mockResolvedValue(event());
  api.updateCalendarEvent.mockResolvedValue(event());
  api.deleteCalendarEvent.mockResolvedValue({});
});

describe('deleting an event', () => {
  // `handleDelete` was defined in this file and called from nowhere, so the
  // web app could not delete a calendar event at all — only Alfred could.
  it('is possible at all, from the event itself', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<CalendarPanel />);
    await settle();

    fireEvent.click(screen.getByRole('button', { name: 'Edit "Dentist"' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete "Dentist"' }));

    await waitFor(() => expect(api.deleteCalendarEvent).toHaveBeenCalledWith(1));
    confirmSpy.mockRestore();
  });

  it('asks first', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: 'Edit "Dentist"' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete "Dentist"' }));
    expect(api.deleteCalendarEvent).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe('an event that runs over several days', () => {
  // It used to be drawn only on the day it STARTED, so the days you were
  // actually busy looked free.
  it('appears on every day it covers', async () => {
    api.getCalendarEvents.mockResolvedValue([
      event({ title: 'Conference', start_time: iso(10, 9), end_time: iso(12, 17) }),
    ]);
    render(<CalendarPanel />);
    await settle();
    // 10th, 11th, 12th — three cells, one chip each.
    expect(screen.getAllByTitle('Conference').length).toBe(3);
  });

  it('does not bleed into the day after it ends', async () => {
    api.getCalendarEvents.mockResolvedValue([
      event({ title: 'Conference', start_time: iso(10, 9), end_time: iso(10, 17) }),
    ]);
    render(<CalendarPanel />);
    await settle();
    expect(screen.getAllByTitle('Conference').length).toBe(1);
  });
});

describe('a busy day', () => {
  // The overflow count only appeared above eight items and subtracted eight,
  // while the cell drew at most four of each kind. Five missions and nothing
  // else therefore hid one in complete silence.
  it('counts everything it could not draw', async () => {
    api.getMissions.mockResolvedValue(
      Array.from({ length: 5 }, (_, i) => ({
        id: i + 1, title: `Mission ${i + 1}`, status: 'pending', due_date: '2026-11-10T00:00:00Z',
      })));
    api.getCalendarEvents.mockResolvedValue([]);
    render(<CalendarPanel />);
    await settle();
    expect(screen.getByText('+2 more')).toBeTruthy();
  });

  it('says nothing when everything fits', async () => {
    api.getMissions.mockResolvedValue([
      { id: 1, title: 'Only one', status: 'pending', due_date: '2026-11-10T00:00:00Z' },
    ]);
    api.getCalendarEvents.mockResolvedValue([]);
    render(<CalendarPanel />);
    await settle();
    expect(screen.queryByText(/more$/)).toBeNull();
  });
});

describe('the form', () => {
  it('refuses an end before the start, without a round trip', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /New event/i }));

    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'Backwards' } });
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-11-10T12:00' } });
    fireEvent.change(screen.getByLabelText(/^Ends/), { target: { value: '2026-11-10T09:00' } });
    fireEvent.click(screen.getByRole('button', { name: /Add event/i }));

    expect(await screen.findByText('An event cannot end before it starts.')).toBeTruthy();
    expect(api.createCalendarEvent).not.toHaveBeenCalled();
  });

  it('accepts an event with no end at all', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /New event/i }));
    fireEvent.change(screen.getByLabelText('What is it'), { target: { value: 'A moment' } });
    fireEvent.click(screen.getByRole('button', { name: /Add event/i }));
    await waitFor(() => expect(api.createCalendarEvent).toHaveBeenCalled());
    expect(api.createCalendarEvent.mock.calls[0][0].end_time).toBeNull();
  });

  // A clicked day is literally midnight, and nobody means 00:00.
  it('defaults the day view\'s Event button to nine in the morning', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getAllByRole('button', { name: /^Open / })[0]);
    fireEvent.click(screen.getByRole('button', { name: /^event$/i }));
    expect(screen.getByLabelText('Starts').value).toMatch(/T09:00$/);
  });

  it('takes the hour from the row that was pointed at', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getAllByRole('button', { name: /^Open / })[0]);
    fireEvent.click(screen.getByRole('button', { name: /add an event at 14:00/i }));
    expect(screen.getByLabelText('Starts').value).toMatch(/T14:00$/);
  });

  it('closes on Escape', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /New event/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('"upcoming" means upcoming', () => {
  it('leaves out what has already finished', async () => {
    api.getCalendarEvents.mockResolvedValue([
      event({ id: 1, title: 'Last month', start_time: iso(10, 10, 10) }),
      event({ id: 2, title: 'Later', start_time: iso(20) }),
    ]);
    render(<CalendarPanel />);
    await settle();
    expect(screen.getByRole('button', { name: 'Edit "Later"' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Edit "Last month"' })).toBeNull();
  });

  it('keeps one that is running right now', async () => {
    api.getCalendarEvents.mockResolvedValue([
      event({ title: 'In progress', start_time: iso(3, 8), end_time: iso(3, 18) }),
    ]);
    render(<CalendarPanel />);
    await settle();
    expect(screen.getByRole('button', { name: 'Edit "In progress"' })).toBeTruthy();
  });
});

describe('Focus on a mission from the calendar', () => {
  const due = [{ id: 7, title: 'Pay the invoice', status: 'pending', due_date: '2026-11-10T00:00:00Z' }];

  it('opens the day rather than committing to one action', async () => {
    // A chip has one click to give. It used to start a focus session —
    // right when that is what you wanted, wrong every other time.
    const onFocusOn = vi.fn();
    api.getMissions.mockResolvedValue(due);
    api.getCalendarEvents.mockResolvedValue([]);
    render(<CalendarPanel onFocusOn={onFocusOn} />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /mission due: pay the invoice/i }));
    expect(onFocusOn).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: /day view/i })).toBeTruthy();
  });

  it('and focusing is then one more click, inside the day', async () => {
    const onFocusOn = vi.fn();
    api.getMissions.mockResolvedValue(due);
    api.getCalendarEvents.mockResolvedValue([]);
    render(<CalendarPanel onFocusOn={onFocusOn} />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /mission due: pay the invoice/i }));
    fireEvent.click(screen.getByRole('button', { name: /focus on "pay the invoice"/i }));
    expect(onFocusOn).toHaveBeenCalledWith(7);
  });

  it('can move a mission to another day from the calendar', async () => {
    // The one edit that belongs here: the calendar is where you see that a
    // due date lands badly.
    api.getMissions.mockResolvedValue(due);
    api.getCalendarEvents.mockResolvedValue([]);
    api.updateMission.mockResolvedValue({});
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /mission due: pay the invoice/i }));
    fireEvent.click(screen.getByRole('button', { name: /move "pay the invoice" to another day/i }));
    fireEvent.change(screen.getByLabelText(/new date for "pay the invoice"/i),
      { target: { value: '2026-11-20' } });
    await waitFor(() => expect(api.updateMission).toHaveBeenCalledWith(
      7, { due_date: '2026-11-20T00:00:00Z' }));
  });

  it('still shows the mission when no focus handler is wired', async () => {
    api.getMissions.mockResolvedValue(due);
    api.getCalendarEvents.mockResolvedValue([]);
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: /mission due: pay the invoice/i }));
    expect(screen.queryByRole('button', { name: /focus on/i })).toBeNull();
    expect(screen.getByText('Due this day')).toBeTruthy();
  });
});

describe('A day with more than one thing in it', () => {
  const day = '2026-11-10';
  const at = (h, m = 0) => `${day}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`;

  // Scoped to the dialog: the "Upcoming" strip at the foot of the page uses
  // the same `Edit "X"` labels, so an unscoped query matches both and the
  // test fails for a reason that has nothing to do with the day view.
  const openTheDay = async () => {
    render(<CalendarPanel />);
    await settle();
    const cell = screen.getAllByRole('button', { name: /^Open / })
      .find(b => /11\/10\/2026|10\/11\/2026/.test(b.getAttribute('aria-label')));
    expect(cell, 'the 10th should be in the rendered month').toBeTruthy();
    fireEvent.click(cell);
    return within(screen.getByRole('dialog', { name: /day view/i }));
  };

  it('shows every event, not four and a count', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => ({
        id: i + 1, title: `Event ${i + 1}`, start_time: at(9 + i), end_time: null,
      })));
    const view = await openTheDay();
    for (let i = 1; i <= 6; i += 1) {
      expect(view.getByRole('button', { name: `Edit "Event ${i}"` })).toBeTruthy();
    }
  });

  it('keeps missions and events apart rather than in one stack', async () => {
    api.getMissions.mockResolvedValue([
      { id: 7, title: 'Pay the invoice', status: 'pending', due_date: `${day}T00:00:00Z` },
      { id: 8, title: 'Burn the papers', status: 'pending', due_date: `${day}T00:00:00Z` },
    ]);
    api.getCalendarEvents.mockResolvedValue([
      { id: 1, title: 'Standup', start_time: at(9), end_time: at(9, 30) },
    ]);
    const view = await openTheDay();
    expect(view.getByText('Due this day')).toBeTruthy();
    expect(view.getByRole('button', { name: /move "pay the invoice"/i })).toBeTruthy();
    expect(view.getByRole('button', { name: /move "burn the papers"/i })).toBeTruthy();
    expect(view.getByRole('button', { name: 'Edit "Standup"' })).toBeTruthy();
  });

  it('puts two events in the same hour in time order', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue([
      { id: 2, title: 'Later', start_time: at(9, 45), end_time: null },
      { id: 1, title: 'Earlier', start_time: at(9, 5), end_time: null },
    ]);
    const view = await openTheDay();
    const titles = view.getAllByRole('button', { name: /^Edit "/ })
      .map(b => b.getAttribute('aria-label'));
    expect(titles).toEqual(['Edit "Earlier"', 'Edit "Later"']);
  });

  it('says when an event starts and ends', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue([
      { id: 1, title: 'Standup', start_time: at(9), end_time: at(9, 30) },
    ]);
    const view = await openTheDay();
    expect(view.getByText('09:00–09:30')).toBeTruthy();
  });

  it('an hour that already has something is not an add target', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue([
      { id: 1, title: 'Standup', start_time: at(9), end_time: null },
    ]);
    const view = await openTheDay();
    expect(view.queryByRole('button', { name: /add an event at 09:00/i })).toBeNull();
    expect(view.getByRole('button', { name: /add an event at 10:00/i })).toBeTruthy();
  });

  it('editing an event from the day view opens the real form', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue([
      { id: 1, title: 'Standup', start_time: at(9), end_time: null },
    ]);
    const view = await openTheDay();
    fireEvent.click(view.getByRole('button', { name: 'Edit "Standup"' }));
    expect(screen.getByLabelText('Starts').value).toMatch(/T09:00$/);
    expect(screen.getByDisplayValue('Standup')).toBeTruthy();
  });

  it('closes on Escape', async () => {
    api.getMissions.mockResolvedValue([]);
    api.getCalendarEvents.mockResolvedValue([]);
    await openTheDay();
    expect(screen.getByRole('dialog', { name: /day view/i })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: /day view/i })).toBeNull());
  });
});

describe('Switching between the calendar views', () => {
  const pick = (name) => fireEvent.click(screen.getByRole('button', { name }));

  const open = async (events = [], missions = []) => {
    api.getMissions.mockResolvedValue(missions);
    api.getCalendarEvents.mockResolvedValue(events);
    render(<CalendarPanel />);
    await settle();
  };

  it('starts on the month grid', async () => {
    await open();
    // The weekday strip belongs to the month view alone.
    expect(screen.getByText('Mon')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Add an event on .* at /i })).toBeNull();
  });

  it('week shows hours instead of a grid of days', async () => {
    await open();
    pick(/^week$/i);
    expect(screen.getAllByRole('button', { name: /^Add an event on .* at /i }).length)
      .toBeGreaterThan(0);
  });

  it('day shows one column, week shows seven', async () => {
    await open();
    pick(/^day$/i);
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(1);
    pick(/^week$/i);
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(7);
  });

  it('3 days shows three', async () => {
    await open();
    pick(/^3 days$/i);
    expect(screen.getAllByRole('button', { name: /^Open / })).toHaveLength(3);
  });

  it('agenda says when there is nothing ahead', async () => {
    await open();
    pick(/^agenda$/i);
    expect(screen.getByText(/nothing in the next 30 days/i)).toBeTruthy();
  });

  it('the heading names what is on screen, not always a month', async () => {
    await open();
    pick(/^agenda$/i);
    // The Upcoming panel is an h2 as well, so take the calendar's own.
    const heading = () => screen.getAllByRole('heading', { level: 2 })[0].textContent;
    expect(heading()).toMatch(/next 30 days/i);
    pick(/^month$/i);
    expect(heading()).toMatch(/\d{4}$/);
  });

  it('back and forward move by the unit the view is made of', async () => {
    // Stepping a month while looking at three days would be a different
    // screen, not the next one.
    await open();
    pick(/^day$/i);
    const before = screen.getAllByRole('button', { name: /^Open / })[0]
      .getAttribute('aria-label');
    fireEvent.click(screen.getByRole('button', { name: /^forward$/i }));
    const after = screen.getAllByRole('button', { name: /^Open / })[0]
      .getAttribute('aria-label');
    expect(after).not.toBe(before);

    const day = (label) => Number(label.match(/(\d+)\/(\d+)\//)[2]);
    expect(Math.abs(day(after) - day(before))).toBe(1);
  });

  it('Today comes back to today from any view', async () => {
    await open();
    pick(/^week$/i);
    fireEvent.click(screen.getByRole('button', { name: /^forward$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^today$/i }));
    expect(screen.queryByRole('button', { name: /^today$/i })).toBeNull();
  });
});
