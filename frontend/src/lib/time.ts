/**
 * Relative-time labels matching the prototype's agoLabel/formatAgo:
 *   < 1m   -> "just now"
 *   < 60m  -> "{n}m ago"
 *   < 24h  -> "{n}h ago"
 *   else   -> "{n}d ago"
 */
export function formatAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'unknown';

  const mins = Math.max(0, Math.round((now - then) / 60_000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

/** Milliseconds since `iso`, used for chronological sorting. Invalid/missing sorts last. */
export function ageMs(iso: string | null | undefined, now: number = Date.now()): number {
  if (!iso) return Number.POSITIVE_INFINITY;
  const then = new Date(iso).getTime();
  return Number.isNaN(then) ? Number.POSITIVE_INFINITY : now - then;
}

/** "HH:MM:SS" clock stamp for terminal log lines. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '--:--:--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--:--';
  return d.toTimeString().slice(0, 8);
}
