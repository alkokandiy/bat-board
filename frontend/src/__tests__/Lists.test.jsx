import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import ListRail from '../components/ListRail';
import MissionsPanel, { blankMission } from '../components/MissionsPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    createMission: vi.fn(),
    updateMission: vi.fn(),
  },
}));

const list = (over = {}) => ({
  id: 5,
  name: 'Gotham',
  color: null,
  icon: null,
  position: 0,
  archived: false,
  created_at: '2026-01-01T00:00:00Z',
  open_missions: 3,
  ...over,
});

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
  list_id: null,
  is_pinned: false,
  is_dismissed: false,
  focus_minutes: 0,
  completed_focus_sessions: 0,
  ...over,
});

const todayKey = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T00:00:00Z`;
};

const renderRail = (over = {}) => {
  const handlers = {
    lists: [list()],
    archivedLists: [],
    counts: { inbox: 2, 5: 3 },
    selected: null,
    onSelect: vi.fn(),
    onCreate: vi.fn().mockResolvedValue(undefined),
    onRename: vi.fn().mockResolvedValue(undefined),
    onArchive: vi.fn().mockResolvedValue(undefined),
    onRestore: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
  render(<ListRail {...handlers} />);
  return handlers;
};

const renderPanel = (missions, over = {}) => {
  const onRefreshMissions = vi.fn().mockResolvedValue(undefined);
  const onRefreshAccount = vi.fn().mockResolvedValue(undefined);
  render(
    <MissionsPanel
      missions={missions}
      onRefreshMissions={onRefreshMissions}
      onRefreshAccount={onRefreshAccount}
      {...over}
    />,
  );
  return { onRefreshMissions };
};

beforeEach(() => {
  vi.clearAllMocks();
  api.createMission.mockResolvedValue({});
});

// This project's vitest setup has no automatic cleanup (the other suites
// query defensively instead), and these tests render twice per it() —
// so every leftover render would answer the next one's queries.
afterEach(cleanup);

describe('The rail', () => {
  it('renders All, the Inbox with its count, and the lists with theirs', () => {
    renderRail({
      lists: [list({ id: 5, name: 'Gotham', open_missions: 3 }), list({ id: 7, name: 'Bludhaven', open_missions: 1 })],
      counts: { inbox: 2, 5: 3, 7: 1 },
    });
    expect(screen.getByRole('button', { name: /^Gotham/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Bludhaven/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Inbox/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^All/ })).toBeTruthy();
    // Inbox count comes from the counts endpoint, list counts from the rows.
    const inbox = screen.getByRole('button', { name: /^Inbox/ });
    expect(within(inbox).getByText('2')).toBeTruthy();
    expect(within(screen.getByRole('button', { name: /^Bludhaven/ })).getByText('1')).toBeTruthy();
  });

  it('an empty list shows no badge rather than an emphatic zero', () => {
    renderRail({ lists: [list({ id: 5, name: 'Gotham', open_missions: 0 })], counts: { inbox: 0, 5: 0 } });
    expect(within(screen.getByRole('button', { name: /^Gotham/ })).queryByText('0')).toBeNull();
    expect(within(screen.getByRole('button', { name: /^Inbox/ })).queryByText('0')).toBeNull();
  });

  it('hands back a list id, the Inbox sentinel, and null for All', () => {
    const { onSelect } = renderRail();
    fireEvent.click(screen.getByRole('button', { name: /^Gotham/ }));
    expect(onSelect).toHaveBeenLastCalledWith(5);
    fireEvent.click(screen.getByRole('button', { name: /^Inbox/ }));
    expect(onSelect).toHaveBeenLastCalledWith('inbox');
    fireEvent.click(screen.getByRole('button', { name: /^All/ }));
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it('marks the selected row', () => {
    renderRail({ selected: 5 });
    expect(screen.getByRole('button', { name: /^Gotham/ }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: /^Inbox/ }).getAttribute('aria-pressed')).toBe('false');
  });

  it('creates a list from what was typed', async () => {
    const { onCreate } = renderRail();
    fireEvent.click(screen.getByRole('button', { name: /Add list/i }));
    fireEvent.change(screen.getByLabelText('New list name'), { target: { value: 'Wayne' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save list' }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('Wayne'));
  });

  it('archives and renames without leaving the rail', async () => {
    const { onArchive, onRename } = renderRail();
    fireEvent.click(screen.getByRole('button', { name: 'Archive "Gotham"' }));
    await waitFor(() => expect(onArchive).toHaveBeenCalledWith(5));
    fireEvent.click(screen.getByRole('button', { name: 'Rename "Gotham"' }));
    fireEvent.change(screen.getByLabelText('Rename list Gotham'), { target: { value: 'Batcave' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save name for "Gotham"' }));
    await waitFor(() => expect(onRename).toHaveBeenCalledWith(5, 'Batcave'));
  });

  it('deleting says where the missions go: the Inbox, not the void', async () => {
    const { onDelete } = renderRail();
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Gotham"' }));
    const note = screen.getByText(/missions move to the Inbox/i);
    expect(note).toBeTruthy();
    expect(note.textContent).toMatch(/nothing is deleted/i);

    // Confirming performs it; keeping does not.
    fireEvent.click(within(note.closest('div')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(5));
  });

  it('the confirmation can be declined and then nothing is sent', async () => {
    const { onDelete } = renderRail();
    fireEvent.click(screen.getByRole('button', { name: 'Delete "Gotham"' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByText(/missions move to the Inbox/i)).toBeNull();
  });

  it('shows the server\'s refusal, which is meant to be read', async () => {
    renderRail({ onCreate: vi.fn().mockRejectedValue(new Error('A list with that name already exists.')) });
    fireEvent.click(screen.getByRole('button', { name: /Add list/i }));
    fireEvent.change(screen.getByLabelText('New list name'), { target: { value: 'Gotham' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save list' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('A list with that name already exists.');
  });

  it('archived lists are kept visible for restoring, not vanished', async () => {
    const { onRestore } = renderRail({
      archivedLists: [list({ id: 9, name: 'Old case files', archived: true })],
    });
    fireEvent.click(screen.getByText(/Archived \(1\)/));
    fireEvent.click(screen.getByRole('button', { name: 'Restore "Old case files"' }));
    await waitFor(() => expect(onRestore).toHaveBeenCalledWith(9));
  });
});

describe('The list filter combines with the date filter', () => {
  it('both apply, not one instead of the other', () => {
    renderPanel(
      [
        mission({ id: 1, title: 'Gotham today', list_id: 5, due_date: todayKey() }),
        mission({ id: 2, title: 'Bludhaven today', list_id: 7, due_date: todayKey() }),
        mission({ id: 3, title: 'Gotham someday', list_id: 5 }),
      ],
      { lists: [list({ id: 5, name: 'Gotham' }), list({ id: 7, name: 'Bludhaven' })], selectedList: 5 },
    );
    // The list filter alone: everything in Gotham, nothing from Bludhaven.
    expect(screen.queryByText('Bludhaven today')).toBeNull();
    expect(screen.getByText('Gotham someday')).toBeTruthy();
    expect(screen.getByText('Gotham today')).toBeTruthy();

    // And the date filter still narrows on top of the list one.
    fireEvent.click(screen.getByRole('button', { name: 'Today' }));
    expect(screen.getByText('Gotham today')).toBeTruthy();
    expect(screen.queryByText('Gotham someday')).toBeNull();
  });

  it('Inbox means exactly the unfiled missions', () => {
    renderPanel(
      [
        mission({ id: 1, title: 'Unfiled' }),
        mission({ id: 2, title: 'Filed', list_id: 5 }),
      ],
      { lists: [list()], selectedList: 'inbox' },
    );
    expect(screen.getByText('Unfiled')).toBeTruthy();
    expect(screen.queryByText('Filed')).toBeNull();
  });

  it('no rail wired means everything, as before', () => {
    renderPanel([mission({ id: 1, title: 'Unfiled' }), mission({ id: 2, title: 'Filed', list_id: 5 })]);
    expect(screen.getByText('Unfiled')).toBeTruthy();
    expect(screen.getByText('Filed')).toBeTruthy();
  });

  it('a mission row shows its list as a chip, when it has one', () => {
    renderPanel(
      [mission({ title: 'Filed', list_id: 5 }), mission({ title: 'Unfiled' })],
      { lists: [list({ id: 5, name: 'Gotham', color: '#4b0082' })] },
    );
    expect(screen.getByText('Gotham')).toBeTruthy();
    expect(screen.getAllByText('Gotham')).toHaveLength(1);
  });
});

describe('A new mission defaults to where the rail is standing', () => {
  const lastPayload = () => api.createMission.mock.calls.at(-1)[0];

  const openAndSubmit = async (title) => {
    fireEvent.click(screen.getByRole('button', { name: /New mission/i }));
    fireEvent.change(screen.getByLabelText(/what is it/i), { target: { value: title } });
    fireEvent.click(screen.getByRole('button', { name: /^add mission$/i }));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
  };

  it('files it into the selected list', async () => {
    renderPanel([], { lists: [list({ id: 5, name: 'Gotham' })], selectedList: 5 });
    await openAndSubmit('Patrol');
    expect(lastPayload().list_id).toBe(5);
  });

  it('files it into the Inbox when the rail is on Inbox', async () => {
    renderPanel([], { lists: [list()], selectedList: 'inbox' });
    await openAndSubmit('Patrol');
    expect(lastPayload().list_id).toBeNull();
  });

  it('files it into the Inbox when the rail is on All', async () => {
    renderPanel([], { lists: [list()] });
    await openAndSubmit('Patrol');
    expect(lastPayload().list_id).toBeNull();
  });

  it('the form field itself starts on the selected list', () => {
    renderPanel([], { lists: [list({ id: 5, name: 'Gotham' })], selectedList: 5 });
    fireEvent.click(screen.getByRole('button', { name: /New mission/i }));
    expect(screen.getByLabelText(/^List/).value).toBe('5');
  });

  it('and the maker of a blank mission can ask for one directly', () => {
    expect(blankMission(new Date(2026, 10, 13), 9).list_id).toBe(9);
    expect(blankMission(new Date(2026, 10, 13)).list_id).toBeNull();
  });

  it('editing a filed mission keeps its list', async () => {
    api.updateMission.mockResolvedValue({});
    renderPanel([mission({ id: 3, title: 'Filed', list_id: 5 })], { lists: [list()] });
    fireEvent.click(screen.getByRole('button', { name: /Edit "Filed"/i }));
    expect(screen.getByLabelText(/^List/).value).toBe('5');
    fireEvent.click(screen.getByRole('button', { name: /Save changes/i }));
    await waitFor(() => expect(api.updateMission).toHaveBeenCalled());
    expect(api.updateMission.mock.calls.at(-1)[1].list_id).toBe(5);
  });
});
