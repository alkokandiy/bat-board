import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

const TABS = [
  { key: 'overview', label: 'OVERVIEW' },
  { key: 'day', label: 'DAY' },
  { key: 'records', label: 'RECORDS' },
];

const PERIODS = [
  { key: 'day', label: 'DAY' },
  { key: 'week', label: 'WEEK' },
  { key: 'month', label: 'MONTH' },
  { key: 'year', label: 'YEAR' },
  { key: 'all', label: 'ALL' },
];

const TREND_GRANULARITIES = [
  { key: 'day', label: 'DAY' },
  { key: 'week', label: 'WEEK' },
  { key: 'month', label: 'MONTH' },
];

const WEEKDAY_HEADERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const YELLOW = '#FFD700';
const AMBER = '#f59e0b';
const SLATE = '#64748b';
const RED = '#dc2626';
const TAG_PALETTE = ['#FFD700', '#f59e0b', '#eab308', '#fbbf24', '#a16207'];

const fmtDuration = (minutes) => {
  const m = minutes || 0;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h > 0) return `${h}h ${mm}m`;
  return `${mm}m`;
};

const toISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const heatColor = (minutes) => {
  if (minutes <= 0) return 'bg-slate-800';
  if (minutes <= 15) return 'bg-electric-bat-yellow/20';
  if (minutes <= 30) return 'bg-electric-bat-yellow/50';
  if (minutes <= 60) return 'bg-electric-bat-yellow/75';
  return 'bg-electric-bat-yellow';
};

const tabClass = (active) =>
  active
    ? 'px-3 py-1.5 rounded text-[10px] font-mono tracking-wider border bg-electric-bat-yellow text-dark-slate font-bold border-electric-bat-yellow'
    : 'px-3 py-1.5 rounded text-[10px] font-mono tracking-wider border bg-transparent border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-300';

const BatIcon = () => (
  <svg width="14" height="8" viewBox="0 0 24 14" fill="#FFD700">
    <path d="M 12 0 C 10.5 2 7 2 4 0 C 2 2 0 6 0 9 C 3 9 6 7 8 5 C 9 8 11 12 12 14 C 13 12 15 8 16 5 C 18 7 21 9 24 9 C 24 6 22 2 20 0 C 17 2 13.5 2 12 0 Z" />
  </svg>
);

const Donut = ({ segments, size = 150, stroke = 18, centerText, centerSub }) => {
  const total = segments.reduce((a, s) => a + s.value, 0);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={stroke} />
        {total > 0 &&
          segments.map((seg, i) => {
            const len = (seg.value / total) * c;
            const el = (
              <circle
                key={i}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={seg.color}
                strokeOpacity={seg.opacity ?? 1}
                strokeWidth={stroke}
                strokeDasharray={`${len} ${Math.max(0, c - len)}`}
                strokeDashoffset={-offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
              />
            );
            offset += len;
            return el;
          })}
        {centerText !== undefined && (
          <text
            x="50%"
            y="50%"
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="18"
            fill="#f1f5f9"
            fontFamily="Share Tech Mono, monospace"
          >
            {centerText}
          </text>
        )}
        {centerSub && (
          <text
            x="50%"
            y="62%"
            textAnchor="middle"
            fontSize="9"
            fill="#64748b"
            fontFamily="Share Tech Mono, monospace"
          >
            {centerSub}
          </text>
        )}
      </svg>
    </div>
  );
};

const TrendChart = ({ points }) => {
  const W = 600;
  const H = 160;
  const PAD = 14;
  const values = points.map((p) => p.minutes);
  const maxVal = Math.max(...values, 0);
  const yScale = maxVal > 0 ? maxVal : 1;
  const step = values.length > 1 ? (W - PAD * 2) / (values.length - 1) : 0;
  const x = (i) => PAD + i * step;
  const y = (v) => H - PAD - (v / yScale) * (H - PAD * 2);

  let path = `M ${x(0)},${y(values[0])}`;
  for (let i = 0; i < values.length - 1; i++) {
    const mx = (x(i) + x(i + 1)) / 2;
    path += ` C ${mx},${y(values[i])} ${mx},${y(values[i + 1])} ${x(i + 1)},${y(values[i + 1])}`;
  }

  const allZero = maxVal === 0;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line
          x1={PAD}
          y1={y(maxVal)}
          x2={W - PAD}
          y2={y(maxVal)}
          stroke="#1e293b"
          strokeWidth="1"
        />
        <path d={path} fill="none" stroke={YELLOW} strokeWidth="2" strokeLinecap="round" />
        {!allZero &&
          values.map((v, i) => (
            <circle key={i} cx={x(i)} cy={y(v)} r="2.5" fill={YELLOW} />
          ))}
        {values.map((p, i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 2}
            textAnchor="middle"
            fontSize="9"
            fill="#64748b"
            fontFamily="Share Tech Mono, monospace"
          >
            {p.label}
          </text>
        ))}
      </svg>
      {allZero && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-mono text-slate-500">No sessions yet this period</span>
        </div>
      )}
    </div>
  );
};

