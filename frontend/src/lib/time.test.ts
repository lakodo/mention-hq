import { describe, expect, it } from 'vitest';
import { ageMs, formatAgo, formatClock } from './time';

const now = new Date('2026-07-16T12:00:00.000Z').getTime();
const ago = (mins: number) => new Date(now - mins * 60_000).toISOString();

describe('formatAgo', () => {
  it('says "just now" under a minute', () => {
    expect(formatAgo(ago(0), now)).toBe('just now');
    expect(formatAgo(ago(0.4), now)).toBe('just now');
  });

  it('uses minutes under an hour', () => {
    expect(formatAgo(ago(5), now)).toBe('5m ago');
    expect(formatAgo(ago(59), now)).toBe('59m ago');
  });

  it('uses hours under a day', () => {
    expect(formatAgo(ago(60), now)).toBe('1h ago');
    expect(formatAgo(ago(300), now)).toBe('5h ago');
  });

  it('uses days beyond 24h', () => {
    expect(formatAgo(ago(1440), now)).toBe('1d ago');
    expect(formatAgo(ago(7200), now)).toBe('5d ago');
  });

  it('clamps future timestamps to "just now" rather than going negative', () => {
    expect(formatAgo(ago(-30), now)).toBe('just now');
  });

  it('handles null and malformed input', () => {
    expect(formatAgo(null, now)).toBe('never');
    expect(formatAgo(undefined, now)).toBe('never');
    expect(formatAgo('not-a-date', now)).toBe('unknown');
  });
});

describe('ageMs', () => {
  it('measures elapsed milliseconds', () => {
    expect(ageMs(ago(1), now)).toBe(60_000);
  });

  it('sorts missing timestamps last', () => {
    expect(ageMs(null, now)).toBe(Number.POSITIVE_INFINITY);
    expect(ageMs('garbage', now)).toBe(Number.POSITIVE_INFINITY);
  });
});

describe('formatClock', () => {
  it('renders an HH:MM:SS stamp', () => {
    expect(formatClock(ago(0))).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });

  it('degrades gracefully on bad input', () => {
    expect(formatClock(null)).toBe('--:--:--');
    expect(formatClock('nope')).toBe('--:--:--');
  });
});
