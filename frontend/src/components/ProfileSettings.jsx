import React, { useState, useEffect } from 'react';
import { api, browserTimezone } from '../utils/api';
import { PageHeader } from './ui';

function timezoneOptions(current) {
  let zones = [];
  try {
    zones = Intl.supportedValuesOf('timeZone');
  } catch {
    zones = [];
  }
  const all = new Set(['UTC', ...zones]);
  if (current) all.add(current);
  return [...all].sort();
}

const LEVELS = [
  { min: 0, max: 1999, title: 'The Recruit' },
  { min: 2000, max: 4999, title: 'The Vigilante' },
  { min: 5000, max: 9999, title: 'The Detective' },
  { min: 10000, max: 19999, title: "Gotham's Shadow" },
  { min: 20000, max: 34999, title: 'The Caped Crusader' },
  { min: 35000, max: 54999, title: 'The Watchful Protector' },
  { min: 55000, max: 79999, title: 'The Dark Knight' },
  { min: 80000, max: 119999, title: 'Legend of Gotham' },
  { min: 120000, max: 179999, title: 'The Bat Incarnate' },
  { min: 180000, max: null, title: 'The Dark Knight Eternal' },
];

function AdminPanel() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getAdminUsers());
    } catch (e) {
      setError(e.message || 'Failed to load users.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const p = api.getAdminMe?.();
    if (!p || typeof p.then !== 'function') return; // never break the Profile page
    p.then((r) => {
      if (cancelled || !r?.is_admin) return;
      setIsAdmin(true);
      load();
    }).catch(() => {}); // non-admins / errors: stay hidden
    return () => { cancelled = true; };
  }, []);

  if (!isAdmin) return null;

  const act = async (fn, id) => {
    setBusyId(id);
    setError(null);
    try {
      await fn(id);
      await load();
    } catch (e) {
      setError(e.message || 'Action failed.');
    } finally {
      setBusyId(null);
      setConfirmDeleteId(null);
    }
  };

  return (
    <div className="bg-bat-surface rounded-tile border ring-1 ring-signal-warn/30 p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-mono tracking-widest text-signal-warn">ADMIN · USERS</h3>
        <button
          onClick={load}
          className="px-3 py-1 border border-bat-line text-ink-muted rounded text-[11px] font-mono tracking-widest hover:border-signal-warn/60 transition"
        >
          REFRESH
        </button>
      </div>
      {data && (
        <p className="text-xs text-ink-faint font-body mb-4">
          {data.total_users} user{data.total_users === 1 ? '' : 's'} · {data.active_users} active
        </p>
      )}
      {error && <div className="text-[12px] text-signal-late font-body mb-3">{error}</div>}
      {loading && !data ? (
        <div className="text-ink-faint text-sm">Loading…</div>
      ) : data && data.users.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px] font-body">
            <thead>
              <tr className="text-ink-faint font-mono text-[10px] tracking-wider border-b border-bat-line">
                <th className="py-2 pr-3">USER</th>
                <th className="py-2 pr-3">STATUS</th>
                <th className="py-2 pr-3">SETUP</th>
                <th className="py-2 pr-3">DATA</th>
                <th className="py-2 pr-3 text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {data.users.map((u) => (
                <tr key={u.id} className="align-middle">
                  <td className="py-2.5 pr-3">
                    <div className="text-ink">
                      {u.username}
                      {u.is_admin && <span className="ml-1.5 text-signal-warn text-[10px] font-mono">ADMIN</span>}
                    </div>
                    <div className="text-ink-faint text-[10px]">{u.bat_level} · {u.points} BP</div>
                  </td>
                  <td className="py-2.5 pr-3">
                    {u.is_active
                      ? <span className="text-signal-good">active</span>
                      : <span className="text-signal-late">disabled</span>}
                  </td>
                  <td className="py-2.5 pr-3 text-[11px]">
                    <span className={u.telegram_linked ? 'text-ink-muted' : 'text-ink-faint'}>TG</span>
                    {' · '}
                    <span className={u.provider_configured ? 'text-ink-muted' : 'text-ink-faint'}>AI</span>
                  </td>
                  <td className="py-2.5 pr-3 text-ink-faint text-[11px]">
                    {u.counts.missions}m · {u.counts.habits}h · {u.counts.notes}n
                  </td>
                  <td className="py-2.5 pr-0 text-right whitespace-nowrap">
                    {u.is_admin ? (
                      <span className="text-ink-faint text-[11px]">—</span>
                    ) : confirmDeleteId === u.id ? (
                      <span className="inline-flex gap-1.5 items-center">
                        <span className="text-[10px] text-signal-late font-mono">delete?</span>
                        <button
                          disabled={busyId === u.id}
                          onClick={() => act(api.deleteUser, u.id)}
                          className="px-2 py-1 border border-signal-late/50 text-signal-late rounded text-[10px] font-mono hover:bg-signal-late/10 disabled:opacity-50"
                        >YES</button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="px-2 py-1 border border-bat-line text-ink-muted rounded text-[10px] font-mono"
                        >NO</button>
                      </span>
                    ) : (
                      <span className="inline-flex gap-1.5">
                        {u.is_active ? (
                          <button
                            disabled={busyId === u.id}
                            onClick={() => act(api.disableUser, u.id)}
                            className="px-2 py-1 border border-bat-line text-ink-muted rounded text-[10px] font-mono tracking-wider hover:border-signal-warn/60 disabled:opacity-50"
                          >DISABLE</button>
                        ) : (
                          <button
                            disabled={busyId === u.id}
                            onClick={() => act(api.enableUser, u.id)}
                            className="px-2 py-1 border border-bat-line text-signal-good rounded text-[10px] font-mono tracking-wider hover:border-signal-good/60 disabled:opacity-50"
                          >ENABLE</button>
                        )}
                        <button
                          disabled={busyId === u.id}
                          onClick={() => setConfirmDeleteId(u.id)}
                          className="px-2 py-1 border border-signal-late/40 text-signal-late/90 rounded text-[10px] font-mono tracking-wider hover:bg-signal-late/10 disabled:opacity-50"
                        >DELETE</button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-ink-faint font-body mt-3">
            Disable blocks login (reversible). Delete permanently removes the user and all their data. Admins are protected.
          </p>
        </div>
      ) : (
        <div className="text-ink-faint text-sm">No users.</div>
      )}
    </div>
  );
}

