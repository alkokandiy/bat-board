import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from '../utils/api';

/**
 * When the session is over, and when it merely looks like it.
 *
 * Reported: "session time limit seems to short, after few minutes it's out
 * and i have to login again". The access token lasts a day and the refresh
 * token a month, so nothing about the clock explained it.
 *
 * The cause was `if (!res.ok) clearTokens()` in the refresh path: ANY
 * non-2xx threw the credentials away. /auth/refresh is rate limited to ten
 * a minute, Railway returns 502 while it restarts, and any 500 counted too
 * — so a single bad response signed the person out, whatever the tokens
 * actually said.
 *
 * A failed refresh says nothing about whether the credential is still
 * good. Only the server rejecting the credential says that.
 */

const loggedOut = () => localStorage.getItem('bat_refresh_token') === null;

let logoutEvents;
const onLogout = () => { logoutEvents += 1; };

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem('bat_access_token', 'stale-access');
  localStorage.setItem('bat_refresh_token', 'good-refresh');
  logoutEvents = 0;
  window.addEventListener('auth:logout', onLogout);
});

afterEach(() => {
  window.removeEventListener('auth:logout', onLogout);
  vi.unstubAllGlobals();
});

/** First call 401s the real endpoint; the second is the refresh attempt. */
const stubFetch = (refreshStatus, { refreshBody, afterRefresh } = {}) => {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url, opts) => {
    calls.push(String(url));
    if (String(url).includes('/auth/refresh')) {
      if (refreshStatus === 'network') throw new TypeError('Failed to fetch');
      return {
        ok: refreshStatus >= 200 && refreshStatus < 300,
        status: refreshStatus,
        json: async () => refreshBody || {},
      };
    }
    if (calls.filter((c) => !c.includes('/auth/refresh')).length === 1) {
      return { ok: false, status: 401, json: async () => ({ detail: 'expired' }) };
    }
    return afterRefresh || { ok: true, status: 200, json: async () => ({ ok: true }) };
  }));
  return calls;
};

describe('A refresh that did not go through', () => {
  it('a rate limit does NOT sign you out', async () => {
    // Ten a minute on /auth/refresh, and several tabs will reach it.
    stubFetch(429);
    await expect(api.getMissions()).rejects.toThrow(/could not refresh/i);
    expect(loggedOut()).toBe(false);
    expect(logoutEvents).toBe(0);
  });

  it('a server error does NOT sign you out', async () => {
    stubFetch(500);
    await expect(api.getMissions()).rejects.toThrow(/could not refresh/i);
    expect(loggedOut()).toBe(false);
  });

  it('a restarting server does NOT sign you out', async () => {
    // Railway answers 502 for a few seconds on every deploy.
    stubFetch(502);
    await expect(api.getMissions()).rejects.toThrow(/could not refresh/i);
    expect(loggedOut()).toBe(false);
  });

  it('being offline does NOT sign you out', async () => {
    stubFetch('network');
    await expect(api.getMissions()).rejects.toThrow(/could not reach the server/i);
    expect(loggedOut()).toBe(false);
  });
});

describe('A session that really is over', () => {
  it('a rejected refresh token signs you out', async () => {
    stubFetch(401);
    await expect(api.getMissions()).rejects.toThrow(/log in again/i);
    expect(loggedOut()).toBe(true);
    expect(logoutEvents).toBe(1);
  });

  it('a forbidden refresh token signs you out', async () => {
    stubFetch(403);
    await expect(api.getMissions()).rejects.toThrow(/log in again/i);
    expect(loggedOut()).toBe(true);
  });

  it('having no refresh token at all signs you out', async () => {
    localStorage.removeItem('bat_refresh_token');
    stubFetch(200);
    await expect(api.getMissions()).rejects.toThrow();
    expect(loggedOut()).toBe(true);
  });
});

describe('A refresh that works', () => {
  it('retries the original request with the new token', async () => {
    const calls = stubFetch(200, {
      refreshBody: { access_token: 'fresh-access', refresh_token: 'fresh-refresh' },
    });
    await expect(api.getMissions()).resolves.toEqual({ ok: true });
    expect(localStorage.getItem('bat_access_token')).toBe('fresh-access');
    expect(localStorage.getItem('bat_refresh_token')).toBe('fresh-refresh');
    expect(loggedOut()).toBe(false);
    // original → refresh → original again
    expect(calls).toHaveLength(3);
  });

  it('leaves the tokens untouched when a refresh merely failed', async () => {
    stubFetch(429);
    await expect(api.getMissions()).rejects.toThrow();
    expect(localStorage.getItem('bat_access_token')).toBe('stale-access');
    expect(localStorage.getItem('bat_refresh_token')).toBe('good-refresh');
  });
});

describe('The periodic refresh', () => {
  it('a transient failure there does not end the session either', async () => {
    // This one runs hourly and on tab focus, so it has the most chances to
    // hit a rate limit — and used to be the most likely thing to log you out.
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 429, json: async () => ({}),
    })));
    await expect(api.refreshToken()).rejects.toThrow(/could not refresh/i);
    expect(loggedOut()).toBe(false);
  });
});
