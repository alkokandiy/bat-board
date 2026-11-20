/**
 * Minor units in, text out. The only place in the browser that turns a stored
 * integer into something a person reads.
 *
 * Amounts are integers of minor units everywhere else — 1 018 500,00 UZS is
 * 101850000 — so no arithmetic in this app ever happens in floating point,
 * where 0.10 cannot be represented and a ledger quietly drifts.
 */

// Minor digits per currency. Two almost everywhere; these are the exceptions,
// and getting one wrong puts every amount out by a factor of a hundred.
const EXPONENTS = {
  JPY: 0, KRW: 0, VND: 0, CLP: 0, ISK: 0, BIF: 0, DJF: 0, GNF: 0,
  KMF: 0, PYG: 0, RWF: 0, UGX: 0, VUV: 0, XAF: 0, XOF: 0, XPF: 0,
  BHD: 3, IQD: 3, JOD: 3, KWD: 3, LYD: 3, OMR: 3, TND: 3,
};

export function exponent(currency) {
  return EXPONENTS[String(currency || '').toUpperCase()] ?? 2;
}

/**
 * "1 018 500,00" — thin spaces between thousands, comma before the minor part,
 * which is how the numbers are already read in the app this replaces.
 */
export function formatMinor(minor, currency, { sign = false } = {}) {
  const exp = exponent(currency);
  const n = Number(minor || 0);
  const negative = n < 0;
  const abs = Math.abs(n);

  const divisor = 10 ** exp;
  const major = Math.floor(abs / divisor);
  const rest = abs % divisor;

  const grouped = String(major).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  const text = exp > 0 ? `${grouped},${String(rest).padStart(exp, '0')}` : grouped;

  const prefix = negative ? '-' : (sign ? '+' : '');
  return `${prefix}${text}`;
}

/** The same with its currency in front: "UZS 1 018 500,00". */
export function formatMoney(minor, currency, options) {
  const amount = formatMinor(minor, currency, options);
  return currency ? `${currency} ${amount}` : amount;
}

/**
 * What a person typed back into minor units.
 *
 * Accepts "45000", "45 000", "45,5", "45.5" — a comma and a full stop both
 * mean the decimal separator here, since the keyboard and the locale disagree
 * about which one is which and guessing wrong by 100x is not recoverable.
 * Returns null when there is no number in it, so a caller can refuse rather
 * than silently book zero.
 */
export function parseToMinor(input, currency) {
  const raw = String(input ?? '').trim().replace(/[\s  ]/g, '');
  if (!raw) return null;

  const normalised = raw.replace(',', '.');
  if (!/^\d*\.?\d*$/.test(normalised) || normalised === '.') return null;

  const [major = '0', minorPart = ''] = normalised.split('.');
  const exp = exponent(currency);
  if (exp === 0) {
    // Rounding, not truncation: "45.7" in a currency with no minor unit is 46,
    // and silently dropping it loses money on every entry.
    return Math.round(Number(normalised));
  }
  const padded = (minorPart + '0'.repeat(exp)).slice(0, exp);
  const value = Number(major || '0') * 10 ** exp + Number(padded || '0');
  return Number.isFinite(value) ? value : null;
}

/** Local YYYY-MM-DD. Never toISOString, which shifts the day in half the world. */
export function toDateString(date) {
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * The window of a budget month that starts on `startDay`.
 *
 * With startDay 25, "November" runs 25 Oct → 24 Nov: the month a salary
 * actually governs, rather than the one the calendar prints.
 */
export function monthWindow(year, monthIndex, startDay = 1) {
  if (startDay <= 1) {
    return {
      start: toDateString(new Date(year, monthIndex, 1)),
      end: toDateString(new Date(year, monthIndex + 1, 0)),
    };
  }
  return {
    start: toDateString(new Date(year, monthIndex - 1, startDay)),
    end: toDateString(new Date(year, monthIndex, startDay - 1)),
  };
}
