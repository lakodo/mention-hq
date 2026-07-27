/**
 * Geometric spatial navigation: pick the focusable element nearest to the current one in a given
 * direction. Pure DOM/maths, no React — so the scoring is unit-testable with synthetic rects.
 */

export type Direction = 'up' | 'down' | 'left' | 'right';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]',
].join(',');

// How much an off-axis gap counts against a candidate. >1 keeps navigation honest: a control
// straight ahead beats one that's closer as-the-crow-flies but far to the side.
const OFF_AXIS_WEIGHT = 3;

/** Visible, focusable elements under `root` — including `tabindex="-1"` (the div participants). */
export function collectFocusables(root: ParentNode = document): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) =>
      el.getClientRects().length > 0 &&
      el.getAttribute('aria-hidden') !== 'true' &&
      !el.hasAttribute('hidden'),
  );
}

interface Point {
  primary: number; // distance along the direction of travel (must be > 0 to be a candidate)
  off: number; // absolute offset on the perpendicular axis
}

/** Where `to` sits relative to `from` when travelling in `dir`, using the nearest edges. */
function offset(from: DOMRect, to: DOMRect, dir: Direction): Point {
  const centerX = (r: DOMRect) => r.left + r.width / 2;
  const centerY = (r: DOMRect) => r.top + r.height / 2;
  switch (dir) {
    case 'up':
      return { primary: from.top - to.bottom, off: Math.abs(centerX(to) - centerX(from)) };
    case 'down':
      return { primary: to.top - from.bottom, off: Math.abs(centerX(to) - centerX(from)) };
    case 'left':
      return { primary: from.left - to.right, off: Math.abs(centerY(to) - centerY(from)) };
    case 'right':
      return { primary: to.left - from.right, off: Math.abs(centerY(to) - centerY(from)) };
  }
}

/**
 * The nearest candidate strictly in `dir` from `current`, or null if none. A candidate qualifies
 * when its near edge is ahead of the current element's far edge (`primary >= 0`, allowing a small
 * overlap so stacked cards still count), and wins on the lowest `primary + OFF_AXIS_WEIGHT * off`.
 */
export function nearestInDirection(
  current: HTMLElement,
  candidates: HTMLElement[],
  dir: Direction,
): HTMLElement | null {
  const from = current.getBoundingClientRect();
  let best: HTMLElement | null = null;
  let bestScore = Infinity;

  for (const candidate of candidates) {
    if (candidate === current) continue;
    const { primary, off } = offset(from, candidate.getBoundingClientRect(), dir);
    // A small negative tolerance lets a candidate that merely overlaps the current edge still count
    // as "ahead" (e.g. a card whose top is a pixel above the row's bottom).
    if (primary < -1) continue;
    const score = Math.max(primary, 0) + OFF_AXIS_WEIGHT * off;
    if (score < bestScore) {
      bestScore = score;
      best = candidate;
    }
  }
  return best;
}

/** Enter/Space activation for a div participant that isn't a native button. */
export function onActivateKeys(action: () => void) {
  return (event: { key: string; preventDefault: () => void }) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      action();
    }
  };
}
