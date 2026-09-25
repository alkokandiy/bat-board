const API_BASE_URL = import.meta.env.DEV
  ? (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api')
  : '/api';

function getTokens() {
  try {
    const access = localStorage.getItem('bat_access_token');
    const refresh = localStorage.getItem('bat_refresh_token');
    return { access, refresh };
  } catch {
    return { access: null, refresh: null };
  }
}

function setTokens(access, refresh) {
  localStorage.setItem('bat_access_token', access);
  localStorage.setItem('bat_refresh_token', refresh);
}

function clearTokens() {
  localStorage.removeItem('bat_access_token');
  localStorage.removeItem('bat_refresh_token');
}

let isRefreshing = false;
let refreshQueue = [];

async function refreshAccessToken() {
  const { refresh } = getTokens();
  if (!refresh) throw new Error('No refresh token');

  const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  if (!res.ok) {
    clearTokens();
    throw new Error('Session expired');
  }

  const data = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data.access_token;
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const { access } = getTokens();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (access) {
    headers['Authorization'] = `Bearer ${access}`;
  }

  const config = { ...options, headers };

  if (config.body && typeof config.body !== 'string' && !(config.body instanceof URLSearchParams) && !(config.body instanceof FormData)) {
    config.body = JSON.stringify(config.body);
  }

  let response;
  try {
    response = await fetch(url, config);
  } catch (networkError) {
    throw new Error('Unable to connect to backend server. Ensure it is running.');
  }

  if (response.status === 401 && access) {
    if (!isRefreshing) {
      isRefreshing = true;
      try {
        const newToken = await refreshAccessToken();
        isRefreshing = false;
        refreshQueue.forEach(cb => cb(newToken));
        refreshQueue = [];
        headers['Authorization'] = `Bearer ${newToken}`;
        config.headers = headers;
        response = await fetch(url, config);
      } catch {
        isRefreshing = false;
        refreshQueue = [];
        clearTokens();
        window.dispatchEvent(new CustomEvent('auth:logout'));
        throw new Error('Session expired. Please log in again.');
      }
    } else {
      const newToken = await new Promise(resolve => {
        refreshQueue.push(resolve);
      });
      headers['Authorization'] = `Bearer ${newToken}`;
      config.headers = headers;
      response = await fetch(url, config);
    }
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Request failed (${response.status})`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  // Auth
  login: (username, password) =>
    request('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password }),
    }).then(data => {
      setTokens(data.access_token, data.refresh_token);
      return data;
    }),

  register: (username, password) =>
    request('/auth/register', {
      method: 'POST',
      body: { username, password },
    }),

  getMe: () => request('/auth/me'),

  logout: () => {
    clearTokens();
    window.dispatchEvent(new CustomEvent('auth:logout'));
  },

  refreshToken: () => refreshAccessToken(),

  // Account
  getAccount: () => request('/account'),
  updateAccount: (data) => request('/account', { method: 'PUT', body: data }),

  // Missions
  getMissions: () => request('/missions'),
  createMission: (data) => request('/missions', { method: 'POST', body: data }),
  updateMission: (id, data) => request(`/missions/${id}`, { method: 'PUT', body: data }),
  deleteMission: (id) => request(`/missions/${id}`, { method: 'DELETE' }),

  // Habits
  getHabits: () => request('/habits'),
  createHabit: (data) => request('/habits', { method: 'POST', body: data }),
  updateHabit: (id, data) => request(`/habits/${id}`, { method: 'PUT', body: data }),
  deleteHabit: (id) => request(`/habits/${id}`, { method: 'DELETE' }),
  checkInHabit: (id) => request(`/habits/${id}/check-in`, { method: 'POST' }),

  // Logs
  getLogs: (limit = 50, start_date = '', end_date = '') => {
    let url = `/logs?limit=${limit}`;
    if (start_date) url += `&start_date=${encodeURIComponent(start_date)}`;
    if (end_date) url += `&end_date=${encodeURIComponent(end_date)}`;
    return request(url);
  },
  createLog: (data) => request('/logs', { method: 'POST', body: data }),

  // Focus
  startFocusSession: (data) => request('/focus/sessions', { method: 'POST', body: data }),
  endFocusSession: (id, data) => request(`/focus/sessions/${id}`, { method: 'PUT', body: data }),
  getFocusSessions: (limit = 20) => request(`/focus/sessions?limit=${limit}`),

  // Focus Stats
  getFocusStats: (period = 'week') => request(`/stats/focus?period=${encodeURIComponent(period)}`),
  getFocusTrend: (granularity = 'day') =>
    request(`/stats/focus/trend?granularity=${encodeURIComponent(granularity)}`),
  getDayStats: (day) => request(`/stats/day?day=${encodeURIComponent(day)}`),
  getFocusSessionLog: (limit = 20, offset = 0) =>
    request(`/stats/focus/sessions?limit=${limit}&offset=${offset}`),

  // Account
  changePassword: (current_password, new_password) =>
    request('/account/password', { method: 'PUT', body: { current_password, new_password } }),
  resetPoints: () => request('/account/reset-points', { method: 'POST' }),

  // Calendar Events
  getCalendarEvents: () => request('/calendar/events'),
  createCalendarEvent: (data) => request('/calendar/events', { method: 'POST', body: data }),
  updateCalendarEvent: (id, data) => request(`/calendar/events/${id}`, { method: 'PUT', body: data }),
  deleteCalendarEvent: (id) => request(`/calendar/events/${id}`, { method: 'DELETE' }),

  // Notes
  getNotes: (search = '', sort = '') => {
    let url = '/notes';
    const params = [];
    if (search) params.push(`search=${encodeURIComponent(search)}`);
    if (sort) params.push(`sort=${encodeURIComponent(sort)}`);
    if (params.length) url += `?${params.join('&')}`;
    return request(url);
  },
  createNote: (data) => request('/notes', { method: 'POST', body: data }),
  updateNote: (id, data) => request(`/notes/${id}`, { method: 'PUT', body: data }),
  deleteNote: (id) => request(`/notes/${id}`, { method: 'DELETE' }),

  // Countdowns
  getCountdowns: () => request('/countdowns'),
  createCountdown: (data) => request('/countdowns', { method: 'POST', body: data }),
  deleteCountdown: (id) => request(`/countdowns/${id}`, { method: 'DELETE' }),

  // Telegram linking
  generateTelegramCode: () => request('/account/telegram-link/generate-code', { method: 'POST' }),
  getTelegramLinkStatus: () => request('/account/telegram-link/status'),
  unlinkTelegram: () => request('/account/telegram-link', { method: 'DELETE' }),

  // Alfred in-app chat (same brain as the Telegram bot, JWT user)
  sendAlfredMessage: (message, session_id) => request('/alfred/chat', { method: 'POST', body: { message, session_id } }),

  // Alfred sessions
  getAlfredSessions: () => request('/alfred/sessions'),
  createAlfredSession: (title) => request('/alfred/sessions', { method: 'POST', body: { title } }),
  getAlfredSessionMessages: (id) => request(`/alfred/sessions/${id}/messages`),

  // Alfred provider (BYOK — key never returned by any of these)
  getAlfredProvider: () => request('/alfred/provider'),
  testAlfredProvider: (provider, model_name, api_key) => request('/alfred/provider/test', { method: 'POST', body: { provider, model_name, api_key } }),
  saveAlfredProvider: (provider, model_name, api_key) => request('/alfred/provider', { method: 'POST', body: { provider, model_name, api_key } }),
  deleteAlfredProvider: () => request('/alfred/provider', { method: 'DELETE' }),
};