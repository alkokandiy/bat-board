import React, { useState, useEffect } from 'react';
import { api, browserTimezone } from '../utils/api';

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
  { min: 0, max: 1999, title: 'The Orphan' },
  { min: 2000, max: 4999, title: 'The Vigilante' },
  { min: 5000, max: 9999, title: 'The Detective' },
  { min: 10000, max: 19999, title: 'Son of Gotham' },
  { min: 20000, max: 34999, title: 'The Caped Crusader' },
  { min: 35000, max: 54999, title: 'Heir of the Demon' },
  { min: 55000, max: 79999, title: 'The Dark Knight' },
  { min: 80000, max: 119999, title: 'Faris al-Khorasan' },
  { min: 120000, max: 179999, title: 'Sword of the Ummah' },
  { min: 180000, max: null, title: 'Dark Knight of Khorasan' },
];

export default function ProfileSettings({ account, onRefreshAccount }) {
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
  const [showLogs, setShowLogs] = useState(false);
  const [ledger, setLedger] = useState([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [addressDraft, setAddressDraft] = useState(account?.alfred_address || '');
  const [addressMsg, setAddressMsg] = useState(null);
  const [addressError, setAddressError] = useState(null);
  useEffect(() => { setAddressDraft(account?.alfred_address || ''); }, [account?.alfred_address]);

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
    try {
      await api.resetPoints();
      await onRefreshAccount();
    } catch (err) {
      alert(err.message);
    } finally {
      setResetting(false);
    }
  };

  const currentPoints = account?.points ?? 0;
  const currentLevel = account?.bat_level ?? 'The Orphan';

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
    } catch (err) {
      alert(err.message);
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
    } catch (err) {
      alert(err.message);
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
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
        <h1 className="text-2xl font-bold tracking-wider">PROFILE & SETTINGS</h1>
        <p className="text-xs text-slate-400">Manage your identity, credentials, and Bat Point ledger.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Bat Level Ladder */}
        <div className="bg-dark-slate rounded border border-slate-800 p-6">
          <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
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
                      ? 'bg-electric-bat-yellow/10 text-electric-bat-yellow border border-electric-bat-yellow/30'
                      : reqMet
                        ? 'text-slate-400'
                        : 'text-slate-600'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isCurrent && <span className="text-[10px]">{'>'}</span>}
                    <span>{lvl.title}</span>
                  </div>
                  <span className={isCurrent ? 'text-electric-bat-yellow' : 'text-slate-500'}>
                    {rangeStr}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-500 font-mono">
            Current: <span className="text-electric-bat-yellow font-bold">{currentPoints.toLocaleString()} BP</span> — {currentLevel}
          </div>
        </div>

        <div className="space-y-6">
          {/* Change Password */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              Change Password
            </h2>
            <form onSubmit={handlePasswordChange} className="space-y-3">
              <div className="text-xs">
                <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  required
                  className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow"
                />
              </div>
              <div className="text-xs">
                <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">New Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  required
                  minLength={8}
                  className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow"
                />
              </div>
              <div className="text-xs">
                <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  required
                  className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow"
                />
              </div>
              {pwMsg && <div className="text-xs text-green-400">{pwMsg}</div>}
              {pwError && <div className="text-xs text-red-400">{pwError}</div>}
              <button
                type="submit"
                className="px-5 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded text-xs font-mono tracking-widest hover:bg-yellow-400 transition"
              >
                UPDATE PASSWORD
              </button>
            </form>
          </div>

          {/* Alfred form of address */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              What Alfred Calls You
            </h2>
            <p className="text-xs text-slate-400 mb-3">
              Used in Telegram and the in-app chat. Leave empty to be addressed by your username ({account?.username}).
            </p>
            <form onSubmit={saveAddress} className="flex gap-2">
              <input
                type="text"
                value={addressDraft}
                onChange={e => { setAddressDraft(e.target.value); setAddressMsg(null); }}
                maxLength={60}
                placeholder={account?.username || 'e.g. Master Wayne'}
                className="flex-1 min-w-0 bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow"
              />
              <button
                type="submit"
                disabled={addressDraft.trim() === (account?.alfred_address || '')}
                className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded text-xs font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
              >
                SAVE
              </button>
            </form>
            {addressMsg && <div className="text-xs text-green-400 mt-2">{addressMsg}</div>}
            {addressError && <div className="text-xs text-red-400 mt-2">{addressError}</div>}
          </div>

          {/* Timezone */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              Timezone
            </h2>
            <p className="text-xs text-slate-400 mb-3">
              Days for habits, daily stats, and Alfred's clock and daily limit start at midnight in this zone.
            </p>
            <select
              value={accountTz}
              disabled={tzBusy}
              onChange={e => saveTimezone(e.target.value)}
              className="w-full bg-matte-obsidian border border-slate-800 rounded px-2.5 py-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-electric-bat-yellow disabled:opacity-50"
            >
              {timezoneOptions(accountTz).map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
            {deviceTz && deviceTz !== accountTz && (
              <button
                type="button"
                onClick={() => saveTimezone(deviceTz)}
                disabled={tzBusy}
                className="mt-3 text-[10px] font-mono tracking-widest text-slate-400 hover:text-electric-bat-yellow border border-slate-800 hover:border-electric-bat-yellow/50 rounded px-2 py-1 transition disabled:opacity-50"
              >
                USE THIS DEVICE'S ZONE ({deviceTz})
              </button>
            )}
            {tzError && <div className="text-xs text-red-400 mt-2">{tzError}</div>}
          </div>

          {/* Reset Points */}
          <div className="bg-dark-slate rounded border border-red-900/30 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-red-400 border-b border-red-900/30 pb-2 mb-4">
              Danger Zone
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Reset all Bat Points to 0. Your level will revert to The Orphan. This action is irreversible.
            </p>
            <button
              onClick={handleResetPoints}
              disabled={resetting}
              className="px-5 py-2 bg-red-900/30 border border-red-900/50 text-red-400 font-bold rounded text-xs font-mono tracking-widest hover:bg-red-900/50 transition disabled:opacity-50"
            >
              {resetting ? 'RESETTING...' : 'RESET BAT POINTS'}
            </button>

            <div className="mt-6 pt-4 border-t border-red-900/30">
              <p className="text-xs text-slate-400 mb-3">
                Start fresh with Alfred by permanently deleting your conversations.
              </p>
              <label className="flex items-center gap-2 text-xs text-slate-400 mb-4 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={eraseMemory}
                  onChange={e => setEraseMemory(e.target.checked)}
                  className="accent-red-500"
                />
                Also erase everything Alfred remembers about me (its memory notes)
              </label>
              {confirmingAlfredReset ? (
                <div role="alertdialog" aria-label="Confirm Alfred reset" className="rounded border border-red-900/60 bg-red-950/20 p-4 space-y-3">
                  <div className="text-xs font-bold text-red-400">This cannot be undone.</div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-red-400 mb-1">Will be deleted</div>
                    <ul className="text-xs text-slate-300 space-y-0.5 list-disc pl-4">
                      {alfredResetDeletes.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-green-400 mb-1">Will be kept</div>
                    <ul className="text-xs text-slate-400 space-y-0.5 list-disc pl-4">
                      {alfredResetKeeps.map(item => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                  <div className="text-[11px] text-slate-500">
                    The Telegram chat window itself isn't cleared — use "Clear history" in Telegram for that.
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={handleResetAlfred}
                      className="px-4 py-2 bg-red-700 text-white font-bold rounded text-xs font-mono tracking-widest hover:bg-red-600 transition"
                    >
                      DELETE PERMANENTLY
                    </button>
                    <button
                      onClick={() => setConfirmingAlfredReset(false)}
                      className="px-4 py-2 bg-slate-800 text-slate-300 rounded text-xs font-mono tracking-widest hover:bg-slate-700 transition"
                    >
                      CANCEL
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => { setAlfredResetMsg(null); setConfirmingAlfredReset(true); }}
                  disabled={alfredResetting}
                  className="px-5 py-2 bg-red-900/30 border border-red-900/50 text-red-400 font-bold rounded text-xs font-mono tracking-widest hover:bg-red-900/50 transition disabled:opacity-50"
                >
                  {alfredResetting ? 'RESETTING...' : 'RESET ALFRED'}
                </button>
              )}
              {alfredResetMsg && <div className="text-xs text-slate-400 mt-2">{alfredResetMsg}</div>}
            </div>
          </div>

          {/* Link Telegram */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              Link Telegram
            </h2>
            {tgLinked === null ? (
              <p className="text-xs text-slate-500 font-mono">Checking link status...</p>
            ) : tgLinked ? (
              <div className="space-y-3">
                <p className="text-xs text-green-400 font-mono">Linked ✓ — Alfred will respond to this Telegram account.</p>
                <button
                  onClick={handleUnlink}
                  disabled={tgBusy}
                  className="px-5 py-2 bg-matte-obsidian border border-slate-800 text-slate-300 font-bold rounded text-xs font-mono tracking-widest hover:border-red-900/50 hover:text-red-400 transition disabled:opacity-50"
                >
                  UNLINK
                </button>
              </div>
            ) : tgCode ? (
              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  Open Telegram, message the bot, and send this code. Expires in{' '}
                  <span className="text-electric-bat-yellow font-mono font-bold">{fmtExpiry(tgSecondsLeft)}</span>.
                </p>
                <div className="text-3xl font-mono font-bold tracking-[0.3em] text-electric-bat-yellow text-center py-2 bg-matte-obsidian rounded border border-slate-800">
                  {tgCode}
                </div>
                <button
                  onClick={handleGenerateCode}
                  disabled={tgBusy}
                  className="px-5 py-2 bg-matte-obsidian border border-slate-800 text-slate-300 font-bold rounded text-xs font-mono tracking-widest hover:border-electric-bat-yellow/50 transition disabled:opacity-50"
                >
                  REGENERATE CODE
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  Connect your Telegram account to chat with Alfred. Generate a code, then send it to the bot.
                </p>
                <button
                  onClick={handleGenerateCode}
                  disabled={tgBusy}
                  className="px-5 py-2 bg-electric-bat-yellow text-matte-obsidian font-bold rounded text-xs font-mono tracking-widest hover:bg-yellow-400 transition disabled:opacity-50"
                >
                  {tgBusy ? 'GENERATING...' : 'GENERATE LINK CODE'}
                </button>
              </div>
            )}
          </div>
          {/* Ledger Log */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 border-b border-slate-800 pb-2 mb-4">
              Ledger Log
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Immutable history of account modifications, completions, and point awards.
            </p>
            <button
              onClick={toggleLogs}
              className="px-5 py-2 bg-matte-obsidian border border-slate-800 text-slate-300 font-bold rounded text-xs font-mono tracking-widest hover:border-electric-bat-yellow/50 transition"
            >
              {showLogs ? 'HIDE LEDGER' : 'VIEW LEDGER'}
            </button>
            {showLogs && (
              <div className="mt-4 max-h-80 overflow-y-auto divide-y divide-slate-800 font-mono text-xs border border-slate-800 rounded">
                {ledgerLoading ? (
                  <div className="p-4 text-center text-slate-500">Loading ledger...</div>
                ) : ledger.length === 0 ? (
                  <div className="p-4 text-center text-slate-500">No ledger entries yet.</div>
                ) : ledger.map((log) => {
                  let summary = log.details;
                  try {
                    const d = JSON.parse(log.details);
                    summary = d.message || d.reason || log.details;
                  } catch {}
                  return (
                    <div key={log.id} className="px-3 py-2.5 flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="px-1.5 py-0.5 bg-slate-800 text-slate-300 rounded text-[10px] shrink-0">
                          {log.event_type}
                        </span>
                        <span className="text-slate-400 truncate">{summary}</span>
                      </div>
                      <span className="text-slate-600 text-[10px] shrink-0">
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
    </div>
  );
}
