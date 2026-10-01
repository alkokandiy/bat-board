/**
 * One-time localStorage → API migration helper.
 *
 * Runs exactly once per browser: reads legacy items, uploads each via
 * `upload`, and only then sets the flag. If any upload fails the flag is
 * NOT set, so the next mount retries the items not yet uploaded.
 */
const inFlight = new Map();

export function migrateOnce(options) {
  // Concurrent callers (e.g. React StrictMode's double mount) share one run
  // instead of uploading every item twice.
  const { flagKey } = options;
  if (!inFlight.has(flagKey)) {
    inFlight.set(flagKey, runMigration(options).finally(() => inFlight.delete(flagKey)));
  }
  return inFlight.get(flagKey);
}

async function runMigration({ legacyKey, flagKey, toPayload, upload }) {
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

  // Sequential uploads. Each success is removed from the legacy list right
  // away, so a failure partway retries only the remainder next load (it used
  // to re-upload everything and duplicate the items that had succeeded).
  const total = items.length;
  while (items.length > 0) {
    await upload(toPayload(items[0]));
    items = items.slice(1);
    try {
      localStorage.setItem(legacyKey, JSON.stringify(items));
    } catch {}
  }

  try {
    localStorage.setItem(flagKey, '1');
    localStorage.removeItem(legacyKey);
  } catch {}
  return { status: 'migrated', count: total };
}
