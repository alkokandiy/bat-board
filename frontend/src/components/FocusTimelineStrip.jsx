import React, { useEffect, useState } from 'react';
import { api } from '../utils/api';

const MINUTES_IN_DAY = 1440;

const fmtDuration = (minutes) => {
  const m = minutes || 0;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h > 0) return `${h}h ${mm}m`;
  return `${mm}m`;
};

// Mission is the person's own work, so it gets the yellow. The rest are
// deliberately quiet: a day should read as its shape first, its labels second.
const TYPE_STYLES = {
  mission: 'bg-signal-self',
  habit: 'bg-signal-work/55',
  work: 'bg-signal-good/45',
  none: 'bg-bat-line-strong/70 opacity-60',
};

const TYPE_LABELS = {
  mission: 'Mission',
  habit: 'Habit',
  work: 'Work',
  none: 'Unattributed',
};

const HOUR_LABELS = [0, 6, 12, 18, 24];

export default function FocusTimelineStrip({ day }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    api.getFocusDay(day)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not load this day.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [day]);

  const total = data ? data.total_minutes : 0;

  return (
    <div className="rounded-card bg-gradient-to-b from-bat-surface to-bat-bg ring-1 ring-bat-line shadow-tile p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <span className="text-[10px] font-mono uppercase tracking-widest text-ink-muted">THE DAY</span>
        <span className="text-xs font-mono text-ink-muted tabular-nums">
          {data ? fmtDuration(total) : '—'}
        </span>
      </div>

      {error && (
        <div className="rounded-chip bg-signal-late/10 ring-1 ring-signal-late/30 px-3 py-2 text-[11px] text-signal-late">
          {error}
        </div>
      )}

      {!error && loading && !data && (
        <div className="py-8 text-center text-ink-faint font-mono text-xs">LOADING THE DAY...</div>
      )}

      {!error && data && (
        <>
          <div
            data-testid="focus-track"
            className="relative h-16 rounded-tile bg-bat-surface ring-1 ring-bat-line overflow-hidden"
          >
            {Array.from({ length: 24 }, (_, i) => (
              <span
                key={i}
                data-testid="focus-hour-tick"
                aria-hidden="true"
                className="absolute inset-y-0 border-l border-bat-line/60"
                style={{ left: `${(i / 24) * 100}%` }}
              />
            ))}

            {data.sessions.map((session) => {
              const width = Math.max(0, session.end_minute - session.start_minute);
              const label = session.name || TYPE_LABELS[session.type] || 'Focus';
              const title = `${label} · ${fmtDuration(session.minutes)}`;
              return (
                <div
                  key={session.id}
                  data-testid={`focus-block-${session.id}`}
                  role="img"
                  aria-label={`${title}${session.running ? ', running' : ''}`}
                  title={title}
                  className={`absolute top-1 bottom-1 rounded-chip ${TYPE_STYLES[session.type] || TYPE_STYLES.none}
                    ${session.running ? 'animate-pulse ring-2 ring-ink/70' : ''}`}
                  style={{
                    left: `${(session.start_minute / MINUTES_IN_DAY) * 100}%`,
                    width: `${(width / MINUTES_IN_DAY) * 100}%`,
                    minWidth: '3px',
                  }}
                />
              );
            })}

            {data.now_minute !== null && data.now_minute !== undefined && (
              <span
                data-testid="now-line"
                aria-hidden="true"
                className="absolute inset-y-0 w-px bg-signal-self shadow-glow-self z-10"
                style={{ left: `${(data.now_minute / MINUTES_IN_DAY) * 100}%` }}
              />
            )}
          </div>

          <div className="relative h-4 mt-1.5">
            {HOUR_LABELS.map((hour) => (
              <span
                key={hour}
                className="absolute top-0 text-[9px] font-mono text-ink-faint tabular-nums"
                style={{
                  left: `${(hour / 24) * 100}%`,
                  transform: hour === 0 ? 'translateX(0)' : hour === 24 ? 'translateX(-100%)' : 'translateX(-50%)',
                }}
              >
                {hour}:00
              </span>
            ))}
          </div>

          {data.sessions.length === 0 && (
            <p data-testid="focus-empty" className="mt-2 text-[11px] font-mono text-ink-faint">
              Nothing logged this day — the empty track is the record.
            </p>
          )}
        </>
      )}
    </div>
  );
}
