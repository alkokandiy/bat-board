import React, { useState } from 'react';
import { api } from '../utils/api';

export default function LogsPanel({ initialLogs, onRefreshLogs }) {
  const [logs, setLogs] = useState(initialLogs || []);
  const [dateFilter, setDateFilter] = useState('all');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [loading, setLoading] = useState(false);

  const handleFilter = async (filter, start = '', end = '') => {
    setDateFilter(filter);
    setLoading(true);
    let startDate = '';
    let endDate = '';
    const now = new Date();

    if (filter === '7d') {
      const d = new Date(now); d.setDate(d.getDate() - 7);
      startDate = d.toISOString().slice(0, 19);
    } else if (filter === '21d') {
      const d = new Date(now); d.setDate(d.getDate() - 21);
      startDate = d.toISOString().slice(0, 19);
    } else if (filter === '30d') {
      const d = new Date(now); d.setDate(d.getDate() - 30);
      startDate = d.toISOString().slice(0, 19);
    } else if (filter === '60d') {
      const d = new Date(now); d.setDate(d.getDate() - 60);
      startDate = d.toISOString().slice(0, 19);
    } else if (filter === 'custom') {
      startDate = start ? new Date(start).toISOString().slice(0, 19) : '';
      endDate = end ? new Date(end + 'T23:59:59').toISOString().slice(0, 19) : '';
    }

    try {
      const data = await api.getLogs(200, startDate, endDate);
      setLogs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (dateFilter === 'custom') {
      await handleFilter('custom', customStart, customEnd);
    } else {
      await handleFilter(dateFilter);
    }
    if (onRefreshLogs) onRefreshLogs();
  };

  const filters = [
    { key: 'all', label: 'All' },
    { key: '7d', label: '7 days' },
    { key: '21d', label: '21 days' },
    { key: '30d', label: '30 days' },
    { key: '60d', label: '60 days' },
    { key: 'custom', label: 'Custom' },
  ];

  return (
    <div className="space-y-6">
      <div className="border-l-4 border-electric-bat-yellow pl-4 py-1 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-wider">LEDGER SECURITY LOG</h1>
          <p className="text-xs text-slate-400">Cryptographically secure immutable history tracking account modifications.</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-800 rounded font-mono text-[10px] tracking-wider transition disabled:opacity-50"
        >
          {loading ? 'LOADING...' : 'REFRESH FEED'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {filters.map(f => (
          <button
            key={f.key}
            onClick={() => {
              if (f.key !== 'custom') handleFilter(f.key);
              setDateFilter(f.key);
            }}
            className={`px-3 py-1.5 rounded text-[10px] font-mono tracking-wider border transition ${
              dateFilter === f.key
                ? 'bg-electric-bat-yellow/10 border-electric-bat-yellow text-electric-bat-yellow'
                : 'bg-matte-obsidian border-slate-800 text-slate-400 hover:border-slate-700'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {dateFilter === 'custom' && (
        <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
          <div>
            <label className="text-slate-500 text-[10px] mr-1">From:</label>
            <input
              type="date"
              value={customStart}
              onChange={e => setCustomStart(e.target.value)}
              className="bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-300 focus:outline-none focus:border-electric-bat-yellow"
            />
          </div>
          <div>
            <label className="text-slate-500 text-[10px] mr-1">To:</label>
            <input
              type="date"
              value={customEnd}
              onChange={e => setCustomEnd(e.target.value)}
              className="bg-matte-obsidian border border-slate-800 rounded px-2 py-1.5 text-slate-300 focus:outline-none focus:border-electric-bat-yellow"
            />
          </div>
          <button
            onClick={() => handleFilter('custom', customStart, customEnd)}
            className="px-3 py-1.5 bg-electric-bat-yellow text-matte-obsidian rounded text-[10px] font-bold font-mono tracking-wider hover:bg-yellow-400 transition"
          >
            APPLY
          </button>
        </div>
      )}

      <div className="bg-dark-slate rounded border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800 bg-matte-obsidian flex justify-between items-center">
          <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">LOG METADATA RECORD</span>
          <span className="text-xs font-mono text-slate-500">Showing {logs.length} entries</span>
        </div>
        <div className="divide-y divide-slate-800 font-mono text-xs">
          {logs.length === 0 ? (
            <div className="p-6 text-center text-slate-500">No cryptographic log ledger entries captured yet.</div>
          ) : (
            (() => {
              const grouped = {};
              logs.forEach((log) => {
                const dateKey = new Date(log.timestamp).toLocaleDateString('en-US', {
                  weekday: 'short',
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                });
                if (!grouped[dateKey]) grouped[dateKey] = [];
                grouped[dateKey].push(log);
              });

              return Object.entries(grouped).map(([date, entries]) => (
                <div key={date}>
                  <div className="px-4 py-2 bg-matte-obsidian border-b border-slate-800 flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-electric-bat-yellow/60" />
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{date}</span>
                    <span className="text-[9px] text-slate-600">({entries.length} event{entries.length !== 1 ? 's' : ''})</span>
                  </div>
                  {entries.map((log) => {
                    let parsedDetails = {};
                    try {
                      parsedDetails = JSON.parse(log.details);
                    } catch {
                      parsedDetails = { raw: log.details };
                    }
                    return (
                      <div key={log.id} className="px-4 py-3 hover:bg-slate-900/50 transition flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800/50 last:border-b-0">
                        <div className="flex items-center gap-3">
                          <div className="w-1.5 h-1.5 rounded-full bg-slate-700 shrink-0" />
                          <div className="space-y-1">
                            <span className="px-2 py-0.5 bg-slate-800 text-slate-300 rounded text-[10px]">
                              {log.event_type}
                            </span>
                            <span className="text-slate-300">
                              {parsedDetails.message || parsedDetails.reason || JSON.stringify(parsedDetails)}
                            </span>
                          </div>
                        </div>
                        <span className="text-slate-500 text-[10px] shrink-0 md:ml-4">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ));
            })()
          )}
        </div>
      </div>
    </div>
  );
}
