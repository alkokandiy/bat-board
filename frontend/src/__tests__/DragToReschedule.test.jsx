import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import CalendarPanel from '../components/CalendarPanel';
import DayView from '../components/DayView';
import { api } from '../utils/api';

/**
 * Drag to reschedule.
 *
 * These tests stub `fetch` rather than mocking the api module, on purpose:
 * the whole point of a move is what goes over the wire. The server keeps
 * an event's duration and a mission's time of day, so the one thing that
 * must never happen is the client sending an end it computed for itself —
 * and only a body assertion can prove it never does.
 */

const at = (day, h, m = 0) => new Date(2026, 10, day, h, m).toISOString();
const DAY = new Date(2026, 10, 3, 9, 0);          // the fixed "today": Tue 3 Nov 2026

let calls;

const makeFetch = ({ events, missions, failMove } = {}) => {
  let serverEvents = (events || [
    { id: 1, title: 'Dentist', start_time: at(10, 14, 5), end_time: null, color: '#eab308' },
  ]).map((e) => ({ ...e }));
  const serverMissions = missions || [
    { id: 7, title: 'Pay the invoice', status: 'pending', due_date: '2026-11-10T00:00:00Z' },
  ];
  const json = (data) => ({ ok: true, status: 200, json: () => Promise.resolve(data) });
  return vi.fn(async (url, init = {}) => {
    const path = String(url);
    const method = init.method || 'GET';
    calls.push({ path, method, body: init.body ? JSON.parse(init.body) : null });

    const eventMove = path.match(/\/calendar\/events\/(\d+)\/move$/);
    if (eventMove && method === 'POST') {
      if (failMove) return { ok: false, status: 404, json: () => Promise.resolve({ detail: 'Event not found' }) };
      // The server keeps the duration; here it just re-dates the start,
      // which is enough for the client's refresh to be observable.
      const id = Number(eventMove[1]);
      serverEvents = serverEvents.map((e) => (e.id === id
        ? { ...e, start_time: JSON.parse(init.body).start_time } : e));
      return json(serverEvents[0]);
    }
    const missionMove = path.match(/\/missions\/(\d+)\/move$/);
    if (missionMove && method === 'POST') {
      if (failMove) return { ok: false, status: 404, json: () => Promise.resolve({ detail: 'Mission not found' }) };
      return json(serverMissions[0]);
    }
    if (method === 'GET' && path.includes('/calendar/events')) return json(serverEvents);
    if (method === 'GET' && path.includes('/missions')) return json(serverMissions);
    throw new Error(`unexpected call: ${method} ${path}`);
  });
};

const moves = () => calls.filter((c) => c.method === 'POST' && c.path.endsWith('/move'));

// Locale-proof: the grid writes its labels with toLocaleDateString, which
// may be 11/20/2026 or 20/11/2026.
const cellFor = (month, day) => screen.getAllByRole('button', { name: /^Open / })
  .find((b) => {
    const label = b.getAttribute('aria-label') || '';
    return label.includes(`${month}/${day}/2026`) || label.includes(`${day}/${month}/2026`);
  });

const renderPanel = (opts = {}) => {
  vi.stubGlobal('fetch', makeFetch(opts));
  const view = render(<CalendarPanel />);
  return view;
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.setSystemTime(DAY);
  calls = [];
});

afterEach(() => vi.unstubAllGlobals());

describe('the wire format', () => {
  it('moveEvent sends only a start time — never an end it computed itself', async () => {
    vi.stubGlobal('fetch', makeFetch());
    await api.moveEvent(1, '2026-11-20T14:00:00Z');
    const move = moves()[0];
    expect(move.path).toContain('/calendar/events/1/move');
    expect(Object.keys(move.body)).toEqual(['start_time']);
  });

  it('moveMission sends only a plain YYYY-MM-DD day', async () => {
    vi.stubGlobal('fetch', makeFetch());
    await api.moveMission(7, '2026-11-21');
    const move = moves()[0];
    expect(move.path).toContain('/missions/7/move');
    expect(move.body).toEqual({ day: '2026-11-21' });
  });
});

