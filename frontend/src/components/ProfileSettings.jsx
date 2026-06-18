import React, { useState } from 'react';
import { api } from '../utils/api';

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

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwMsg(null);
    setPwError(null);
    if (newPassword !== confirmPassword) {
      setPwError('Passwords do not match');
      return;
    }
    if (newPassword.length < 4) {
      setPwError('Password must be at least 4 characters');
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
                  minLength={4}
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
          </div>
        </div>
      </div>
    </div>
  );
}