export default function ProfileSettings({ account, onRefreshAccount, workEnabled = false, onWorkEnabledChange = () => {} }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwMsg, setPwMsg] = useState(null);
  const [pwError, setPwError] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [tgLinked, setTgLinked] = useState(null);
  const [tgCode, setTgCode] = useState(null);
  const [tgExpiresAt, setTgExpiresAt] = useState(null);
  const [tgSecondsLeft, setTgSecondsLeft] = useState(0);
  const [tgBusy, setTgBusy] = useState(false);
  const [tgError, setTgError] = useState(null);
  const [pointsError, setPointsError] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [ledger, setLedger] = useState([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [workBusy, setWorkBusy] = useState(false);
  const [workError, setWorkError] = useState(null);
  const [workHasData, setWorkHasData] = useState(false);
  const [addressDraft, setAddressDraft] = useState(account?.alfred_address || '');
  const [addressMsg, setAddressMsg] = useState(null);
  const [addressError, setAddressError] = useState(null);
  useEffect(() => { setAddressDraft(account?.alfred_address || ''); }, [account?.alfred_address]);

  // Whether they have work data decides the wording below ("nothing is
  // deleted" only means something if there is something to keep).
  useEffect(() => {
    let cancelled = false;
    api.getWorkStatus()
      .then((st) => { if (!cancelled) setWorkHasData(!!st.has_data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [workEnabled]);

  const toggleWork = async (enabled) => {
    setWorkBusy(true);
    setWorkError(null);
    try {
      const st = await api.setWorkEnabled(enabled);
      setWorkHasData(!!st.has_data);
      onWorkEnabledChange(!!st.enabled);
    } catch (err) {
      setWorkError(err.message);
    } finally {
      setWorkBusy(false);
    }
  };

  const saveAddress = async (e) => {
    e.preventDefault();
    setAddressMsg(null);
    setAddressError(null);
    try {
      await api.updateAccount({ alfred_address: addressDraft.trim() });
      await onRefreshAccount();
      setAddressMsg('Saved');
    } catch (err) {
      setAddressError(err.message);
    }
  };

  const [eraseMemory, setEraseMemory] = useState(false);
  const [alfredResetting, setAlfredResetting] = useState(false);
  const [alfredResetMsg, setAlfredResetMsg] = useState(null);
  const [confirmingAlfredReset, setConfirmingAlfredReset] = useState(false);

  const alfredResetDeletes = [
    'All Alfred conversations and their messages — in the app and on Telegram',
    'Any pending delete confirmation or unfinished /setkey setup',
    ...(eraseMemory ? ["Everything Alfred remembers about you (its memory notes)"] : []),
  ];
  const alfredResetKeeps = [
    ...(eraseMemory ? [] : ["Alfred's memory notes about you"]),
    'Your AI model key and settings',
    'Your Telegram link',
    'Your own notes, missions, habits, calendar and Bat Points',
    "Today's Alfred message count",
  ];

  const handleResetAlfred = async () => {
    setConfirmingAlfredReset(false);
    setAlfredResetting(true);
    setAlfredResetMsg(null);
    try {
      const res = await api.resetAlfred(eraseMemory);
      window.dispatchEvent(new CustomEvent('alfred:reset'));
      setAlfredResetMsg(
        `Deleted ${res.sessions} conversation${res.sessions === 1 ? '' : 's'}` +
        (eraseMemory ? ` and ${res.memory_notes} memory note${res.memory_notes === 1 ? '' : 's'}.` : '.')
      );
      setEraseMemory(false);
    } catch (err) {
      setAlfredResetMsg(err.message);
    } finally {
      setAlfredResetting(false);
    }
  };

  const [tzBusy, setTzBusy] = useState(false);
  const [tzError, setTzError] = useState(null);
  const deviceTz = browserTimezone();
  const accountTz = account?.timezone || 'UTC';

  const saveTimezone = async (tz) => {
    if (!tz || tz === account?.timezone) return;
    setTzBusy(true);
    setTzError(null);
    try {
      await api.updateAccount({ timezone: tz });
      await onRefreshAccount();
    } catch (err) {
      setTzError(err.message);
    } finally {
      setTzBusy(false);
    }
  };

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwMsg(null);
    setPwError(null);
    if (newPassword !== confirmPassword) {
      setPwError('Passwords do not match');
      return;
    }
    if (newPassword.length < 8) {
      setPwError('Password must be at least 8 characters');
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      setPwMsg('Password updated successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPwError(err.message);
    }
  };

  const handleResetPoints = async () => {
    if (!window.confirm('Are you sure you want to reset all Bat Points to 0? This cannot be undone.')) return;
    setResetting(true);
    setPointsError(null);
    try {
      await api.resetPoints();
      await onRefreshAccount();
    } catch (err) {
      setPointsError(err.message);
    } finally {
      setResetting(false);
    }
  };

  const currentPoints = account?.points ?? 0;
  const currentLevel = account?.bat_level ?? 'The Recruit';
  // The ladder was drawn but never said how far along it you are.
  const nextLevel = LEVELS.find((l) => l.min > currentPoints) || null;
  const pointsToNextLevel = nextLevel ? nextLevel.min - currentPoints : null;

  useEffect(() => {
    let cancelled = false;
    api.getTelegramLinkStatus()
      .then(s => { if (!cancelled) setTgLinked(!!s.linked); })
      .catch(() => { if (!cancelled) setTgLinked(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!tgExpiresAt) return;
    const tick = () => {
      const left = Math.max(0, Math.round((new Date(tgExpiresAt).getTime() - Date.now()) / 1000));
      setTgSecondsLeft(left);
      if (left <= 0) {
        setTgCode(null);
        setTgExpiresAt(null);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [tgExpiresAt]);

  const handleGenerateCode = async () => {
    setTgBusy(true);
    try {
      const res = await api.generateTelegramCode();
      setTgCode(res.code);
      setTgExpiresAt(res.expires_at);
      setTgError(null);
    } catch (err) {
      setTgError(err.message);
    } finally {
      setTgBusy(false);
    }
  };

  const handleUnlink = async () => {
    if (!window.confirm('Unlink Telegram from your bat-board account? Alfred will stop responding here.')) return;
    setTgBusy(true);
    try {
      await api.unlinkTelegram();
      setTgLinked(false);
      setTgCode(null);
      setTgExpiresAt(null);
      setTgError(null);
    } catch (err) {
      setTgError(err.message);
    } finally {
      setTgBusy(false);
    }
  };

  const fmtExpiry = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  const toggleLogs = async () => {
    if (showLogs) {
      setShowLogs(false);
      return;
    }
    setShowLogs(true);
    if (ledger.length > 0) return;
    setLedgerLoading(true);
    try {
      setLedger(await api.getLogs(100));
    } catch {
      // keep empty rather than crashing
    } finally {
      setLedgerLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* "Manage your identity, credentials, and Bat Point ledger" described
          the page to someone already looking at it. Where you stand is the
          thing worth the line. */}
      <PageHeader
        title="PROFILE & SETTINGS"
        stats={[
          { label: 'points', value: currentPoints.toLocaleString() },
          { label: currentLevel, value: '', tone: 'self' },
          ...(pointsToNextLevel !== null
            ? [{ label: `to ${nextLevel.title}`, value: pointsToNextLevel.toLocaleString() }]
            : []),
        ]}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Bat Level Ladder */}
        <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
          <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
            Bat Level Ladder
          </h2>
          <div className="space-y-1">
            {LEVELS.map((lvl) => {
              const isCurrent = lvl.title === currentLevel;
              const reqMet = currentPoints >= lvl.min;
              const rangeStr = lvl.max !== null
                ? `${lvl.min.toLocaleString()} — ${lvl.max.toLocaleString()} BP`
                : `${lvl.min.toLocaleString()}+ BP`;
              return (
                <div
                  key={lvl.title}
                  className={`flex items-center justify-between px-3 py-2 rounded text-xs font-mono transition ${
                    isCurrent
                      ? 'bg-signal-self/10 text-signal-self border border-signal-self/30'
                      : reqMet
                        ? 'text-ink-muted'
                        : 'text-ink-faint'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isCurrent && <span className="text-[10px]">{'>'}</span>}
                    <span>{lvl.title}</span>
                  </div>
                  <span className={isCurrent ? 'text-signal-self' : 'text-ink-faint'}>
                    {rangeStr}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-3 border-t border-bat-line text-xs text-ink-faint font-mono">
            Current: <span className="text-signal-self font-bold">{currentPoints.toLocaleString()} BP</span> — {currentLevel}
          </div>
        </div>

        <div className="space-y-6">
          {/* Change Password */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              Change Password
            </h2>
            <form onSubmit={handlePasswordChange} className="space-y-3">
              <div className="text-xs">
                <label className="block text-ink-muted mb-1.5 font-mono uppercase tracking-[0.14em] text-[10px]">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  required
                  className="w-full rounded-chip bg-bat-raised px-3 py-2 text-ink font-mono ring-1 ring-bat-line transition-all duration-200 ease-soft focus:outline-none focus:ring-2 focus:ring-signal-self/50"
                />
              </div>
              <div className="text-xs">
                <label className="block text-ink-muted mb-1.5 font-mono uppercase tracking-[0.14em] text-[10px]">New Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full rounded-chip bg-bat-raised px-3 py-2 text-ink font-mono ring-1 ring-bat-line transition-all duration-200 ease-soft focus:outline-none focus:ring-2 focus:ring-signal-self/50"
                />
              </div>
              <div className="text-xs">
                <label className="block text-ink-muted mb-1.5 font-mono uppercase tracking-[0.14em] text-[10px]">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  required
                  className="w-full rounded-chip bg-bat-raised px-3 py-2 text-ink font-mono ring-1 ring-bat-line transition-all duration-200 ease-soft focus:outline-none focus:ring-2 focus:ring-signal-self/50"
                />
              </div>
              {pwMsg && <div className="text-xs text-signal-good">{pwMsg}</div>}
              {pwError && <div className="text-xs text-signal-late">{pwError}</div>}
              <button
                type="submit"
                className="px-4 py-2 rounded-chip bg-signal-self text-bat-bg font-bold text-[11px] font-mono uppercase tracking-widest shadow-tile hover:brightness-110 transition-all duration-200 ease-soft active:scale-[0.97]"
              >
                UPDATE PASSWORD
              </button>
            </form>
          </div>

          {/* Alfred form of address */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              What Alfred Calls You
            </h2>
            <p className="text-xs text-ink-muted mb-3">
              Used in Telegram and the in-app chat. Leave empty to be addressed by your username ({account?.username}).
            </p>
            <form onSubmit={saveAddress} className="flex gap-2">
              <input
                type="text"
                value={addressDraft}
                onChange={e => { setAddressDraft(e.target.value); setAddressMsg(null); }}
                maxLength={60}
                placeholder={account?.username || 'e.g. Master Wayne'}
                className="flex-1 min-w-0 bg-bat-raised border border-bat-line rounded px-3 py-2 text-xs text-ink placeholder-ink-faint focus:outline-none focus:border-signal-self"
              />
              <button
                type="submit"
                disabled={addressDraft.trim() === (account?.alfred_address || '')}
                className="px-4 py-2 rounded-chip bg-signal-self text-bat-bg font-bold text-[11px] font-mono uppercase tracking-widest shadow-tile hover:brightness-110 transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
              >
                SAVE
              </button>
            </form>
            {addressMsg && <div className="text-xs text-signal-good mt-2">{addressMsg}</div>}
            {addressError && <div className="text-xs text-signal-late mt-2">{addressError}</div>}
          </div>

          {/* Timezone */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              Timezone
            </h2>
            <p className="text-xs text-ink-muted mb-3">
              Days for habits, daily stats, and Alfred's clock and daily limit start at midnight in this zone.
            </p>
            <select
              value={accountTz}
              disabled={tzBusy}
              onChange={e => saveTimezone(e.target.value)}
              className="w-full rounded-chip bg-bat-raised px-2.5 py-2 text-xs text-ink font-mono ring-1 ring-bat-line transition-all duration-200 ease-soft focus:outline-none focus:ring-2 focus:ring-signal-self/50 disabled:opacity-50"
            >
              {timezoneOptions(accountTz).map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
            {deviceTz && deviceTz !== accountTz && (
              <button
                type="button"
                onClick={() => saveTimezone(deviceTz)}
                disabled={tzBusy}
                className="mt-3 text-[10px] font-mono tracking-widest text-ink-muted hover:text-signal-self border border-bat-line hover:border-signal-self/50 rounded px-2 py-1 transition disabled:opacity-50"
              >
                USE THIS DEVICE'S ZONE ({deviceTz})
              </button>
            )}
            {tzError && <div className="text-xs text-signal-late mt-2">{tzError}</div>}
          </div>

          {/* Work track */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              Work Track
            </h2>
            <p className="text-xs text-ink-muted mb-4">
              The corporate side: tasks for your employer, a work journal and work
              reports, kept entirely apart from your missions and earning no Bat
              Points. With it off, the Work tab disappears, Alfred stops offering
              anything work-related, and automatic work reports stop.
              {workHasData && ' Your work data is kept either way and returns exactly as it was.'}
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => toggleWork(!workEnabled)}
                disabled={workBusy}
                className={`px-5 py-2 font-bold rounded text-xs font-mono tracking-widest transition disabled:opacity-50 border ${
                  workEnabled
                    ? 'bg-bat-raised ring-1 ring-bat-line text-ink-muted hover:text-ink hover:ring-bat-line-strong'
                    : 'bg-signal-work/10 border-signal-work/40 text-signal-work hover:bg-signal-work/20'
                }`}
              >
                {workBusy ? 'SAVING...' : workEnabled ? 'TURN WORK OFF' : 'TURN WORK ON'}
              </button>
              <span className="text-[10px] font-mono tracking-wider text-ink-faint">
                {workEnabled ? 'CURRENTLY ON' : 'CURRENTLY OFF'}
              </span>
            </div>
            {workError && <div className="text-xs text-signal-late mt-2">{workError}</div>}
          </div>

          {/* Reset Points */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-signal-late/25 shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-signal-late border-b border-signal-late/20 pb-2.5 mb-4">
              Danger Zone
            </h2>
            <p className="text-xs text-ink-muted mb-4">
              Reset all Bat Points to 0. Your level will revert to The Recruit. This action is irreversible.
            </p>
            {pointsError && (
              <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late mb-3">{pointsError}</div>
            )}

            <button
              onClick={handleResetPoints}
              disabled={resetting}
              className="px-4 py-2 rounded-chip bg-transparent ring-1 ring-signal-late/40 text-signal-late font-bold text-[11px] font-mono uppercase tracking-widest hover:bg-signal-late/10 hover:ring-signal-late/70 transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
            >
              {resetting ? 'RESETTING...' : 'RESET BAT POINTS'}
            </button>

            <div className="mt-6 pt-4 border-t border-signal-late/20">
              <p className="text-xs text-ink-muted mb-3">
                Start fresh with Alfred by permanently deleting your conversations.
              </p>
              <label className="flex items-center gap-2 text-xs text-ink-muted mb-4 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={eraseMemory}
                  onChange={e => setEraseMemory(e.target.checked)}
                  className="accent-signal-late"
                />
                Also erase everything Alfred remembers about me (its memory notes)
              </label>
              {confirmingAlfredReset ? (
                <div role="alertdialog" aria-label="Confirm Alfred reset" className="rounded-tile border border-signal-late/40 bg-signal-late/10 p-4 space-y-3">
                  <div className="text-xs font-bold text-signal-late">This cannot be undone.</div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-signal-late mb-1">Will be deleted</div>
                    <ul className="text-xs text-ink-muted space-y-0.5 list-disc pl-4">
                      {alfredResetDeletes.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-signal-good mb-1">Will be kept</div>
                    <ul className="text-xs text-ink-muted space-y-0.5 list-disc pl-4">
                      {alfredResetKeeps.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div className="text-[11px] text-ink-faint">
                    The Telegram chat window itself isn't cleared — use "Clear history" in Telegram for that.
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={handleResetAlfred}
                      className="px-4 py-2 bg-signal-late text-bat-bg font-bold rounded text-xs font-mono tracking-widest hover:brightness-110 transition"
                    >
                      DELETE PERMANENTLY
                    </button>
                    <button
                      onClick={() => setConfirmingAlfredReset(false)}
                      className="px-4 py-2 rounded-chip bg-bat-raised ring-1 ring-bat-line text-ink-muted text-[11px] font-mono uppercase tracking-widest hover:text-ink hover:ring-bat-line-strong transition-all duration-200 ease-soft active:scale-[0.97]"
                    >
                      CANCEL
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => { setAlfredResetMsg(null); setConfirmingAlfredReset(true); }}
                  disabled={alfredResetting}
                  className="px-4 py-2 rounded-chip bg-transparent ring-1 ring-signal-late/40 text-signal-late font-bold text-[11px] font-mono uppercase tracking-widest hover:bg-signal-late/10 hover:ring-signal-late/70 transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
                >
                  {alfredResetting ? 'RESETTING...' : 'RESET ALFRED'}
                </button>
              )}
              {alfredResetMsg && <div className="text-xs text-ink-muted mt-2">{alfredResetMsg}</div>}
            </div>
          </div>

          {/* Link Telegram */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              Link Telegram
            </h2>
{tgError && (
              <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late mb-3">{tgError}</div>
            )}
            {tgLinked === null ? (
              <p className="text-xs text-ink-faint font-mono">Checking link status...</p>
            ) : tgLinked ? (
              <div className="space-y-3">
                <p className="text-xs text-signal-good font-mono">Linked ✓ — Alfred will respond to this Telegram account.</p>
                <button
                  onClick={handleUnlink}
                  disabled={tgBusy}
                  className="px-4 py-2 rounded-chip bg-bat-raised ring-1 ring-bat-line text-ink-muted font-bold text-[11px] font-mono uppercase tracking-widest hover:text-signal-late hover:ring-signal-late/40 transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
                >
                  UNLINK
                </button>
              </div>
            ) : tgCode ? (
              <div className="space-y-3">
                <p className="text-xs text-ink-muted">
                  Open Telegram, message the bot, and send this code. Expires in{' '}
                  <span className="text-signal-self font-mono font-bold">{fmtExpiry(tgSecondsLeft)}</span>.
                </p>
                <div className="text-3xl font-mono font-bold tracking-[0.3em] text-signal-self text-center py-2 bg-bat-raised rounded-tile border border-bat-line">
                  {tgCode}
                </div>
                <button
                  onClick={handleGenerateCode}
                  disabled={tgBusy}
                  className="px-4 py-2 rounded-chip bg-bat-raised ring-1 ring-bat-line text-ink-muted font-bold text-[11px] font-mono uppercase tracking-widest hover:text-ink hover:ring-bat-line-strong transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
                >
                  REGENERATE CODE
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-ink-muted">
                  Connect your Telegram account to chat with Alfred. Generate a code, then send it to the bot.
                </p>
                <button
                  onClick={handleGenerateCode}
                  disabled={tgBusy}
                  className="px-4 py-2 rounded-chip bg-signal-self text-bat-bg font-bold text-[11px] font-mono uppercase tracking-widest shadow-tile hover:brightness-110 transition-all duration-200 ease-soft active:scale-[0.97] disabled:opacity-40"
                >
                  {tgBusy ? 'GENERATING...' : 'GENERATE LINK CODE'}
                </button>
              </div>
            )}
          </div>
          {/* Ledger Log */}
          <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
            <h2 className="text-[11px] font-mono uppercase tracking-[0.14em] text-ink-muted border-b border-white/[0.04] pb-2.5 mb-4">
              Ledger Log
            </h2>
            <p className="text-xs text-ink-muted mb-4">
              Immutable history of account modifications, completions, and point awards.
            </p>
            <button
              onClick={toggleLogs}
              className="px-5 py-2 bg-bat-raised border border-bat-line text-ink-muted font-bold rounded text-xs font-mono tracking-widest hover:border-signal-self/50 transition"
            >
              {showLogs ? 'HIDE LEDGER' : 'VIEW LEDGER'}
            </button>
            {showLogs && (
              <div className="mt-4 max-h-80 overflow-y-auto divide-y divide-white/[0.04] font-mono text-xs border border-bat-line rounded">
                {ledgerLoading ? (
                  <div className="p-4 text-center text-ink-faint">Loading ledger...</div>
                ) : ledger.length === 0 ? (
                  <div className="p-4 text-center text-ink-faint">No ledger entries yet.</div>
                ) : ledger.map((log) => {
                  let summary = log.details;
                  try {
                    const d = JSON.parse(log.details);
                    summary = d.message || d.reason || log.details;
                  } catch {}
                  return (
                    <div key={log.id} className="px-3 py-2.5 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="px-1.5 py-0.5 bg-bat-raised ring-1 ring-bat-line text-ink-muted rounded-chip text-[10px] shrink-0">
                          {log.event_type}
                        </span>
                        <span className="text-ink-muted truncate">{summary}</span>
                      </div>
                      <span className="text-ink-faint text-[10px] shrink-0">
                        {new Date(log.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <AdminPanel />
    </div>
  );
}
