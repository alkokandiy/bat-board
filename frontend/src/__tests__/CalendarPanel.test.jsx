import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import CalendarPanel from '../components/CalendarPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    getCalendarEvents: vi.fn(),
    getMissions: vi.fn(),
    createCalendarEvent: vi.fn(),
    updateCalendarEvent: vi.fn(),
    deleteCalendarEvent: vi.fn(),
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
  it('defaults a day click to nine in the morning', async () => {
    render(<CalendarPanel />);
    await settle();
    fireEvent.click(screen.getAllByRole('button', { name: /Add an event on/ })[0]);
    expect(screen.getByLabelText('Starts').value).toMatch(/T09:00$/);
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
