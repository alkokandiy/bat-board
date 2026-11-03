import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ListChecks,
  Flame,
  Timer,
  CalendarDays,
  NotebookText,
  Briefcase,
  CircleUserRound,
  ChevronLeft,
} from 'lucide-react';

const ICON_MAP = {
  missions: ListChecks,
  habits: Flame,
  focus: Timer,
  calendar: CalendarDays,
  notes: NotebookText,
  work: Briefcase,
  profile: CircleUserRound,
};

const SIDEBAR_WIDTH = 256;
const SIDEBAR_COLLAPSED_WIDTH = 72;

// Stamped at build time by the Dockerfile (ARG BUILD_SHA). "dev" locally.
const BUILD_SHA = (import.meta.env.VITE_BUILD_SHA || 'dev').slice(0, 7);

export default function DashboardLayout({ account, currentView, onViewChange = () => {}, onLogout = () => {}, activeTrack, isPlaying, onTogglePlay, onTrackChange, focusMode, workEnabled = false, children }) {
  const { username = "Loading...", points = 0, bat_level = "Loading..." } = account || {};

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('batboard_sidebar_collapsed') === 'true';
  });
  const [hoveredItem, setHoveredItem] = useState(null);
  const [glowingItem, setGlowingItem] = useState(null);

  const glowTimeoutRef = useRef(null);

  // Work appears only when the user has the corporate track switched on. With
  // it off the entry is simply absent — not greyed out, not a dead end.
  const navItems = [
    { id: 'missions', label: 'Missions' },
    { id: 'habits', label: 'Habits' },
    { id: 'focus', label: 'Focus' },
    { id: 'calendar', label: 'Calendar' },
    { id: 'notes', label: 'Notes' },
    ...(workEnabled ? [{ id: 'work', label: 'Work' }] : []),
    { id: 'profile', label: 'Profile' },
  ];

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('batboard_sidebar_collapsed', String(next));
      return next;
    });
  }, []);

  useEffect(() => {
    if (glowingItem) {
      clearTimeout(glowTimeoutRef.current);
      glowTimeoutRef.current = setTimeout(() => setGlowingItem(null), 400);
    }
    return () => clearTimeout(glowTimeoutRef.current);
  }, [glowingItem]);

  const handleViewChange = useCallback((id) => {
    onViewChange(id);
    setGlowingItem(id);
  }, [onViewChange]);

  const isCollapsed = sidebarCollapsed;

  return (
    <div className="h-screen bg-bat-bg text-ink flex flex-col font-sans overflow-hidden">
      {!focusMode && (
        <header className="h-16 border-b border-white/[0.04] flex items-center justify-between px-6 bg-bat-surface z-10">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => onViewChange('dashboard')}
              className="font-display text-signal-self text-2xl tracking-widest hover:brightness-110 transition-all duration-200 ease-soft"
              title="Back to Command Center"
            >
              BAT-BOARD
            </button>
            <span className="text-[10px] bg-bat-raised text-ink-muted px-2.5 py-1 rounded-chip font-mono uppercase tracking-widest ring-1 ring-bat-line">
              SYSTEM ONLINE
            </span>
          </div>

          <div className="flex items-center space-x-6">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-semibold text-ink">{username}</div>
              <div className="text-[10px] text-signal-self font-mono uppercase tracking-widest font-semibold">
                {bat_level}
              </div>
            </div>
            <div className="h-10 px-4 bg-bat-raised rounded-chip ring-1 ring-bat-line flex items-center justify-center space-x-2 font-mono">
              <span className="text-[10px] text-ink-muted uppercase tracking-widest">pts</span>
              <span className="text-signal-self font-bold text-sm tabular-nums">{points}</span>
            </div>
            <button
              onClick={onLogout}
              className="text-[10px] text-ink-faint hover:text-signal-late transition-colors duration-200 font-mono uppercase tracking-widest"
              title="Disconnect"
            >
              EXIT
            </button>
          </div>
        </header>
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {!focusMode && (
          <aside
            className="border-r border-white/[0.04] bg-bat-surface flex flex-col shrink-0 hidden md:flex relative overflow-hidden"
            style={{
              width: isCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
              transition: 'width 260ms cubic-bezier(0.4, 0, 0.2, 1)',
            }}
          >
            {/* Toggle row — fully inside sidebar, no clipping */}
            <div
              className="flex items-center shrink-0"
              style={{
                height: 40,
                width: '100%',
                justifyContent: isCollapsed ? 'center' : 'flex-end',
                paddingRight: isCollapsed ? 0 : 16,
              }}
            >
              <button
                onClick={toggleSidebar}
                aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                aria-expanded={!isCollapsed}
                title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                className="group w-[26px] h-[26px] flex items-center justify-center rounded-full
                  bg-bat-raised ring-1 ring-bat-line text-ink-faint
                  hover:ring-signal-self/60 hover:text-signal-self
                  transition-all duration-200 ease-soft active:scale-[0.94]
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-self/60"
              >
                <ChevronLeft
                  size={18}
                  className={`transition-transform duration-200 ease-soft ${isCollapsed ? '' : 'rotate-180'}`}
                />
              </button>
            </div>

            <nav className="space-y-1.5 px-4 flex-1 relative">
              {!isCollapsed && (
                <p className="text-[10px] text-ink-faint font-mono uppercase tracking-[0.14em] px-3 mb-3">
                  Operations Center
                </p>
              )}

              {/* There was a sliding yellow rail here, positioned from
                  `offsetTop` measured on a render before the layout had
                  settled — so it pointed at the previous item as often as
                  the current one. The active row already says what it is
                  with its background, its colour and its ringed icon; a
                  fourth marker that is sometimes wrong is worse than none. */}
              <div className="relative">
                {navItems.map((item) => {
                  const isActive = currentView === item.id;
                  const Icon = ICON_MAP[item.id];
                  const isHovered = hoveredItem === item.id;
                  const isGlowing = glowingItem === item.id && isActive;

                  return (
                    <div key={item.id} className="relative" style={{ marginBottom: 2 }}>
                      <button
                        onClick={() => handleViewChange(item.id)}
                        onMouseEnter={() => setHoveredItem(item.id)}
                        onMouseLeave={() => setHoveredItem(null)}
                        className={`group w-full flex items-center rounded-tile text-sm font-medium
                          transition-all duration-200 ease-soft active:scale-[0.97]
                          focus:outline-none focus-visible:ring-1 focus-visible:ring-signal-self/60 ${
                          isCollapsed ? 'justify-center px-0 py-3' : 'px-4 py-3'
                        } ${
                          isActive
                            ? 'text-signal-self bg-bat-raised'
                            : 'text-ink-muted hover:text-ink hover:bg-bat-raised/60 hover:translate-x-0.5'
                        }`}
                        style={{ gap: isCollapsed ? 0 : 12 }}
                      >
                        <div
                          className={`w-8 h-8 flex items-center justify-center rounded-chip shrink-0 ring-1
                            transition-all duration-200 ease-soft ${
                            isActive
                              ? 'ring-signal-self text-signal-self'
                              : 'ring-bat-line text-ink-faint group-hover:ring-bat-line-strong group-hover:text-ink-muted'
                          } ${isGlowing ? 'shadow-glow-self' : ''}`}
                        >
                          <Icon size={18} />
                        </div>
                        {!isCollapsed && (
                          <span
                            className="tracking-wide"
                            style={{
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                            }}
                          >
                            {item.label}
                          </span>
                        )}
                      </button>

                      {isCollapsed && isHovered && (
                        <div
                          className="absolute left-full ml-3 top-1/2 -translate-y-1/2 bg-bat-raised ring-1 ring-bat-line-strong shadow-lift text-xs text-ink px-2.5 py-1.5 rounded-chip z-50 pointer-events-none"
                          style={{ whiteSpace: 'nowrap' }}
                        >
                          {item.label}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </nav>

            {!isCollapsed && (
              <div className="px-6 text-center mt-4 shrink-0">
                {/* The real commit, not a hard-coded "v1.0.0". A stale
                    frontend ran against a current backend for weeks and
                    nothing on screen could say so. */}
                <div className="text-[10px] font-mono text-ink-faint" title="Build this page was compiled from">
                  BUILD {BUILD_SHA} // ENCRYPTED
                </div>
              </div>
            )}
          </aside>
        )}

        <main className={`flex-1 min-h-0 bg-bat-bg overflow-y-auto ${focusMode ? 'p-0' : 'p-6 md:p-8'}`}>
          {children}
        </main>
      </div>

      {!focusMode && (
        <nav className="md:hidden border-t border-white/[0.04] bg-bat-surface h-16 flex items-center justify-around px-2 shrink-0">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            const Icon = ICON_MAP[item.id];
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`flex flex-col items-center justify-center py-2 px-2 transition-colors duration-200 ${isActive ? 'text-signal-self' : 'text-ink-faint'}`}
              >
                <span className="w-6 h-6 flex items-center justify-center">
                  <Icon size={16} strokeWidth={1.5} />
                </span>
                <span className="text-[9px] mt-1 font-semibold">{item.label}</span>
              </button>
            );
          })}
          <button onClick={onLogout} aria-label="Sign out" className="flex flex-col items-center justify-center py-2 px-2 text-ink-faint hover:text-signal-late transition-colors duration-200">
            <span className="w-6 h-6 flex items-center justify-center text-xs font-bold border border-current rounded">X</span>
            <span className="text-[9px] mt-1 font-semibold">Exit</span>
          </button>
        </nav>
      )}
    </div>
  );
}
