import { describe, it, expect, beforeEach, vi } from 'vitest';
import { migrateOnce } from '../utils/migrateLocalStorage.js';

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('migrateOnce', () => {
  it('uploads each legacy item once, then sets the flag and clears the legacy key', async () => {
    localStorage.setItem(
      'bat_notes',
      JSON.stringify([
        { id: 'a', title: 'One', body: 'b1', category: 'c', pinned: false },
        { id: 'b', title: 'Two', body: 'b2', category: '', pinned: true },
      ])
    );
    const upload = vi.fn(async () => ({ ok: true }));

    const res = await migrateOnce({
      legacyKey: 'bat_notes',
      flagKey: 'bat_notes_migrated',
      toPayload: (n) => ({ title: n.title, body: n.body, is_pinned: n.pinned }),
      upload,
    });

    expect(res.status).toBe('migrated');
    expect(res.count).toBe(2);
    expect(upload).toHaveBeenCalledTimes(2);
    expect(upload).toHaveBeenNthCalledWith(1, { title: 'One', body: 'b1', is_pinned: false });
    expect(localStorage.getItem('bat_notes_migrated')).toBe('1');
    expect(localStorage.getItem('bat_notes')).toBeNull();
  });

  it('never re-uploads on subsequent loads (flag already set)', async () => {
    localStorage.setItem('bat_notes_migrated', '1');
    const upload = vi.fn();

    const res = await migrateOnce({
      legacyKey: 'bat_notes',
      flagKey: 'bat_notes_migrated',
      toPayload: (n) => n,
      upload,
    });

    expect(res.status).toBe('already');
    expect(upload).not.toHaveBeenCalled();
  });

  it('does NOT set the flag when an upload fails, so the next load retries', async () => {
    localStorage.setItem('bat_countdown_goals', JSON.stringify([{ id: 1, label: 'X', target: '2030-01-01T00:00' }]));
    const upload = vi.fn(async () => {
      throw new Error('network down');
    });

    await expect(
      migrateOnce({
        legacyKey: 'bat_countdown_goals',
        flagKey: 'bat_countdown_migrated',
        toPayload: (g) => ({ title: g.label, target_date: g.target }),
        upload,
      })
    ).rejects.toThrow('network down');

    expect(localStorage.getItem('bat_countdown_migrated')).toBeNull();
    expect(JSON.parse(localStorage.getItem('bat_countdown_goals'))).toHaveLength(1);

    // Retry succeeds and uploads exactly once.
    upload.mockResolvedValueOnce({ ok: true });
    const res = await migrateOnce({
      legacyKey: 'bat_countdown_goals',
      flagKey: 'bat_countdown_migrated',
      toPayload: (g) => ({ title: g.label, target_date: g.target }),
      upload,
    });
    expect(res.status).toBe('migrated');
    expect(upload).toHaveBeenCalledTimes(2); // 1 failed + 1 retry
    expect(localStorage.getItem('bat_countdown_migrated')).toBe('1');
  });

  it('sets the flag when there is nothing to migrate', async () => {
    const upload = vi.fn();
    const res = await migrateOnce({
      legacyKey: 'bat_notes',
      flagKey: 'bat_notes_migrated',
      toPayload: (n) => n,
      upload,
    });
    expect(res.status).toBe('empty');
    expect(upload).not.toHaveBeenCalled();
    expect(localStorage.getItem('bat_notes_migrated')).toBe('1');
  });
});
