import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import DashboardLayout from './components/DashboardLayout';
import MissionsPanel from './components/MissionsPanel';
import HabitsPanel from './components/HabitsPanel';
import FocusPanel from './components/FocusPanel';
import CountdownSection from './components/CountdownSection';
import CalendarPanel from './components/CalendarPanel';
import NotesPanel from './components/NotesPanel';
import WorkPanel from './components/WorkPanel';
import ProfileSettings from './components/ProfileSettings';
import StatsPanel from './components/StatsPanel';
import { PageHeader, StatTile, EmptyState, Panel } from './components/ui';
import AlfredWidget from './components/AlfredWidget';
import AudioPlayer, { trackPresets } from './components/AudioPlayer';
import { api } from './utils/api';
import { FOCUS_MODE_TO_API } from './utils/focusModes';

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
      // The server trims usernames on registration; trim here too so
      // " batman" can still log in as "batman".
      const name = username.trim();
      if (isRegister) {
        await api.register(name, password);
      }
      await api.login(name, password);
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
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTrack, setActiveTrack] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  // Is the corporate track switched on? Drives the sidebar entry and the
  // dashboard tile. Defaults to off, so a failed/absent status never shows a
  // work side that cannot work.
  const [workEnabled, setWorkEnabled] = useState(false);

  // Focus timer state - persists across tab switches
  // 25 is folklore — it came from the inventor's kitchen timer, and no study
  // has ever compared it against anything. The real default is the user's own
  // median session, fetched at boot; this is only the value before that lands.
  const [focusSessionLength, setFocusSessionLength] = useState(30);
  const [focusSuggestion, setFocusSuggestion] = useState(null);
  const [focusTimeLeft, setFocusTimeLeft] = useState(25 * 60);
  const [focusRunning, setFocusRunning] = useState(false);
  const [focusSelectedMissionId, setFocusSelectedMissionId] = useState('');
  const [focusSelectedHabitId, setFocusSelectedHabitId] = useState('');
  const [focusNotice, setFocusNotice] = useState(null);
  // Timer visual mode ('N' | 'F' | 'B' | 'M'). Lives here, not in the timer:
  // entering focus mode mounts a second timer, which used to reset it, and the
  // session start below needs to record it.
  const [focusVisualMode, setFocusVisualMode] = useState('N');
  const focusVisualModeRef = useRef(focusVisualMode);
  focusVisualModeRef.current = focusVisualMode;
  const focusSessionIdRef = useRef(null);
  const focusStartTimeRef = useRef(null);
  const focusSessionStartRef = useRef(null);
  // Milliseconds the timer actually ran for the current session. Pauses are
  // excluded: crediting wall-clock time since start counted paused time too.
  const focusActiveMsRef = useRef(0);
  const focusTimerRef = useRef(null);

  const fetchAllData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [acc, miss, habs] = await Promise.all([
        api.getAccount(),
        api.getMissions(),
        api.getHabits(),
      ]);
      setAccount(acc);
      setMissions(miss);
      setHabits(habs);
      setIsAuthenticated(true);
      // Deliberately after the boot data and never awaited into it: work is
      // optional, so if this call fails the dashboard still comes up and the
      // work entry simply stays hidden.
      api.getWorkStatus()
        .then((st) => setWorkEnabled(!!st.enabled))
        .catch(() => setWorkEnabled(false));

      // Their own median session length, once they have enough history for
      // one. Kept off the boot path: a failure here must not block the board.
      api.getSuggestedFocusMinutes()
        .then((s) => {
          // Kept, not just applied: the Focus screen says WHERE the number
          // came from, because "25 minutes" with no provenance is exactly the
          // folklore this replaced.
          setFocusSuggestion(s || null);
          if (s?.basis === 'history' && s.minutes > 0) setFocusSessionLength(s.minutes);
        })
        .catch(() => {});
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
      setWorkEnabled(false);
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
    } catch (err) {
      console.error(err);
    }
  };

  // One place decides what "work is off" means for the UI: hide the entry and
  // leave the work view if that is where the user happens to be standing.
  const handleWorkEnabledChange = useCallback((enabled) => {
    setWorkEnabled(!!enabled);
    if (!enabled) {
      setCurrentView((view) => (view === 'work' ? 'dashboard' : view));
    }
  }, []);

  const handleWorkStatus = useCallback((st) => {
    handleWorkEnabledChange(!!st?.enabled);
  }, [handleWorkEnabledChange]);

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

  // Focus timer interval - uses Date.now() for accuracy across browser tab throttling
  useEffect(() => {
    if (!focusRunning) {
      clearInterval(focusTimerRef.current);
      return;
    }
    focusStartTimeRef.current = Date.now();
    const expectedInterval = 1000;
    focusTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - focusStartTimeRef.current;
      const ticks = Math.floor(elapsed / expectedInterval);
      if (ticks >= 1) {
        focusStartTimeRef.current += ticks * expectedInterval;
        focusActiveMsRef.current += ticks * expectedInterval;
        setFocusTimeLeft((prev) => {
          const next = prev - ticks;
          return next > 0 ? next : 0;
        });
      }
    }, 200);
    return () => clearInterval(focusTimerRef.current);
  }, [focusRunning]);

  const endFocusSession = useCallback(async () => {
    const sid = focusSessionIdRef.current;
    if (!sid) return;
    focusSessionIdRef.current = null;
    focusSessionStartRef.current = null;
    // Time the timer actually ran (Date.now()-based ticks, so accurate even
    // when the tab is backgrounded/throttled), excluding pauses. The server
    // additionally caps this at the session's wall-clock span.
    const durationMin = Math.max(0, Math.round(focusActiveMsRef.current / 60000));
    focusActiveMsRef.current = 0;
    try {
      const res = await api.endFocusSession(sid, { duration_minutes: durationMin });
      // Sessions under the 5-minute minimum are discarded server-side.
      setFocusNotice(res?.discarded ? 'Under 5 minutes — session not counted.' : null);
      handleRefreshMissions();
      handleRefreshAccount();
    } catch (err) {
      console.error(err);
    }
  }, [handleRefreshMissions, handleRefreshAccount]);

  // Natural completion: persist the session exactly once when timeLeft hits 0.
  // Declared after endFocusSession (its dep array must not reference a TDZ
  // binding). endFocusSession() nulls focusSessionIdRef first, so it can never
  // double-fire.
  useEffect(() => {
    if (focusRunning && focusTimeLeft === 0) {
      setFocusRunning(false);
      endFocusSession();
    }
  }, [focusRunning, focusTimeLeft, endFocusSession]);

  const startFocusSession = useCallback(async (missionId, habitId) => {
    focusActiveMsRef.current = 0;
    setFocusNotice(null);
    try {
      const data = {};
      if (missionId) data.mission_id = parseInt(missionId);
      if (habitId) data.habit_id = parseInt(habitId);
      // Recorded at start only; switching mode mid-session doesn't change it.
      const mode = FOCUS_MODE_TO_API[focusVisualModeRef.current];
      if (mode) data.mode = mode;
      const session = await api.startFocusSession(data);
      focusSessionIdRef.current = session.id;
      focusSessionStartRef.current = Date.now();
    } catch (err) {
      console.error(err);
    }
  }, []);

  const handleFocusToggle = useCallback(() => {
    if (focusRunning) {
      setFocusRunning(false);
      return;
    }
    // Starting or resuming. Only create a backend session on the FIRST start;
    // pausing is a frontend-only state, so resume must not open a new row.
    if (focusTimeLeft === 0) {
      setFocusTimeLeft(focusSessionLength * 60);
    }
    if (!focusSessionIdRef.current) {
      startFocusSession(focusSelectedMissionId, focusSelectedHabitId);
    }
    setFocusRunning(true);
  }, [focusRunning, focusTimeLeft, focusSessionLength, focusSelectedMissionId, focusSelectedHabitId, startFocusSession]);

  // Leaving focus mode (EXIT FOCUS / STOP & LOG) ends the session and logs the
  // time — previously exiting left the session open forever, so web focus work
  // was never credited unless the countdown happened to reach zero.
  const handleFocusModeChange = useCallback(async (active) => {
    setFocusMode(active);
    if (active) return;
    setFocusRunning(false);
    clearInterval(focusTimerRef.current);
    await endFocusSession();
    setFocusTimeLeft(focusSessionLength * 60);
  }, [endFocusSession, focusSessionLength]);

  const handleFocusAdjustTime = useCallback((delta) => {
    setFocusTimeLeft((prev) => {
      const next = Math.max(0, prev + delta);
      return next;
    });
  }, []);

  const handleFocusSessionChange = useCallback((minutes) => {
    setFocusSessionLength(minutes);
    setFocusTimeLeft(minutes * 60);
  }, []);

  const handleFocusReset = useCallback(async () => {
    clearInterval(focusTimerRef.current);
    if (focusSessionIdRef.current) {
      await endFocusSession();
    }
    setFocusRunning(false);
    setFocusTimeLeft(focusSessionLength * 60);
  }, [focusSessionLength, endFocusSession]);

  const handleFocusExit = useCallback(async () => {
    await handleFocusReset();
    setFocusMode(false);
    if (document.fullscreenElement) await document.exitFullscreen();
  }, [handleFocusReset]);

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

  // --- what the dashboard actually reports -----------------------------
  // Computed once, in one place, so the header strip and the tiles can never
  // disagree with each other about the same board.
  const openMissions = useMemo(
    () => missions.filter((m) => m.status === 'pending' && !m.is_dismissed),
    [missions]);

  const overdueMissions = useMemo(() => {
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    return openMissions.filter((m) => m.due_date && new Date(m.due_date) < startOfToday);
  }, [openMissions]);

  const dueTodayMissions = useMemo(() => {
    const d = new Date();
    const key = d.toDateString();
    return openMissions.filter((m) => m.due_date && new Date(m.due_date).toDateString() === key);
  }, [openMissions]);

  const bestStreak = useMemo(
    () => habits.reduce((max, h) => Math.max(max, h.streak || 0), 0), [habits]);

  // null means "no habits at all", which is a different thing from "none left".
  const habitsLeftToday = useMemo(() => {
    if (!habits.length) return null;
    const today = new Date().toDateString();
    return habits.filter(
      (h) => !(h.last_completed && new Date(h.last_completed).toDateString() === today)).length;
  }, [habits]);

  const dashboardStats = useMemo(() => {
    const out = [{ label: 'open', value: openMissions.length }];
    if (overdueMissions.length) out.push({ label: 'overdue', value: overdueMissions.length, tone: 'late' });
    if (dueTodayMissions.length) out.push({ label: 'due today', value: dueTodayMissions.length, tone: 'warn' });
    if (habitsLeftToday) out.push({ label: 'habits left', value: habitsLeftToday, tone: 'warn' });
    return out;
  }, [openMissions, overdueMissions, dueTodayMissions, habitsLeftToday]);

  const todayLabel = useMemo(
    () => new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' }), []);

  const operationalLines = useMemo(() => {
    const lines = [];
    if (overdueMissions.length) {
      lines.push({
        dot: 'bg-signal-late',
        text: `${overdueMissions.length} mission${overdueMissions.length === 1 ? '' : 's'} past ${overdueMissions.length === 1 ? 'its' : 'their'} date — oldest: ${overdueMissions[0].title}`,
      });
    }
    if (dueTodayMissions.length) {
      lines.push({
        dot: 'bg-signal-warn',
        text: `Due today: ${dueTodayMissions.slice(0, 3).map((m) => m.title).join(', ')}`,
      });
    }
    if (habitsLeftToday) {
      lines.push({ dot: 'bg-signal-warn', text: `${habitsLeftToday} habit${habitsLeftToday === 1 ? '' : 's'} still to keep today` });
    } else if (habitsLeftToday === 0) {
      lines.push({ dot: 'bg-signal-good', text: 'Every habit kept today' });
    }
    if (!overdueMissions.length && openMissions.length) {
      lines.push({ dot: 'bg-signal-good', text: 'Nothing overdue' });
    }
    return lines;
  }, [overdueMissions, dueTodayMissions, habitsLeftToday, openMissions]);

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
          <div className="space-y-6">
            <FocusPanel
              activeTrack={activeTrack}
              isPlaying={isPlaying}
              onTrackChange={handleTrackChange}
              missions={missions}
              habits={habits}
              onRefreshMissions={handleRefreshMissions}
              onRefreshHabits={handleRefreshHabits}
              onRefreshAccount={handleRefreshAccount}
              onFocusModeChange={handleFocusModeChange}
              timerMode={focusVisualMode}
              onTimerModeChange={setFocusVisualMode}
              focusMode={focusMode}
              focusTimeLeft={focusTimeLeft}
              focusTotalTime={focusSessionLength * 60}
              focusRunning={focusRunning}
              focusSessionLength={focusSessionLength}
              focusSuggestion={focusSuggestion}
              focusSelectedMissionId={focusSelectedMissionId}
              focusSelectedHabitId={focusSelectedHabitId}
              focusNotice={focusNotice}
              onFocusMissionChange={setFocusSelectedMissionId}
              onFocusHabitChange={setFocusSelectedHabitId}
              onFocusToggle={handleFocusToggle}
              onFocusAdjustTime={handleFocusAdjustTime}
              onFocusSessionChange={handleFocusSessionChange}
              onFocusReset={handleFocusReset}
              onFocusExit={handleFocusExit}
            />
            <StatsPanel />
          </div>
        );
      case 'calendar':
        return <CalendarPanel />;
      case 'notes':
        return <NotesPanel />;
      case 'work':
        return <WorkPanel onStatusChange={handleWorkStatus} />;
      case 'profile':
        return (
          <ProfileSettings
            account={account}
            onRefreshAccount={handleRefreshAccount}
            workEnabled={workEnabled}
            onWorkEnabledChange={handleWorkEnabledChange}
          />
        );
      default:
        return (
          <div className="space-y-6">
            <div className="border-l-4 border-electric-bat-yellow pl-4 py-1">
              {/* The header carries facts now. "Tactical overview of ongoing
                  Gotham defense protocols" occupied the most valuable line on
                  the screen and said nothing about the board. */}
              <PageHeader
                title="BATCAVE COMMAND CENTER"
                stats={dashboardStats}
              />
            </div>
            <div className={`grid grid-cols-1 gap-4 ${workEnabled ? 'md:grid-cols-2 xl:grid-cols-4' : 'md:grid-cols-3'}`}>
              {/* Only the tile that needs a decision is emphasised. Four
                  identical tiles told the eye nothing about where to look. */}
              <StatTile
                label="Active Missions"
                value={openMissions.length}
                hint={overdueMissions.length
                  ? `${overdueMissions.length} past their date`
                  : 'nothing overdue'}
                tone="late"
                attention={overdueMissions.length > 0}
                onClick={() => setCurrentView('missions')}
              />
              <StatTile
                label="Habit Streaks"
                value={bestStreak ? `${bestStreak}d` : '—'}
                hint={habitsLeftToday === null
                  ? 'no habits yet'
                  : habitsLeftToday === 0
                    ? 'all kept today'
                    : `${habitsLeftToday} still to keep today`}
                tone={habitsLeftToday ? 'warn' : 'good'}
                attention={!!habitsLeftToday}
                onClick={() => setCurrentView('habits')}
              />
              <StatTile
                label="Bat Level"
                value={account?.bat_level || '—'}
                hint={account ? `${account.points} BP` : null}
                tone="self"
                onClick={() => setCurrentView('focus')}
              />
              {workEnabled && (
                <StatTile
                  label="Corporate Track"
                  value="THE JOB"
                  hint="earns no Bat Points, by design"
                  tone="work"
                  onClick={() => setCurrentView('work')}
                />
              )}
            </div>
            <CountdownSection />
            {/* Was a welcome blurb that never changed. It now reports the
                day, because that is what an operational status is. */}
            <Panel title="Operational Status" meta={todayLabel}>
              {operationalLines.length === 0 ? (
                <EmptyState compact>Nothing logged yet today</EmptyState>
              ) : (
                <ul className="space-y-1.5">
                  {operationalLines.map((line) => (
                    <li key={line.text} className="flex items-baseline gap-2 text-xs">
                      <span className={`w-1 h-1 rounded-full shrink-0 translate-y-[-2px] ${line.dot}`} aria-hidden="true" />
                      <span className="text-ink-muted">{line.text}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
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
      workEnabled={workEnabled}
    >
      {renderView()}
      <AudioPlayer
        activeTrack={activeTrack}
        isPlaying={isPlaying}
        onToggle={handleTogglePlay}
        onTrackChange={handleTrackChange}
        hideUI={focusMode}
      />
      {!focusMode && <AlfredWidget account={account} />}
    </DashboardLayout>
  );
}