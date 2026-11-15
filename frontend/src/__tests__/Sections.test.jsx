import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import MissionsPanel from '../components/MissionsPanel';
import { api } from '../utils/api';

vi.mock('../utils/api', () => ({
  api: {
    createMission: vi.fn(),
    updateMission: vi.fn(),
    createSection: vi.fn(),
    renameSection: vi.fn(),
    deleteSection: vi.fn(),
  },
}));

const list = (over = {}) => ({
  id: 5,
  name: 'Gotham',
  color: null,
  position: 0,
  archived: false,
  open_missions: 0,
  ...over,
});

const section = (over = {}) => ({
  id: 11,
  list_id: 5,
  name: 'Day ops',
  position: 0,
  created_at: '2026-01-01T00:00:00Z',
  open_missions: 0,
  ...over,
});

const mission = (over = {}) => ({
  id: 1,
  title: 'Finish the report',
  description: null,
  priority: 'medium',
  status: 'pending',
  due_date: null,
  tags: null,
  location: null,
  notes: null,
  subtasks: null,
  list_id: 5,
  section_id: null,
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

// The Last one: this suite renders repeatedly without automatic cleanup,
// so an earlier test's markup is still in the body.
const lastHeading = (name) => {
  const all = screen.getAllByRole('button', { name });
  return all[all.length - 1];
};

const renderPanel = (missions, over = {}) => {
  const props = {
    lists: [list(), list({ id: 7, name: 'Bludhaven' })],
    selectedList: 5,
    sections: [],
    onRefreshSections: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
  render(
    <MissionsPanel
      missions={missions}
      onRefreshMissions={vi.fn().mockResolvedValue(undefined)}
      onRefreshAccount={vi.fn().mockResolvedValue(undefined)}
      {...props}
    />,
  );
  return props;
};

beforeEach(() => {
  vi.clearAllMocks();
  api.createSection.mockResolvedValue({});
  api.renameSection.mockResolvedValue({});
  api.deleteSection.mockResolvedValue({});
});

afterEach(cleanup);

describe('Grouping under sections', () => {
  const board = () => [
    mission({ id: 1, title: 'Patrol', section_id: 11 }),
    mission({ id: 2, title: 'Case file', section_id: 12 }),
    mission({ id: 3, title: 'Loose ends', section_id: null }),
  ];

  it('missions sit under their own section, and Ungrouped is last', () => {
    renderPanel(board(), {
      sections: [section({ id: 11, name: 'Day ops', position: 0 }), section({ id: 12, name: 'Long game', position: 1 })],
    });

    const headings = screen.getAllByRole('button', { name: /^(Day ops|Long game|Ungrouped)/i });
    expect(headings.map((h) => h.textContent.replace(/\d+$/, ''))).toEqual([
      'Day ops', 'Long game', 'Ungrouped',
    ]);

    // Each mission is inside its own group, not loose on the page.
    expect(within(lastHeading(/^Day ops/i).parentElement).getByText('Patrol')).toBeTruthy();
    expect(within(lastHeading(/^Long game/i).parentElement).getByText('Case file')).toBeTruthy();
    expect(within(lastHeading(/^Ungrouped/i).parentElement).getByText('Loose ends')).toBeTruthy();
  });

  it('a section the user made but left empty still shows its heading', () => {
    // No mission anywhere near section 12. Passing the usual board() here
    // would put one in it, and the test would be checking a populated
    // section while claiming to check an empty one.
    renderPanel([mission({ id: 1, title: 'Patrol', section_id: 11 })], {
      sections: [
        section({ id: 11, name: 'Day ops', position: 0 }),
        section({ id: 12, name: 'Empty shelf', position: 1, open_missions: 0 }),
      ],
    });
    // Made on purpose — it must not silently vanish, or creating a section
    // and seeing nothing appear is the whole experience of making one.
    // Just the heading: a zero count shows no badge, the same rule the
    // list rail follows, so there is no number to assert on here.
    expect(screen.getAllByRole('button', { name: /^Empty shelf/i })).toHaveLength(1);
  });

  it('sections arrive in their position order, not array order', () => {
    renderPanel(board(), {
      sections: [section({ id: 12, name: 'Long game', position: 1 }), section({ id: 11, name: 'Day ops', position: 0 })],
    });
    const headings = screen.getAllByRole('button', { name: /^(Day ops|Long game|Ungrouped)/i });
    expect(headings[0].textContent).toMatch(/^Day ops/);
    expect(headings[1].textContent).toMatch(/^Long game/);
  });

  it('a group heading can be collapsed, and hides only its own cards', () => {
    renderPanel(board(), {
      sections: [section({ id: 11, name: 'Day ops' }), section({ id: 12, name: 'Long game' })],
    });
    const heading = lastHeading(/^Day ops/i);
    expect(heading.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(heading);
    expect(heading.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('Patrol')).toBeNull();
    // The other groups are untouched.
    expect(screen.getByText('Case file')).toBeTruthy();
    expect(screen.getByText('Loose ends')).toBeTruthy();
  });

  it('All and Inbox stay flat: no sections, no headings, no manager', () => {
    // One mission filed, one not, so each selection has something of its own.
    const mixed = [...board(), mission({ id: 4, title: 'Unfiled', list_id: null })];

    renderPanel(mixed, { selectedList: null, sections: [section()] });
    expect(screen.queryByRole('button', { name: /^Ungrouped/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add section/i })).toBeNull();
    expect(screen.getByText('Patrol')).toBeTruthy();
    expect(screen.getByText('Unfiled')).toBeTruthy();
    cleanup();

    renderPanel(mixed, { selectedList: 'inbox', sections: [section()] });
    expect(screen.queryByRole('button', { name: /^Ungrouped/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add section/i })).toBeNull();
    expect(screen.getByText('Unfiled')).toBeTruthy();
    expect(screen.queryByText('Patrol')).toBeNull();
    cleanup();
  });

  it('a list with no sections yet renders flat, as it always did', () => {
    renderPanel(board(), { sections: [] });
    expect(screen.queryByRole('button', { name: /^Ungrouped/i })).toBeNull();
    expect(screen.getByText('Patrol')).toBeTruthy();
  });

  it('grouping composes with the date filter: hidden stays hidden', () => {
    renderPanel(
      [
        mission({ id: 1, title: 'Due today', section_id: 11, due_date: `${todayKey()}T00:00:00Z` }),
        mission({ id: 2, title: 'Lost last month', section_id: 11, due_date: '2026-10-01T00:00:00Z' }),
      ],
      { sections: [section({ id: 11, name: 'Day ops' })] },
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Today' }).at(-1));
    expect(screen.getByText('Due today')).toBeTruthy();
    expect(screen.queryByText('Lost last month')).toBeNull();

    // And the heading count says what is actually visible under it.
    const heading = lastHeading(/^Day ops/i);
    expect(within(heading).getByText('1')).toBeTruthy();
  });

  it('a stale section id lands ungrouped rather than vanishing', () => {
    renderPanel([mission({ id: 1, title: 'Orphan', section_id: 99 })], {
      sections: [section({ id: 11, name: 'Day ops' })],
    });
    expect(within(lastHeading(/^Ungrouped/i).parentElement).getByText('Orphan')).toBeTruthy();
  });
});

describe('The Section control in the mission form', () => {
  const openForm = () => {
    fireEvent.click(screen.getAllByRole('button', { name: /New mission/i }).at(-1));
  };

  it('offers only the sections of the list chosen in the form', () => {
    renderPanel([], {
      sections: [
        section({ id: 11, list_id: 5, name: 'Day ops' }),
        section({ id: 12, list_id: 7, name: 'Bludhaven ops' }),
      ],
    });
    openForm();
    const control = screen.getAllByLabelText(/^Section/).at(-1);
    const names = [...control.options].map((o) => o.textContent);
    expect(names).toContain('Day ops');
    expect(names).not.toContain('Bludhaven ops');
  });

  it('offers nothing when the chosen list is the Inbox', () => {
    renderPanel([], { selectedList: 'inbox', sections: [section({ id: 11, list_id: 5, name: 'Day ops' })] });
    openForm();
    // The form starts on the Inbox, so there is no Section control at all.
    expect(screen.queryByLabelText(/^Section/)).toBeNull();
    // Choosing a real list brings it back — with that list's sections.
    fireEvent.change(screen.getAllByLabelText(/^List/).at(-1), { target: { value: '5' } });
    const control = screen.getAllByLabelText(/^Section/).at(-1);
    expect([...control.options].map((o) => o.textContent)).toContain('Day ops');
  });

  it('changing the list clears the section, and the payload says so', async () => {
    api.updateMission.mockResolvedValue({});
    api.createMission.mockResolvedValue({});
    renderPanel([mission({ id: 3, title: 'Filed', section_id: 11 })], {
      sections: [
        section({ id: 11, list_id: 5, name: 'Day ops' }),
        section({ id: 12, list_id: 7, name: 'Bludhaven ops' }),
      ],
    });
    fireEvent.click(screen.getAllByRole('button', { name: /Edit "Filed"/i }).at(-1));
    const control = screen.getAllByLabelText(/^Section/).at(-1);
    expect(control.value).toBe('11');

    // Moving the list drops the section: the old one belongs to the old list.
    fireEvent.change(screen.getAllByLabelText(/^List/).at(-1), { target: { value: '7' } });
    expect(screen.getAllByLabelText(/^Section/).at(-1).value).toBe('');

    fireEvent.click(screen.getAllByRole('button', { name: /Save changes/i }).at(-1));
    await waitFor(() => expect(api.updateMission).toHaveBeenCalled());
    const payload = api.updateMission.mock.calls.at(-1)[1];
    expect(payload.list_id).toBe(7);
    expect(payload.section_id).toBeNull();
  });

  it('a new mission files itself into the selected list and section', async () => {
    api.createMission.mockResolvedValue({});
    renderPanel([], {
      sections: [section({ id: 11, list_id: 5, name: 'Day ops' })],
    });
    openForm();
    fireEvent.change(screen.getAllByLabelText(/^Section/).at(-1), { target: { value: '11' } });
    fireEvent.change(screen.getAllByLabelText(/what is it/i).at(-1), { target: { value: 'Patrol' } });
    fireEvent.click(screen.getAllByRole('button', { name: /^add mission$/i }).at(-1));
    await waitFor(() => expect(api.createMission).toHaveBeenCalled());
    const payload = api.createMission.mock.calls.at(-1)[0];
    expect(payload.list_id).toBe(5);
    expect(payload.section_id).toBe(11);
  });
});

describe('Section management', () => {
  const openManager = () => {
    return renderPanel([], { sections: [section({ id: 11, name: 'Day ops' })] });
  };

  it('adds a section into the selected list', async () => {
    const { onRefreshSections } = openManager();
    fireEvent.click(screen.getAllByRole('button', { name: /Add section/i }).at(-1));
    fireEvent.change(screen.getByLabelText('New section name'), { target: { value: 'Long game' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save section' }).at(-1));
    await waitFor(() => expect(api.createSection).toHaveBeenCalledWith({ list_id: 5, name: 'Long game' }));
    await waitFor(() => expect(onRefreshSections).toHaveBeenCalled());
  });

  it('renames one inline', async () => {
    openManager();
    fireEvent.click(screen.getAllByRole('button', { name: 'Rename "Day ops"' }).at(-1));
    fireEvent.change(screen.getByLabelText('Rename section Day ops'), { target: { value: 'Night ops' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save name for "Day ops"' }).at(-1));
    await waitFor(() => expect(api.renameSection).toHaveBeenCalledWith(11, 'Night ops'));
  });

  it('the delete confirmation says the missions stay in the list', async () => {
    const { onRefreshSections } = openManager();
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete "Day ops"' }).at(-1));
    const note = screen.getByText(/missions stay in the list/i);
    expect(note.textContent).toMatch(/nothing is deleted/i);

    fireEvent.click(within(note.closest('div')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.deleteSection).toHaveBeenCalledWith(11));
    // Its missions are now ungrouped, so the missions are re-read too.
    await waitFor(() => expect(onRefreshSections).toHaveBeenCalled());
  });

  it('the confirmation can be declined, and then nothing is sent', async () => {
    openManager();
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete "Day ops"' }).at(-1));
    fireEvent.click(screen.getAllByRole('button', { name: 'Keep' }).at(-1));
    expect(api.deleteSection).not.toHaveBeenCalled();
    expect(screen.queryByText(/missions stay in the list/i)).toBeNull();
  });

  it('shows the server\'s refusal, which is meant to be read', async () => {
    api.createSection.mockRejectedValue(new Error('A section with that name already exists in this list.'));
    openManager();
    fireEvent.click(screen.getAllByRole('button', { name: /Add section/i }).at(-1));
    fireEvent.change(screen.getByLabelText('New section name'), { target: { value: 'Day ops' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save section' }).at(-1));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A section with that name already exists in this list.');
  });
});
