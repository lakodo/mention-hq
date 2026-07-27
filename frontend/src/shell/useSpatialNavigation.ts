import { useEffect } from 'react';
import { type Direction, collectFocusables, nearestInDirection } from '../lib/spatialNav';

const ARROWS: Record<string, Direction> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
};

const TEXT_INPUT_TYPES = new Set(['', 'text', 'search', 'email', 'url', 'tel', 'password']);

function isTextEditable(el: HTMLElement): el is HTMLInputElement | HTMLTextAreaElement {
  if (el.tagName === 'TEXTAREA') return true;
  return el.tagName === 'INPUT' && TEXT_INPUT_TYPES.has((el as HTMLInputElement).type);
}

/** The control owns its arrows: a combobox/select opens, a number spinner steps, a menu moves. */
function ownsArrows(el: HTMLElement): boolean {
  const role = el.getAttribute('role');
  if (role === 'combobox' || role === 'spinbutton') return true;
  if (el.getAttribute('aria-haspopup')) return true;
  return el.tagName === 'INPUT' && (el as HTMLInputElement).type === 'number';
}

/** An open dropdown (Select options, a Menu) is on screen and should receive the arrows itself. */
function popupOpen(): boolean {
  return collectFocusables(document).some(
    (el) => el.closest('[role="listbox"],[role="menu"]') !== null,
  );
}

/**
 * At a collapsed caret sitting against the given edge? Used to decide when an arrow should leave a
 * text field rather than move the caret. A selection (shift+arrow) never leaves.
 */
function atCaretEdge(el: HTMLInputElement | HTMLTextAreaElement, edge: 'start' | 'end'): boolean {
  const { selectionStart, selectionEnd, value } = el;
  if (selectionStart === null || selectionStart !== selectionEnd) return false;
  return edge === 'start' ? selectionStart === 0 : selectionStart === value.length;
}

function shouldLeaveInput(el: HTMLInputElement | HTMLTextAreaElement, dir: Direction): boolean {
  const singleLine = el.tagName === 'INPUT';
  switch (dir) {
    case 'left':
      return atCaretEdge(el, 'start');
    case 'right':
      return atCaretEdge(el, 'end');
    case 'up':
      return singleLine || atCaretEdge(el, 'start');
    case 'down':
      return singleLine || atCaretEdge(el, 'end');
  }
}

/**
 * App-wide spatial navigation: the arrow keys move focus to the nearest focusable control in that
 * direction. Bows out where an arrow already means something — inside a text field (except at the
 * caret boundary), on a combobox/number input, or while a dropdown/menu is open — and stays within
 * an open dialog rather than jumping to the page behind it.
 */
export function useSpatialNavigation() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const dir = ARROWS[event.key];
      if (!dir || event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;

      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || active === document.body) return;
      if (ownsArrows(active) || popupOpen()) return;
      if (isTextEditable(active) && !shouldLeaveInput(active, dir)) return;

      const scope = active.closest('[role="dialog"]') ?? document;
      const target = nearestInDirection(active, collectFocusables(scope), dir);
      if (target) {
        event.preventDefault();
        target.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);
}
