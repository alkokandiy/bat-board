import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from './components/DashboardLayout';
import MissionsPanel from './components/MissionsPanel';
import HabitsPanel from './components/HabitsPanel';
import FocusPanel from './components/FocusPanel';
import JohnWickPanel from './components/JohnWickPanel';
import CountdownPanel from './components/CountdownPanel';
import CalendarPanel from './components/CalendarPanel';
import NotesPanel from './components/NotesPanel';
import ProfileSettings from './components/ProfileSettings';
import LogsPanel from './components/LogsPanel';
import AudioPlayer, { trackPresets } from './components/AudioPlayer';
import { api } from './utils/api';

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    setError(null);
    try {
      if (isRegister) {
        await api.register(username, password);
      }
      await api.login(username, password);
      onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-matte-obsidian text-slate-100 flex flex-col items-center justify-center font-sans px-4">
      <div className="max-w-sm w-full space-y-8">
        <div className="text-center space-y-2">
          <div className="text-electric-bat-yellow text-5xl font-bold tracking-widest">BAT-BOARD</div>
          <p className="text-xs text-slate-500 font-mono tracking-widest">SECURE GATEWAY</p>
        </div>
        <form onSubmit={handleSubmit} className="bg-dark-slate p-6 rounded-lg border border-slate-800 space-y-4">
          <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300">
            {isRegister ? 'Establish Identity' : 'Authenticate'}
          </h2>
          {error && (
            <div className="p-3 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs">{error}</div>
          )}
          <div>
            <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="The Dark Knight"
              className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-slate-400 mb-1 font-mono uppercase tracking-wider text-[10px]">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-matte-obsidian border border-slate-800 rounded px-3 py-2 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-electric-bat-yellow"
              required
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-electric-bat-yellow text-matte-obsidian font-bold rounded hover:bg-yellow-400 transition font-mono tracking-widest disabled:opacity-50"
          >
            {loading ? 'AUTHORIZING...' : isRegister ? 'REGISTER IDENTITY' : 'GAIN ACCESS'}
          </button>
          <button
            type="button"
            onClick={() => { setIsRegister(!isRegister); setError(null); }}
            className="w-full text-xs text-slate-500 hover:text-slate-300 transition font-mono tracking-wider"
          >
            {isRegister ? 'Already have access? Sign in' : 'New operative? Register'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [account, setAccount] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentView, setCurrentView] = useState('dashboard');
  const [missions, setMissions] = useState([]);
  const [habits, setHabits] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTrack, setActiveTrack] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [focusMode, setFocusMode] = useState(false);

  const fetchAllData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [acc, miss, habs, lg] = await Promise.all([
        api.getAccount(),
        api.getMissions(),
        api.getHabits(),
        api.getLogs(30),
      ]);
      setAccount(acc);
      setMissions(miss);
      setHabits(habs);
      setLogs(lg);
      setIsAuthenticated(true);
    } catch (err) {
      if (err.message.includes('Session expired')) {
        setIsAuthenticated(false);
        setAccount(null);
      } else {
        setError(err.message);
        setIsAuthenticated(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('bat_access_token');
    if (token) {
      fetchAllData();
    } else {
      setLoading(false);
    }

    const handleLogout = () => {
      setIsAuthenticated(false);
      setAccount(null);
      setMissions([]);
      setHabits([]);
      setLogs([]);
    };
    window.addEventListener('auth:logout', handleLogout);

    const refreshInterval = setInterval(async () => {
      try {
        await api.refreshToken();
      } catch {}
    }, 60 * 60 * 1000);

    return () => {
      window.removeEventListener('auth:logout', handleLogout);
      clearInterval(refreshInterval);
    };
  }, [fetchAllData]);

  const handleLogin = async () => {
    try {
      await fetchAllData();
    } catch {
      // error is already set by fetchAllData
    }
  };

  const handleRefreshAccount = async () => {
    try {
      setAccount(await api.getAccount());
      setLogs(await api.getLogs(30));
    } catch (err) {
      console.error(err);
    }
  };

  const handleRefreshMissions = async () => {
    try {
      setMissions(await api.getMissions());
    } catch (err) {
      console.error(err);
    }
  };

  const handleRefreshHabits = async () => {
    try {
      setHabits(await api.getHabits());
    } catch (err) {
      console.error(err);
    }
  };

  const handleRefreshLogs = async () => {
    try {
      setLogs(await api.getLogs(30));
    } catch (err) {
      console.error(err);
    }
  };

  const handleLogout = () => {
    api.logout();
    setIsAuthenticated(false);
    setAccount(null);
    setCurrentView('dashboard');
  };

  const handleTrackChange = (track) => {
    if (!track) {
      setActiveTrack(null);
      setIsPlaying(false);
    } else if (activeTrack?.id === track.id) {
      setIsPlaying(!isPlaying);
    } else {
      setActiveTrack(track);
      setIsPlaying(true);
    }
  };

  const handleTogglePlay = () => {
    if (!activeTrack) {
      setActiveTrack(trackPresets[0]);
      setIsPlaying(true);
    } else {
      setIsPlaying(!isPlaying);
    }
  };

  if (loading && localStorage.getItem('bat_access_token')) {
    return (
      <div className="min-h-screen bg-matte-obsidian text-slate-100 flex flex-col items-center justify-center font-sans">
        <div className="text-center space-y-4">
          <div className="text-electric-bat-yellow text-4xl animate-pulse font-bold tracking-widest">BAT-BOARD</div>
          <div className="text-xs text-slate-500 font-mono tracking-widest">DECRYPTING SECURITY LEDGER...</div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  if (error) {
    return (
      <div className="min-h-screen bg-matte-obsidian text-slate-100 flex flex-col items-center justify-center font-sans px-4">
        <div className="max-w-md w-full bg-dark-slate p-6 rounded-lg border border-red-950 text-center space-y-4">
          <div className="text-red-500 text-3xl font-bold">BOOT CRITICAL ERROR</div>
          <p className="text-sm text-slate-300">{error}</p>
          <div className="pt-2">
            <button
              onClick={fetchAllData}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold rounded text-xs transition duration-200"
            >
              RETRY BOOT SEQUENCING
            </button>
          </div>
        </div>
      </div>
    );
  }

  const renderView = () => {
    switch (currentView) {
      case 'missions':
        return (
          <MissionsPanel
            missions={missions}
            onRefreshMissions={handleRefreshMissions}
            onRefreshAccount={handleRefreshAccount}
          />
        );
      case 'habits':
        return (
          <HabitsPanel
            habits={habits}
            onRefreshHabits={handleRefreshHabits}
            onRefreshAccount={handleRefreshAccount}
          />
        );
      case 'focus':
        return (
          <FocusPanel
            activeTrack={activeTrack}
            isPlaying={isPlaying}
            onTrackChange={handleTrackChange}
            missions={missions}
            habits={habits}
            onRefreshMissions={handleRefreshMissions}
            onRefreshHabits={handleRefreshHabits}
            onRefreshAccount={handleRefreshAccount}
            onFocusModeChange={setFocusMode}
            focusMode={focusMode}
          />
        );
      case 'johnwick':
        return (
          <JohnWickPanel
            activeTrack={activeTrack}
            isPlaying={isPlaying}
            onTrackChange={handleTrackChange}
            missions={missions}
            onRefreshMissions={handleRefreshMissions}
            onRefreshAccount={handleRefreshAccount}
            onFocusModeChange={setFocusMode}
          />
        );
      case 'countdown':
        return <CountdownPanel />;
      case 'calendar':
        return <CalendarPanel />;
      case 'notes':
        return <NotesPanel />;
      case 'profile':
        return <ProfileSettings account={account} onRefreshAccount={handleRefreshAccount} />;
      case 'logs':
        return (
          <LogsPanel
            initialLogs={logs}
            onRefreshLogs={handleRefreshLogs}
          />
        );
      default:
        return (
          <div className="space-y-6">
            <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
              <h1 className="text-2xl font-bold tracking-wider">BATCAVE COMMAND CENTER</h1>
              <p className="text-xs text-slate-400">Tactical overview of ongoing Gotham defense protocols.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-dark-slate p-5 rounded border border-slate-800 flex flex-col justify-between h-36">
                <div>
                  <span className="text-slate-400 text-xs font-mono uppercase tracking-widest">Active Missions</span>
                  <div className="text-3xl font-bold mt-2 text-slate-100">
                    {missions.filter(m => m.status === 'pending').length}
                  </div>
                </div>
                <div className="text-xs text-slate-500">Missions queued for tactical execution.</div>
              </div>
              <div className="bg-dark-slate p-5 rounded border border-slate-800 flex flex-col justify-between h-36">
                <div>
                  <span className="text-slate-400 text-xs font-mono uppercase tracking-widest">Habit Streaks</span>
                  <div className="text-3xl font-bold mt-2 text-electric-bat-yellow">
                    {habits.reduce((max, h) => Math.max(max, h.streak || 0), 0)} Day Max
                  </div>
                </div>
                <div className="text-xs text-slate-500">Highest ritual continuity metric.</div>
              </div>
              <div className="bg-dark-slate p-5 rounded border border-slate-800 flex flex-col justify-between h-36">
                <div>
                  <span className="text-slate-400 text-xs font-mono uppercase tracking-widest">Current Bat Level</span>
                  <div className="text-lg font-bold mt-2 text-electric-bat-yellow font-mono truncate">
                    {account?.bat_level}
                  </div>
                </div>
                <div className="text-xs text-slate-500">Level upgrade triggers automatically at points tier.</div>
              </div>
            </div>
            <div className="bg-dark-slate rounded border border-slate-800 p-6">
              <h2 className="text-sm font-mono uppercase tracking-widest text-slate-300 mb-4 border-b border-slate-800 pb-2">
                Operational Status
              </h2>
              <div className="text-xs text-slate-400 leading-relaxed max-w-2xl space-y-3">
                <p>Welcome to Bat-Board, premium tactical control desk optimized for personal productivity and operations tracking.</p>
                <p>Use the side navigation panel to log daily habits, track mission completion logs, and observe the secure ledger log system tracking all your points and activities.</p>
              </div>
            </div>
          </div>
        );
    }
  };

  return (
    <DashboardLayout
      account={account}
      currentView={currentView}
      onViewChange={setCurrentView}
      onLogout={handleLogout}
      activeTrack={activeTrack}
      isPlaying={isPlaying}
      onTogglePlay={handleTogglePlay}
      onTrackChange={handleTrackChange}
      focusMode={focusMode}
    >
      {renderView()}
      <AudioPlayer
        activeTrack={activeTrack}
        isPlaying={isPlaying}
        onToggle={handleTogglePlay}
        onTrackChange={handleTrackChange}
        hideUI={focusMode}
      />
    </DashboardLayout>
  );
}