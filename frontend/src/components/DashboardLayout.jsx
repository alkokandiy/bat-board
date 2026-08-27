import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  LayoutDashboard,
  Target,
  Flame,
  Focus,
  Crosshair,
  Hourglass,
  Calendar,
  NotebookText,
  ScrollText,
  BarChart3,
  CircleUserRound,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const ICON_MAP = {
  dashboard: LayoutDashboard,
  missions: Target,
  habits: Flame,
  focus: Focus,
  johnwick: Crosshair,
  countdown: Hourglass,
  calendar: Calendar,
  notes: NotebookText,
  logs: ScrollText,
  stats: BarChart3,
  profile: CircleUserRound,
};

const SIDEBAR_WIDTH = 256;
const SIDEBAR_COLLAPSED_WIDTH = 72;

export default function DashboardLayout({ account, currentView, onViewChange = () => {}, onLogout = () => {}, activeTrack, isPlaying, onTogglePlay, onTrackChange, focusMode, children }) {
  const { username = "Loading...", points = 0, bat_level = "Loading..." } = account || {};

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('batboard_sidebar_collapsed') === 'true';
  });
  const [hoveredItem, setHoveredItem] = useState(null);
  const [pressedItem, setPressedItem] = useState(null);
  const [glowingItem, setGlowingItem] = useState(null);
  const [indicatorStyle, setIndicatorStyle] = useState({ top: 0, height: 0 });

  const navRefs = useRef({});
  const indicatorRef = useRef(null);
  const glowTimeoutRef = useRef(null);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'missions', label: 'Missions' },
    { id: 'habits', label: 'Habits' },
    { id: 'focus', label: 'Focus' },
    { id: 'johnwick', label: 'John Wick' },
    { id: 'countdown', label: 'Countdown' },
    { id: 'calendar', label: 'Calendar' },
    { id: 'notes', label: 'Notes' },
    { id: 'logs', label: 'Logs' },
    { id: 'stats', label: 'Stats' },
    { id: 'profile', label: 'Profile' },
  ];

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('batboard_sidebar_collapsed', String(next));
      return next;
    });
  }, []);

  const updateIndicator = useCallback(() => {
    const activeIdx = navItems.findIndex((item) => item.id === currentView);
    if (activeIdx === -1) return;
    const el = navRefs.current[currentView];
    if (!el) return;
    setIndicatorStyle({ top: el.offsetTop, height: el.offsetHeight });
  }, [currentView]);

  useEffect(() => {
    updateIndicator();
  }, [updateIndicator, sidebarCollapsed]);

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
    <div className="min-h-screen bg-matte-obsidian text-slate-100 flex flex-col font-sans">
      {!focusMode && (
        <header className="h-16 border-b border-dark-slate flex items-center justify-between px-6 bg-matte-obsidian z-10">
          <div className="flex items-center space-x-3">
            <span className="text-electric-bat-yellow text-2xl font-bold tracking-widest">BAT-BOARD</span>
            <span className="text-xs bg-dark-slate text-slate-400 px-2.5 py-1 rounded font-mono tracking-wider border border-slate-800">
              SYSTEM ONLINE
            </span>
          </div>

          <div className="flex items-center space-x-6">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-semibold text-slate-200">{username}</div>
              <div className="text-xs text-electric-bat-yellow font-mono tracking-wider font-semibold">
                {bat_level}
              </div>
            </div>
            <div className="h-10 px-4 bg-dark-slate rounded border border-slate-800 flex items-center justify-center space-x-2 font-mono">
              <span className="text-xs text-slate-400">PTS:</span>
              <span className="text-electric-bat-yellow font-bold text-sm">{points}</span>
            </div>
            <button
              onClick={onLogout}
              className="text-xs text-slate-500 hover:text-red-400 transition font-mono tracking-wider"
              title="Disconnect"
            >
              EXIT
            </button>
          </div>
        </header>
      )}

      <div className="flex flex-1 overflow-hidden">
        {!focusMode && (
          <aside
            className="border-r border-dark-slate bg-matte-obsidian flex flex-col justify-between py-6 shrink-0 hidden md:flex relative overflow-hidden"
            style={{
              width: isCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
              transition: 'width 260ms cubic-bezier(0.4, 0, 0.2, 1)',
            }}
          >
            <div className="flex flex-col flex-1">
              <div
                className="flex items-center px-4 mb-6"
                style={{
                  justifyContent: isCollapsed ? 'center' : 'flex-start',
                  paddingLeft: isCollapsed ? 0 : undefined,
                }}
              >
                {isCollapsed ? (
                  <div className="w-9 h-9 rounded bg-dark-slate border border-slate-700 flex items-center justify-center">
                    <span className="text-electric-bat-yellow text-sm font-bold">🦇</span>
                  </div>
                ) : (
                  <>
                    <span className="text-electric-bat-yellow text-lg font-bold tracking-widest mr-2">BAT-BOARD</span>
                    <span className="text-[10px] bg-dark-slate text-slate-400 px-2 py-0.5 rounded font-mono tracking-wider border border-slate-800">
                      ONLINE
                    </span>
                  </>
                )}
              </div>

              <nav className="space-y-1.5 px-4 flex-1 relative">
                {!isCollapsed && (
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-3 mb-3">
                    Operations Center
                  </p>
                )}

                <div className="relative">
                  <div
                    ref={indicatorRef}
                    className="absolute left-0 w-[3px] bg-electric-bat-yellow rounded-full"
                    style={{
                      top: indicatorStyle.top,
                      height: indicatorStyle.height,
                      transform: `translateY(0)`,
                      boxShadow: '0 0 8px rgba(255,215,0,0.4)',
                      transition: 'top 220ms cubic-bezier(0.4, 0, 0.2, 1), height 220ms cubic-bezier(0.4, 0, 0.2, 1)',
                    }}
                  />

                  {navItems.map((item) => {
                    const isActive = currentView === item.id;
                    const Icon = ICON_MAP[item.id];
                    const isHovered = hoveredItem === item.id;
                    const isPressed = pressedItem === item.id;
                    const isGlowing = glowingItem === item.id && isActive;

                    return (
                      <div key={item.id} className="relative" style={{ marginBottom: '2px' }}>
                        <button
                          ref={(el) => { navRefs.current[item.id] = el; }}
                          onClick={() => handleViewChange(item.id)}
                          onMouseEnter={() => setHoveredItem(item.id)}
                          onMouseLeave={() => { setHoveredItem(null); setPressedItem(null); }}
                          onMouseDown={() => setPressedItem(item.id)}
                          onMouseUp={() => setPressedItem(null)}
                          className={`w-full flex items-center rounded-md text-sm font-medium transition-all duration-150 ${
                            isCollapsed ? 'justify-center px-0 py-3' : 'space-x-3 px-4 py-3'
                          } ${
                            isActive
                              ? 'text-electric-bat-yellow'
                              : 'text-slate-400'
                          }`}
                          style={{
                            backgroundColor: isActive
                              ? 'rgba(44,44,44,0.6)'
                              : isHovered
                                ? 'rgba(44,44,44,0.5)'
                                : 'transparent',
                            transform: isPressed
                              ? 'scale(0.97)'
                              : isHovered
                                ? 'translateX(2px)'
                                : 'translateX(0)',
                            transition: 'background-color 150ms ease, transform 100ms ease',
                            paddingLeft: isCollapsed ? 0 : undefined,
                          }}
                        >
                          <div
                            className={`flex items-center justify-center ${isCollapsed ? '' : 'w-5 h-5 border border-current rounded'}`}
                            style={{
                              color: isActive ? '#FFD700' : isHovered ? '#e2e8f0' : '#94a3b8',
                              boxShadow: isGlowing ? '0 0 12px rgba(255,215,0,0.5)' : 'none',
                              transition: 'color 150ms ease, box-shadow 400ms ease',
                            }}
                          >
                            <Icon size={18} strokeWidth={1.5} />
                          </div>
                          {!isCollapsed && (
                            <span
                              className="tracking-wide"
                              style={{
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                opacity: 1,
                                transform: 'translateX(0)',
                                transition: 'opacity 200ms ease, transform 200ms ease',
                              }}
                            >
                              {item.label}
                            </span>
                          )}
                        </button>

                        {isCollapsed && isHovered && (
                          <div
                            className="absolute left-full ml-3 top-1/2 -translate-y-1/2 bg-matte-obsidian border border-slate-700 text-xs text-slate-200 px-2.5 py-1.5 rounded z-50 pointer-events-none"
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
            </div>

            {!isCollapsed && (
              <div className="px-6 text-center mt-4">
                <div className="text-[10px] font-mono text-slate-600">
                  BUILD v1.0.0 // ENCRYPTED
                </div>
              </div>
            )}

            <button
              onClick={toggleSidebar}
              className="absolute -right-[14px] top-6 w-[28px] h-[28px] rounded-full bg-dark-slate border border-slate-700 flex items-center justify-center hover:border-electric-bat-yellow transition-colors duration-200 z-20"
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <div style={{ transform: isCollapsed ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform 200ms ease' }}>
                <ChevronLeft size={14} strokeWidth={2} />
              </div>
            </button>
          </aside>
        )}

        <main className={`flex-1 bg-matte-obsidian overflow-y-auto ${focusMode ? 'p-0' : 'p-6 md:p-8'}`}>
          {children}
        </main>
      </div>

      {!focusMode && (
        <nav className="md:hidden border-t border-dark-slate bg-matte-obsidian h-16 flex items-center justify-around px-2 shrink-0">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            const Icon = ICON_MAP[item.id];
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`flex flex-col items-center justify-center py-2 px-2 ${isActive ? 'text-electric-bat-yellow' : 'text-slate-500'}`}
              >
                <span className="w-6 h-6 flex items-center justify-center">
                  <Icon size={16} strokeWidth={1.5} />
                </span>
                <span className="text-[9px] mt-1 font-semibold">{item.label}</span>
              </button>
            );
          })}
          <button onClick={onLogout} className="flex flex-col items-center justify-center py-2 px-2 text-slate-500">
            <span className="w-6 h-6 flex items-center justify-center text-xs font-bold border border-current rounded">X</span>
            <span className="text-[9px] mt-1 font-semibold">Exit</span>
          </button>
        </nav>
      )}
    </div>
  );
}