describe('dragging in the month grid', () => {
  it('drops an event on another day at the clock time it already had', async () => {
    const { container } = renderPanel();
    const chip = await screen.findByTitle('Dentist');

    fireEvent.dragStart(chip);
    const target = cellFor(11, 20);
    fireEvent.drop(target);

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0].path).toContain('/calendar/events/1/move');
    // 14:05 stays 14:05 — only the day changes.
    expect(moves()[0].body).toEqual({ start_time: at(20, 14, 5) });
  });

  it('redraws from the server after a move, and the event lands where the server said', async () => {
    renderPanel();
    const chip = await screen.findByTitle('Dentist');

    fireEvent.dragStart(chip);
    fireEvent.drop(cellFor(11, 20));

    await waitFor(() => {
      const moved = cellFor(11, 20)?.querySelector('[title="Dentist"]');
      expect(moved).toBeTruthy();
    });
    // The old cell no longer draws it, and the server was asked twice.
    expect(cellFor(11, 10).querySelector('[title="Dentist"]')).toBeNull();
    expect(calls.filter((c) => c.method === 'GET' && c.path.includes('/calendar/events')))
      .toHaveLength(2);
  });

  it('does not call the API when the item is dropped back on its own day', async () => {
    renderPanel();
    const chip = await screen.findByTitle('Dentist');

    fireEvent.dragStart(chip);
    fireEvent.dragOver(cellFor(11, 10));
    fireEvent.drop(cellFor(11, 10));

    expect(moves()).toHaveLength(0);
  });

  it('drops a mission on another day as a plain date string', async () => {
    renderPanel();
    const chip = await screen.findByRole('button', { name: /mission due: pay the invoice/i });

    fireEvent.dragStart(chip);
    fireEvent.drop(cellFor(11, 20));

    await waitFor(() => expect(moves()).toHaveLength(1));
    // Asserted exactly: a datetime or a converted day is the bug here.
    expect(moves()[0].path).toContain('/missions/7/move');
    expect(moves()[0].body).toEqual({ day: '2026-11-20' });
  });

  it('does not move a mission dropped back on the day it is due', async () => {
    renderPanel();
    const chip = await screen.findByRole('button', { name: /mission due: pay the invoice/i });

    fireEvent.dragStart(chip);
    fireEvent.drop(cellFor(11, 10));

    expect(moves()).toHaveLength(0);
  });

  it('highlights the cell under the drag, and clears it on leave', async () => {
    renderPanel();
    const chip = await screen.findByTitle('Dentist');
    const target = cellFor(11, 20);

    fireEvent.dragStart(chip);
    fireEvent.dragOver(target);
    expect(target).toHaveAttribute('data-drop-target', 'true');

    fireEvent.dragLeave(target);
    expect(target).not.toHaveAttribute('data-drop-target');
  });

  it('clears the highlight after a drop', async () => {
    renderPanel();
    const chip = await screen.findByTitle('Dentist');
    const target = cellFor(11, 20);

    fireEvent.dragStart(chip);
    fireEvent.dragOver(target);
    fireEvent.drop(target);
    await waitFor(() => expect(moves()).toHaveLength(1));

    expect(target).not.toHaveAttribute('data-drop-target');
  });

  it('a failed move says so and leaves the board exactly as it was', async () => {
    renderPanel({ failMove: true });
    const chip = await screen.findByTitle('Dentist');

    fireEvent.dragStart(chip);
    fireEvent.drop(cellFor(11, 20));

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found');
    // The chip never moved: the board was drawn from the server before and
    // is still drawn from it now.
    expect(cellFor(11, 10).querySelector('[title="Dentist"]')).toBeTruthy();
    expect(cellFor(11, 20).querySelector('[title="Dentist"]')).toBeNull();
    // And a failed move does not pretend to refresh.
    expect(calls.filter((c) => c.method === 'GET' && c.path.includes('/calendar/events')))
      .toHaveLength(1);
  });

  it('a failed mission move says so too', async () => {
    renderPanel({ failMove: true });
    const chip = await screen.findByRole('button', { name: /mission due: pay the invoice/i });

    fireEvent.dragStart(chip);
    fireEvent.drop(cellFor(11, 20));

    expect(await screen.findByRole('alert')).toHaveTextContent('Mission not found');
    expect(moves()).toHaveLength(1);
  });

  it('clicking an event still opens the edit dialog — the drag handlers do not swallow it', async () => {
    renderPanel();
    const chip = await screen.findByTitle('Dentist');

    fireEvent.click(chip);

    expect(await screen.findByRole('dialog', { name: 'Edit event' })).toBeTruthy();
    expect(screen.getByLabelText('Starts').value).toMatch(/T14:05$/);
    expect(moves()).toHaveLength(0);
  });

  it('clicking a mission still opens the day, as before', async () => {
    renderPanel();
    const chip = await screen.findByRole('button', { name: /mission due: pay the invoice/i });

    fireEvent.click(chip);

    expect(await screen.findByRole('dialog', { name: /day view/i })).toBeTruthy();
  });
});