export default function StatsPanel() {
  const [tab, setTab] = useState('overview');

  const [period, setPeriod] = useState('week');
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [tiles, setTiles] = useState(null);

  const [trendGranularity, setTrendGranularity] = useState('day');
  const [trend, setTrend] = useState(null);
  const [trendLoading, setTrendLoading] = useState(false);

  const [dayDate, setDayDate] = useState(() => new Date());
  const [dayData, setDayData] = useState(null);
  const [dayLoading, setDayLoading] = useState(false);
  const [dayError, setDayError] = useState(null);
  const [dayView, setDayView] = useState('type');

  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  const loadStats = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      setStats(await api.getFocusStats(p));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTiles = useCallback(async () => {
    try {
      const [today, allTime] = await Promise.all([
        api.getFocusStats('day'),
        api.getFocusStats('all'),
      ]);
      setTiles({
        todaySessions: today.total_sessions,
        todayMinutes: today.total_minutes,
        totalSessions: allTime.total_sessions,
        totalMinutes: allTime.total_minutes,
      });
    } catch {
      // Tiles are decorative — fail silently.
    }
  }, []);

  const loadTrend = useCallback(async (g) => {
    setTrendLoading(true);
    try {
      setTrend(await api.getFocusTrend(g));
    } catch {
      setTrend(null);
    } finally {
      setTrendLoading(false);
    }
  }, []);

  const loadDay = useCallback(async (d) => {
    setDayLoading(true);
    setDayError(null);
    try {
      setDayData(await api.getDayStats(toISODate(d)));
    } catch (err) {
      setDayError(err.message);
    } finally {
      setDayLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async (reset = false) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const offset = reset ? 0 : history.length;
      const data = await api.getFocusSessionLog(20, offset);
      setHistory((prev) => (reset ? data.items : [...prev, ...data.items]));
      setHistoryTotal(data.total);
    } catch (err) {
      setHistoryError(err.message);
    } finally {
      setHistoryLoading(false);
    }
  }, [history.length]);

  useEffect(() => {
    loadStats(period);
  }, [period, loadStats]);

  useEffect(() => {
    loadTiles();
  }, [loadTiles]);

  useEffect(() => {
    loadTrend(trendGranularity);
  }, [trendGranularity, loadTrend]);

  useEffect(() => {
    loadDay(dayDate);
  }, [dayDate, loadDay]);

  useEffect(() => {
    loadHistory(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = () => {
    loadStats(period);
    loadTiles();
    loadTrend(trendGranularity);
    loadDay(dayDate);
    loadHistory(true);
  };

  const displayRows = stats
    ? [...stats.breakdown].sort((a, b) => {
        if (a.type === 'none') return 1;
        if (b.type === 'none') return -1;
        return b.minutes - a.minutes;
      })
    : [];

  const todayISO = toISODate(new Date());
  const selectedISO = toISODate(dayDate);
  const isToday = selectedISO === todayISO;
  const canGoForward = selectedISO < todayISO;

  const prevDay = () => setDayDate((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1));
  const nextDay = () => setDayDate((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1));

  const statusSegments = dayData
    ? [
        { key: 'on_time', label: 'On Time', value: dayData.status_distribution.on_time, color: YELLOW },
        { key: 'overdue', label: 'Overdue', value: dayData.status_distribution.overdue, color: RED, opacity: 0.7 },
        { key: 'uncompleted', label: 'Uncompleted', value: dayData.status_distribution.uncompleted, color: SLATE },
      ]
    : [];

  const typeSegments = dayData
    ? dayData.type_distribution.map((t, i) => ({
        key: t.type,
        label: t.type === 'mission' ? 'Mission' : 'Habit',
        value: t.count,
        color: i % 2 === 0 ? YELLOW : AMBER,
      }))
    : [];

  const tagSegments = dayData
    ? dayData.tag_distribution.map((t, i) => ({
        key: t.tag,
        label: t.tag,
        value: t.count,
        color: t.tag === 'untagged' ? SLATE : TAG_PALETTE[i % TAG_PALETTE.length],
      }))
    : [];

  const statusTotal = statusSegments.reduce((a, s) => a + s.value, 0);

  const groupedHistory = [];
  history.forEach((s) => {
    const d = new Date(s.start_time);
    const key = toISODate(d);
    const last = groupedHistory[groupedHistory.length - 1];
    if (last && last.date === key) {
      last.items.push(s);
    } else {
      groupedHistory.push({ date: key, label: `${d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase()} ${d.getDate()}`, items: [s] });
    }
  });

  const formatTime = (iso) =>
    new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

  const renderOverview = () => (
    <div className="space-y-6">
      {/* Stat tiles — always today/all-time, independent of period toggle */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Today's Sessions", value: tiles ? String(tiles.todaySessions) : '–' },
          { label: "Today's Focus", value: tiles ? fmtDuration(tiles.todayMinutes) : '–' },
          { label: 'Total Sessions', value: tiles ? String(tiles.totalSessions) : '–' },
          { label: 'Total Focus Duration', value: tiles ? fmtDuration(tiles.totalMinutes) : '–' },
        ].map((t) => (
          <div key={t.label} className="bg-dark-slate p-4 rounded border border-slate-800">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">{t.label}</div>
            <div className="text-xl font-bold text-slate-100 font-mono">{t.value}</div>
          </div>
        ))}
      </div>

      {/* Period toggle + totals */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {PERIODS.map((p) => (
            <button key={p.key} data-testid={`period-${p.key}`} onClick={() => setPeriod(p.key)} className={tabClass(period === p.key)}>
              {p.label}
            </button>
          ))}
        </div>

        {loading && !stats && (
          <div className="p-8 text-center text-slate-500 font-mono text-xs">CALCULATING DEEP WORK...</div>
        )}

        {stats && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-dark-slate p-5 rounded border border-slate-800">
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Total Focus</div>
              <div className="text-3xl font-bold text-electric-bat-yellow font-mono">{fmtDuration(stats.total_minutes)}</div>
            </div>
            <div className="bg-dark-slate p-5 rounded border border-slate-800">
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Sessions</div>
              <div className="text-3xl font-bold text-slate-100 font-mono">{stats.total_sessions}</div>
            </div>
            <div className="bg-dark-slate p-5 rounded border border-slate-800">
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Streak</div>
              <div className="text-3xl font-bold text-slate-100 font-mono flex items-center gap-2">
                {stats.current_streak_days > 0 && <BatIcon />}
                {stats.current_streak_days} day{stats.current_streak_days !== 1 ? 's' : ''}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Heatmap */}
      {stats && (
        <div className="bg-dark-slate rounded border border-slate-800 p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">FOCUS HEATMAP</span>
            <span className="text-[10px] font-mono text-slate-500">LAST 35 DAYS</span>
          </div>
          <div className="grid grid-cols-7 gap-1.5 mb-1.5">
            {WEEKDAY_HEADERS.map((d, i) => (
              <div key={i} className="text-center text-[9px] font-mono text-slate-600">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {stats.daily_heatmap.map((cell) => (
              <div key={cell.date} title={`${cell.date} · ${cell.minutes} min`} className={`aspect-square rounded ${heatColor(cell.minutes)}`} />
            ))}
          </div>
          <div className="flex items-center justify-end gap-2 mt-4 text-[9px] font-mono text-slate-600">
            Less
            <div className="w-3 h-3 rounded bg-slate-800" />
            <div className="w-3 h-3 rounded bg-electric-bat-yellow/20" />
            <div className="w-3 h-3 rounded bg-electric-bat-yellow/50" />
            <div className="w-3 h-3 rounded bg-electric-bat-yellow/75" />
            <div className="w-3 h-3 rounded bg-electric-bat-yellow" />
            More
          </div>
        </div>
      )}

      {/* Recent Focus Curve */}
      <div className="bg-dark-slate rounded border border-slate-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">RECENT FOCUS CURVE</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-slate-600 hidden sm:inline">FOCUS MINUTES</span>
            <div className="flex items-center gap-1.5">
              {TREND_GRANULARITIES.map((g) => (
                <button key={g.key} data-testid={`trend-gran-${g.key}`} onClick={() => setTrendGranularity(g.key)} className={`px-2 py-1 rounded text-[9px] font-mono tracking-wider border transition ${tabClass(trendGranularity === g.key)}`}>
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        {trendLoading && !trend ? (
          <div className="h-40 flex items-center justify-center text-slate-500 font-mono text-xs">PLOTTING...</div>
        ) : trend ? (
          <TrendChart points={trend.points} />
        ) : (
          <div className="h-40 flex items-center justify-center text-slate-500 font-mono text-xs">No sessions yet this period</div>
        )}
      </div>

      {/* Breakdown ranking */}
      {stats && (
        <div className="bg-dark-slate rounded border border-slate-800 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">WHERE THE TIME WENT</span>
            <span className="text-[10px] font-mono text-slate-500">{fmtDuration(stats.total_minutes)} total</span>
          </div>
          {displayRows.length === 0 ? (
            <div className="p-6 text-center text-slate-500 font-mono text-xs">No completed focus sessions in this period.</div>
          ) : (
            displayRows.map((item) => {
              const isUnassigned = item.type === 'none';
              return (
                <div key={`${item.type}-${item.id}`} className={isUnassigned ? 'opacity-60' : ''}>
                  <div className="flex items-center justify-between gap-3 mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`text-sm truncate ${isUnassigned ? 'text-slate-500' : 'text-slate-200'}`}>{item.name}</span>
                      <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider shrink-0">
                        {item.type === 'mission' ? 'MISSION' : item.type === 'habit' ? 'HABIT' : 'UNASSIGNED'}
                      </span>
                      <span className="text-[10px] font-mono text-slate-600 shrink-0">
                        {item.sessions} session{item.sessions !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <span className="text-xs font-mono text-slate-400 shrink-0">{fmtDuration(item.minutes)}</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${isUnassigned ? 'bg-slate-600' : 'bg-electric-bat-yellow'}`}
                      style={{ width: `${Math.max(0, Math.min(100, item.percent))}%` }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );

  const legendItem = (color, label, value, opacity) => (
    <div key={label} className="flex items-center justify-between gap-4 text-xs">
      <span className="flex items-center gap-2 text-slate-400">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color, opacity: opacity ?? 1 }} />
        {label}
      </span>
      <span className="text-slate-200 font-mono">{value}</span>
    </div>
  );

  const renderDay = () => (
    <div className="space-y-6">
      {/* Date navigator */}
      <div className="flex items-center justify-center gap-4">
        <button onClick={prevDay} className="w-6 h-6 flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded transition">
          ←
        </button>
        <div className="text-sm font-mono text-slate-100 w-28 text-center">
          {isToday ? 'Today' : dayDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        </div>
        <button
          onClick={nextDay}
          disabled={!canGoForward}
          className="w-6 h-6 flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded transition disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-slate-400"
        >
          →
        </button>
      </div>

      {dayLoading && !dayData && (
        <div className="p-8 text-center text-slate-500 font-mono text-xs">GATHERING RECORDS...</div>
      )}
      {dayError && <div className="p-4 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs font-mono">{dayError}</div>}

      {dayData && dayData.total_count === 0 && (
        <div className="p-10 text-center text-slate-500 font-mono text-xs">Nothing scheduled this day.</div>
      )}

      {dayData && dayData.total_count > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left: completed + rate */}
            <div className="bg-dark-slate rounded border border-slate-800 p-6 flex flex-col justify-center gap-5">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Completed</div>
                <div data-testid="day-completed" className="text-3xl font-bold text-slate-100 font-mono">
                  {dayData.completed_count} <span className="text-slate-500 text-xl">/ {dayData.total_count}</span>
                </div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Completion Rate</div>
                <div data-testid="day-rate" className="text-3xl font-bold text-electric-bat-yellow font-mono">{dayData.completion_rate}%</div>
                {dayData.completed_not_due_today > 0 && (
                  <div className="text-[10px] font-mono text-slate-500 mt-2">
                    +{dayData.completed_not_due_today} completed early / overdue-cleared
                  </div>
                )}
              </div>
            </div>

            {/* Right: status donut */}
            <div className="bg-dark-slate rounded border border-slate-800 p-6">
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-4">Completion Rate Distribution</div>
              {statusTotal === 0 ? (
                <div className="py-8 text-center text-slate-500 font-mono text-xs">No missions due this day.</div>
              ) : (
                <div className="flex flex-col items-center gap-5">
                  <Donut
                    segments={statusSegments}
                    centerText={`${dayData.completion_rate}%`}
                    centerSub="RATE"
                  />
                  <div className="w-full max-w-[220px] space-y-2">
                    {statusSegments.map((s) => legendItem(s.color, s.label, s.value, s.opacity))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Classified completion statistics */}
          <div className="bg-dark-slate rounded border border-slate-800 p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">Classified Completion Statistics</span>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setDayView('type')} className={tabClass(dayView === 'type')}>TYPE</button>
                <button onClick={() => setDayView('tag')} className={tabClass(dayView === 'tag')}>TAG</button>
              </div>
            </div>
            {dayView === 'type' ? (
              typeSegments.length === 0 ? (
                <div className="py-8 text-center text-slate-500 font-mono text-xs">Nothing completed this day.</div>
              ) : (
                <div className="flex flex-col items-center gap-5">
                  <Donut segments={typeSegments} centerText={String(typeSegments.reduce((a, s) => a + s.value, 0))} centerSub="DONE" />
                  <div className="w-full max-w-[220px] space-y-2">
                    {typeSegments.map((s) => legendItem(s.color, s.label, s.value))}
                  </div>
                </div>
              )
            ) : tagSegments.length === 0 ? (
              <div className="py-8 text-center text-slate-500 font-mono text-xs">Nothing completed this day.</div>
            ) : (
              <div className="flex flex-col items-center gap-5">
                <Donut segments={tagSegments} centerText={String(tagSegments.reduce((a, s) => a + s.value, 0))} centerSub="TAGS" />
                <div className="w-full max-w-[220px] space-y-2">
                  {tagSegments.map((s) => legendItem(s.color, s.label, s.value))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );

  const renderRecords = () => (
    <div className="bg-dark-slate rounded border border-slate-800 overflow-hidden">
      <div className="p-4 border-b border-slate-800 bg-matte-obsidian flex justify-between items-center">
        <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">SESSION HISTORY</span>
        <span className="text-xs font-mono text-slate-500">Showing {history.length} of {historyTotal} sessions</span>
      </div>
      <div>
        {historyError && <div className="p-4 text-red-400 font-mono text-xs">{historyError}</div>}
        {history.length === 0 && !historyLoading && !historyError && (
          <div className="p-6 text-center text-slate-500 font-mono text-xs">No completed focus sessions captured yet.</div>
        )}
        {groupedHistory.map((group) => (
          <div key={group.date} className="px-4 pt-5 pb-1">
            <div className="text-[11px] text-slate-400 tracking-wide border-b border-slate-800 pb-2 mb-1">{group.label}</div>
            {group.items.map((s) => {
              const name = s.mission_name || s.habit_name || 'Unassigned';
              const isUnassigned = !s.mission_name && !s.habit_name;
              const range = s.end_time ? `${formatTime(s.start_time)} — ${formatTime(s.end_time)}` : formatTime(s.start_time);
              return (
                <div key={s.id} className="py-2.5">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-full bg-electric-bat-yellow shrink-0" />
                    <span className="text-slate-300 font-mono text-[12px]">
                      {range} <span className="text-slate-500">·</span> {fmtDuration(s.duration_minutes)}
                    </span>
                  </div>
                  <div className={`ml-[18px] text-[14px] ${isUnassigned ? 'text-slate-500' : 'text-slate-200'}`}>{name}</div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      {history.length < historyTotal && (
        <div className="p-4 border-t border-slate-800 bg-matte-obsidian flex justify-center">
          <button
            onClick={() => loadHistory(false)}
            disabled={historyLoading}
            className="px-4 py-2 bg-electric-bat-yellow text-matte-obsidian rounded text-[10px] font-bold font-mono tracking-wider hover:bg-yellow-400 transition disabled:opacity-50"
          >
            {historyLoading ? 'LOADING...' : 'LOAD MORE'}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-wider">FOCUS STATS</h1>
          <p className="text-xs text-slate-400">Where the deep work actually goes.</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-800 rounded font-mono text-[10px] tracking-wider transition disabled:opacity-50"
        >
          {loading ? 'LOADING...' : 'REFRESH FEED'}
        </button>
      </div>

      {/* Sub-tabs */}
      <div className="flex items-center gap-2">
        {TABS.map((t) => (
          <button key={t.key} data-testid={`stats-tab-${t.key}`} onClick={() => setTab(t.key)} className={tabClass(tab === t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="p-4 bg-red-950/40 border border-red-900 rounded text-red-400 text-xs font-mono">
          {error}
        </div>
      )}

      {tab === 'overview' && renderOverview()}
      {tab === 'day' && renderDay()}
      {tab === 'records' && renderRecords()}
    </div>
  );
}