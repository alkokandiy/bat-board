/**
 * Date arithmetic shared by the calendar's four views.
 *
 * Kept out of the components because month, week, day and agenda all need
 * the same answers and three copies of "which Monday is this" is three
 * chances to disagree about it.
 */

export const HOURS = Array.from({ length: 24 }, (_, i) => i);

export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Monday-first, like the missions filter and the habit weekdays. */
export function startOfWeek(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}

export function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

export function weekOf(date) {
  const start = startOfWeek(date);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

export function sameDay(a, b) {
  return !!a && !!b
    && a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export function isToday(date) {
  return sameDay(date, new Date());
}

export function hhmm(date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

/** The hour row an event belongs to on a given day. */
export function hourOn(event, day) {
  const start = new Date(event.start_time);
  // An event that began before this day shows at the top of it, not at
  // whatever hour it started on some earlier date.
  return sameDay(start, day) ? start.getHours() : 0;
}

/** Events grouped by the hour they start, each hour in time order. */
export function byHour(events, day) {
  const map = {};
  events.forEach((e) => {
    const h = hourOn(e, day);
    (map[h] = map[h] || []).push(e);
  });
  Object.values(map).forEach((list) =>
    list.sort((a, b) => new Date(a.start_time) - new Date(b.start_time)));
  return map;
}

export function timeRange(event) {
  const start = new Date(event.start_time);
  const end = event.end_time ? new Date(event.end_time) : null;
  return `${hhmm(start)}${end ? `–${hhmm(end)}` : ''}`;
}
