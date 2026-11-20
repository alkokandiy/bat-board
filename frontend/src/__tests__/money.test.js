import { describe, it, expect } from 'vitest';
import { formatMinor, formatMoney, parseToMinor, exponent, monthWindow, toDateString } from '../utils/money';

describe('formatting minor units', () => {
  it('renders a real figure the way the ledger reads it', () => {
    expect(formatMinor(101850000, 'UZS')).toBe('1 018 500,00');
  });

  it('keeps the minor part even when it is zeros', () => {
    expect(formatMinor(600000, 'UZS')).toBe('6 000,00');
  });

  it('never loses a leading zero in the minor part', () => {
    // 1234 minor = 12.34, but 1204 minor is 12.04 and not 12.4
    expect(formatMinor(1204, 'USD')).toBe('12,04');
  });

  it('drops the minor part entirely for a currency that has none', () => {
    expect(formatMinor(5000, 'JPY')).toBe('5 000');
  });

  it('puts the sign in front, never inside the digits', () => {
    expect(formatMinor(-34200000, 'UZS')).toBe('-342 000,00');
  });

  it('marks a positive only when asked', () => {
    expect(formatMinor(100, 'USD')).toBe('1,00');
    expect(formatMinor(100, 'USD', { sign: true })).toBe('+1,00');
    // A negative is never given a plus by the sign option.
    expect(formatMinor(-100, 'USD', { sign: true })).toBe('-1,00');
  });

  it('prefixes the currency when there is one', () => {
    expect(formatMoney(101850000, 'UZS')).toBe('UZS 1 018 500,00');
    expect(formatMoney(100, null)).toBe('1,00');
  });
});

describe('currency exponents', () => {
  it('assumes two minor digits', () => {
    expect(exponent('UZS')).toBe(2);
    expect(exponent('USD')).toBe(2);
  });

  it('knows the currencies that are not two', () => {
    expect(exponent('JPY')).toBe(0);
    expect(exponent('KWD')).toBe(3);
  });

  it('does not care about case', () => {
    expect(exponent('jpy')).toBe(0);
  });
});

describe('parsing what someone typed', () => {
  it('reads a plain amount as major units', () => {
    expect(parseToMinor('45000', 'UZS')).toBe(4500000);
  });

  it('accepts a comma or a full stop as the decimal separator', () => {
    // The keyboard and the locale disagree about which is which, and guessing
    // wrong is a factor-of-a-hundred error nobody notices until it compounds.
    expect(parseToMinor('45,50', 'USD')).toBe(4550);
    expect(parseToMinor('45.50', 'USD')).toBe(4550);
  });

  it('pads a short minor part rather than misreading it', () => {
    // "45.5" is 45.50, which is 4550 minor — not 455.
    expect(parseToMinor('45.5', 'USD')).toBe(4550);
  });

  it('truncates beyond the currency precision instead of inventing digits', () => {
    expect(parseToMinor('1.239', 'USD')).toBe(123);
  });

  it('ignores the spaces a grouped number is typed with', () => {
    expect(parseToMinor('1 018 500', 'UZS')).toBe(101850000);
    expect(parseToMinor('1 018 500', 'UZS')).toBe(101850000);
  });

  it('rounds for a currency with no minor unit rather than dropping it', () => {
    expect(parseToMinor('45.7', 'JPY')).toBe(46);
  });

  it('returns null for anything that is not a number, never zero', () => {
    // Zero would book a real transaction for nothing; null lets the caller refuse.
    expect(parseToMinor('', 'UZS')).toBeNull();
    expect(parseToMinor('abc', 'UZS')).toBeNull();
    expect(parseToMinor('.', 'UZS')).toBeNull();
    expect(parseToMinor(null, 'UZS')).toBeNull();
  });
});

describe('the budget month', () => {
  it('is the calendar month when it starts on the 1st', () => {
    expect(monthWindow(2026, 10, 1)).toEqual({ start: '2026-11-01', end: '2026-11-30' });
  });

  it('runs from payday to the day before the next one', () => {
    // November, for someone paid on the 25th, is 25 Oct to 24 Nov.
    expect(monthWindow(2026, 10, 25)).toEqual({ start: '2026-10-25', end: '2026-11-24' });
  });

  it('crosses a year boundary correctly', () => {
    expect(monthWindow(2026, 0, 25)).toEqual({ start: '2025-12-25', end: '2026-01-24' });
  });
});

describe('date strings', () => {
  it('uses the local day, not UTC', () => {
    // toISOString() would hand back the previous day for anyone east of UTC
    // late in the evening, filing a transaction under the wrong date.
    const lateEvening = new Date(2026, 10, 20, 23, 30);
    expect(toDateString(lateEvening)).toBe('2026-11-20');
  });
});