describe('dragging in the timeline', () => {
  // A week that contains the fixed today: Mon 2 Nov – Sun 8 Nov 2026.
  const thursday = new Date(2026, 10, 5);
  const friday = new Date(2026, 10, 6);

  const openWeek = async (over = {}) => {
    const { container } = renderPanel({
      events: [{ id: 1, title: 'Dentist', start_time: at(5, 14, 5), end_time: at(5, 15, 5), color: '#eab308' }],
      ...over,
    });
    // The grid chip appears once the events have loaded; switching view
    // before that would race the fetch.
    await screen.findByTitle('Dentist');
    fireEvent.click(screen.getByRole('button', { name: /^week$/i }));
    // The event chip in its hour row — not the "Upcoming" strip's button,
    // which carries the same accessible name.
    const chipIn = (day, hour) => container
      .querySelector(`[data-cell-day="${day.toDateString()}"][data-cell-hour="${hour}"]`)
      .querySelector('button');
    expect(chipIn(thursday, 14)).toBeTruthy();
    return { container, chipIn };
  };

  it('drops an event on an hour row of another day at the whole hour', async () => {
    const { container, chipIn } = await openWeek();

    fireEvent.dragStart(chipIn(thursday, 14));
    const target = container.querySelector(
      `[data-cell-day="${friday.toDateString()}"][data-cell-hour="9"]`);
    expect(target, 'the Friday 09:00 cell should exist').toBeTruthy();
    fireEvent.drop(target);

    await waitFor(() => expect(moves()).toHaveLength(1));
    // Friday at 09:00 exactly — minutes are not carried over to an hour row.
    expect(moves()[0].body).toEqual({ start_time: at(6, 9, 0) });
  });

  it('does not call the API when dropped back on its own hour', async () => {
    const { container, chipIn } = await openWeek();

    fireEvent.dragStart(chipIn(thursday, 14));
    fireEvent.drop(container.querySelector(
      `[data-cell-day="${thursday.toDateString()}"][data-cell-hour="14"]`));

    expect(moves()).toHaveLength(0);
  });

  it('highlights the hour cell under the drag, and clears it on leave', async () => {
    const { container, chipIn } = await openWeek();
    const target = container.querySelector(
      `[data-cell-day="${friday.toDateString()}"][data-cell-hour="9"]`);

    fireEvent.dragStart(chipIn(thursday, 14));
    fireEvent.dragOver(target);
    expect(target).toHaveAttribute('data-drop-target', 'true');

    fireEvent.dragLeave(target);
    expect(target).not.toHaveAttribute('data-drop-target');
  });
});

describe('dragging inside the day view', () => {
  it('drops an event on another hour row and reports the hour', async () => {
    const onMoveEventToHour = vi.fn();
    const event = { id: 3, title: 'Call', start_time: at(10, 14, 5) };
    const { container } = render(
      <DayView
        day={new Date(2026, 10, 10)}
        events={[event]}
        onClose={() => {}}
        onEditEvent={() => {}}
        onAddEvent={() => {}}
        onMoveEventToHour={onMoveEventToHour}
      />);

    fireEvent.dragStart(screen.getByRole('button', { name: 'Edit "Call"' }));
    const row = container.querySelector('[data-hour="9"]');
    fireEvent.dragOver(row);
    expect(row).toHaveAttribute('data-drop-target', 'true');
    fireEvent.drop(row);

    expect(onMoveEventToHour).toHaveBeenCalledWith(event, 9);
    expect(row).not.toHaveAttribute('data-drop-target');
  });

  it('clicking an event still edits it', () => {
    const onEditEvent = vi.fn();
    const event = { id: 3, title: 'Call', start_time: at(10, 14, 5) };
    render(
      <DayView
        day={new Date(2026, 10, 10)}
        events={[event]}
        onClose={() => {}}
        onEditEvent={onEditEvent}
        onAddEvent={() => {}}
      />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit "Call"' }));
    expect(onEditEvent).toHaveBeenCalledWith(event);
  });

  it('dragging inside the day view never moves the event across a day', async () => {
    // The day view is one day wide: the panel resolves the drop against the
    // day that is open, so the wire call keeps that day.
    renderPanel();
    fireEvent.click(await cellFor(11, 10));        // open 10 November
    const dialog = await screen.findByRole('dialog', { name: /day view/i });
    // Scoped to the dialog: the Upcoming strip has a button of the same name.
    const chip = within(dialog).getByRole('button', { name: 'Edit "Dentist"' });

    fireEvent.dragStart(chip);
    fireEvent.drop(dialog.querySelector('[data-hour="9"]'));

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0].body).toEqual({ start_time: at(10, 9, 0) });
  });
});
