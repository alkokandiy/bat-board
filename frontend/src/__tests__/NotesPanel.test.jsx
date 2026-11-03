import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import NotesPanel from '../components/NotesPanel';
import { api } from '../utils/api.js';

vi.mock('../utils/api.js', () => ({
  api: {
    getNotes: vi.fn(),
    createNote: vi.fn(),
    updateNote: vi.fn(),
    deleteNote: vi.fn(),
  },
}));

vi.mock('../utils/migrateLocalStorage.js', () => ({
  migrateOnce: vi.fn().mockResolvedValue(undefined),
}));

const note = (over = {}) => ({
  id: 1,
  title: 'Cold open',
  body: 'Something written here',
  category: null,
  is_pinned: false,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-02T10:00:00Z',
  ...over,
});

const settle = async () => {
  await waitFor(() => expect(api.getNotes).toHaveBeenCalled());
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getNotes.mockResolvedValue([note()]);
  api.createNote.mockResolvedValue(note({ id: 2, title: '', body: '' }));
  api.updateNote.mockResolvedValue(note());
  api.deleteNote.mockResolvedValue({});
});

describe('deleting a note', () => {
  // Reported as "can't delete these notes". The control was opacity-0 until
  // hover with no accessible name, so on a touch screen it did not exist.
  it('is reachable without hovering, and says which note it removes', async () => {
    render(<NotesPanel />);
    await settle();
    expect(screen.getByRole('button', { name: 'Delete "Cold open"' })).toBeTruthy();
  });

  it('asks first', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Cold open"' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.deleteNote).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('removes it on a yes', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Cold open"' }));
    await waitFor(() => expect(api.deleteNote).toHaveBeenCalledWith(1));
    expect(screen.queryByText('Cold open')).toBeNull();
    confirmSpy.mockRestore();
  });

  it('can also be done from the note you are reading', async () => {
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByText('Cold open'));
    // One in the list, one in the editor footer.
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: 'Delete "Cold open"' }).length).toBe(2));
  });
});

describe('the empty states say something useful', () => {
  it('does not greet an empty list with a film quote', async () => {
    api.getNotes.mockResolvedValue([]);
    render(<NotesPanel />);
    await settle();
    expect(screen.getByText('No notes yet')).toBeTruthy();
    expect(screen.queryByText(/night is darkest/i)).toBeNull();
  });

  it('names the search that found nothing', async () => {
    render(<NotesPanel />);
    await settle();
    fireEvent.change(screen.getByLabelText('Search notes'), { target: { value: 'zzz' } });
    expect(screen.getByText('Nothing matches "zzz"')).toBeTruthy();
  });
});

describe('editing', () => {
  afterEach(() => vi.useRealTimers());

  it('saves the body after a pause, not on every keystroke', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByText('Cold open'));
    fireEvent.change(screen.getByLabelText('Note body'), { target: { value: 'Rewritten' } });
    expect(api.updateNote).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(900); });
    await waitFor(() => expect(api.updateNote).toHaveBeenCalled());
    expect(api.updateNote.mock.calls[0][1].body).toBe('Rewritten');
  });

  // The API reads null as "leave unchanged", so an emptied field never saved.
  it('sends an emptied field as an empty string, not null', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByText('Cold open'));
    fireEvent.change(screen.getByLabelText('Note body'), { target: { value: '' } });
    await act(async () => { vi.advanceTimersByTime(900); });
    await waitFor(() => expect(api.updateNote).toHaveBeenCalled());
    expect(api.updateNote.mock.calls[0][1].body).toBe('');
  });

  it('counts the words of what is on screen', async () => {
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByText('Cold open'));
    expect(screen.getByText('3 words')).toBeTruthy();
  });
});

describe("Alfred's own notes", () => {
  it('are a separate set, reloaded when you switch', async () => {
    render(<NotesPanel />);
    await settle();
    fireEvent.click(screen.getByRole('button', { name: "Alfred's" }));
    await waitFor(() => expect(api.getNotes).toHaveBeenCalledWith('', '', 'alfred'));
  });

  // Not a correctness fix — the debounce holds the note in its own closure,
  // so the edit was never lost. It just went up to 800ms after you had
  // already moved on, which is 800ms in which a closed tab loses it.
  it('saves a half-typed edit immediately rather than after the debounce', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    render(<NotesPanel />);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByText('Cold open'));
    fireEvent.change(screen.getByLabelText('Note body'), { target: { value: 'Half typed' } });
    expect(api.updateNote).not.toHaveBeenCalled();

    // No timers advanced: the switch itself must do it.
    fireEvent.click(screen.getByRole('button', { name: "Alfred's" }));
    expect(api.updateNote).toHaveBeenCalledTimes(1);
    expect(api.updateNote.mock.calls[0][0]).toBe(1);
    expect(api.updateNote.mock.calls[0][1].body).toBe('Half typed');
    vi.useRealTimers();
  });
});
