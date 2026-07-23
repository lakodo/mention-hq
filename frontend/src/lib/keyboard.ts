/**
 * One source of truth for keyboard navigation: the jump-to-view targets and the guard that
 * keeps global shortcuts dormant while the user is typing. Header tabs, the number/`g` shortcuts,
 * the command palette and the shortcuts overlay all read `NAV_TARGETS`, so they never drift.
 */

export interface NavTarget {
  label: string;
  path: string;
  /** The letter in the `g`-then-letter shortcut. */
  letter: string;
  /** 1-based position, for the number-key shortcut. */
  number: number;
}

// Order matches the Header's tab groups (primary then secondary), so `1` is the first tab shown.
export const NAV_TARGETS: NavTarget[] = [
  { label: 'Catch-up', path: '/catchup', letter: 'c', number: 1 },
  { label: 'Tasks', path: '/task', letter: 't', number: 2 },
  { label: 'Buckets', path: '/', letter: 'b', number: 3 },
  { label: 'Timeline', path: '/timeline', letter: 'l', number: 4 },
  { label: 'People', path: '/people', letter: 'p', number: 5 },
  { label: 'Log', path: '/log', letter: 'o', number: 6 },
  { label: 'Admin', path: '/admin', letter: 'a', number: 7 },
];

/**
 * True when the event is coming from somewhere the user is entering text, so a bare-key shortcut
 * would eat their keystroke. Global shortcuts bail on this; roving arrow-nav does not (it only
 * fires when a list item itself is focused).
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  return target.isContentEditable;
}
