/**
 * One-time localStorage → API migration helper.
 *
 * Runs exactly once per browser: reads legacy items, uploads each via
 * `upload`, and only then sets the flag. If any upload fails the flag is
 * NOT set, so the next mount retries instead of losing unmigrated items.
 */
export async function migrateOnce({ legacyKey, flagKey, toPayload, upload }) {
  try {
    if (localStorage.getItem(flagKey)) return { status: 'already' };
  } catch {
    return { status: 'unavailable' };
  }

  let items = [];
  try {
    items = JSON.parse(localStorage.getItem(legacyKey) || '[]');
  } catch {
    items = [];
  }

  if (!Array.isArray(items) || items.length === 0) {
    try {
      localStorage.setItem(flagKey, '1');
    } catch {}
    return { status: 'empty' };
  }

  // Sequential uploads; a throw aborts before the flag is set → retry next load.
  for (const item of items) {
    await upload(toPayload(item));
  }

  try {
    localStorage.setItem(flagKey, '1');
    localStorage.removeItem(legacyKey);
  } catch {}
  return { status: 'migrated', count: items.length };
}
