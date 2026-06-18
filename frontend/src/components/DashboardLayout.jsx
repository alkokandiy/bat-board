import React from 'react';

export default function DashboardLayout({ account, currentView, onViewChange = () => {}, onLogout = () => {}, activeTrack, isPlaying, onTogglePlay, onTrackChange, focusMode, children }) {
  const { username = "Loading...", points = 0, bat_level = "Loading..." } = account || {};

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'B' },
    { id: 'missions', label: 'Missions', icon: 'M' },
    { id: 'habits', label: 'Habits', icon: 'H' },
    { id: 'focus', label: 'Focus', icon: 'F' },
    { id: 'johnwick', label: 'John Wick', icon: 'J' },
    { id: 'countdown', label: 'Countdown', icon: 'C' },
    { id: 'calendar', label: 'Calendar', icon: 'E' },
    { id: 'logs', label: 'Logs', icon: 'L' },
    { id: 'profile', label: 'Profile', icon: 'P' },
  ];

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
          <aside className="w-64 border-r border-dark-slate bg-matte-obsidian flex flex-col justify-between py-6 shrink-0 hidden md:flex">
            <nav className="space-y-1.5 px-4">
              <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest px-3 mb-3">
                Operations Center
              </p>
              {navItems.map((item) => {
                const isActive = currentView === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onViewChange(item.id)}
                    className={`w-full flex items-center space-x-3 px-4 py-3 rounded-md text-sm font-medium transition-all duration-200 ${
                      isActive
                        ? 'bg-dark-slate text-electric-bat-yellow border-l-2 border-electric-bat-yellow'
                        : 'text-slate-400 hover:bg-dark-slate hover:text-slate-200'
                    }`}
                  >
                    <span className="w-5 h-5 flex items-center justify-center text-xs font-bold border border-current rounded">
                      {item.icon}
                    </span>
                    <span className="tracking-wide">{item.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="px-6 text-center">
              <div className="text-[10px] font-mono text-slate-600">
                BUILD v1.0.0 // ENCRYPTED
              </div>
            </div>
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
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`flex flex-col items-center justify-center py-2 px-2 ${isActive ? 'text-electric-bat-yellow' : 'text-slate-500'}`}
              >
                <span className="w-6 h-6 flex items-center justify-center text-xs font-bold border border-current rounded">
                  {item.icon}
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