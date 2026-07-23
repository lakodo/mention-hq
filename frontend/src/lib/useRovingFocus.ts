import { useCallback, useRef } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

export type RovingOrientation = 'horizontal' | 'vertical' | 'grid';

interface RovingOptions {
  orientation?: RovingOrientation;
  /** Wrap around at the ends. Off by default — clamping reads more predictably in a list. */
  loop?: boolean;
  /** Fired on Enter/Space when a roving item itself is focused. Omit to leave keys to the item. */
  onActivate?: (el: HTMLElement) => void;
  itemSelector?: string;
}

/**
 * Roving-tabindex arrow navigation over a set of items, following the WAI-ARIA pattern: exactly
 * one item is Tab-reachable at a time and arrow keys move focus between them. Keys are handled on
 * the container and only when a roving item is itself the event target, so they never hijack page
 * scroll, and a nested control (an open Select, a text field) keeps its own arrow behaviour.
 *
 * Items opt in with `data-roving-item`. For `grid` (a 2-D board) each item also carries
 * `data-col`/`data-row`; left/right change column keeping the row where it can, up/down move
 * within a column. Attach the returned `ref` and `onKeyDown` to the container element.
 *
 * `ref` is a callback ref so the tabindex is set the moment the list mounts — which, on a view
 * that renders a loader first, happens after the hook's own render.
 */
export function useRovingFocus<T extends HTMLElement = HTMLDivElement>(
  options: RovingOptions = {},
) {
  const {
    orientation = 'vertical',
    loop = false,
    onActivate,
    itemSelector = '[data-roving-item]',
  } = options;
  const nodeRef = useRef<T | null>(null);
  const observerRef = useRef<MutationObserver | null>(null);

  const items = useCallback(
    () => Array.from(nodeRef.current?.querySelectorAll<HTMLElement>(itemSelector) ?? []),
    [itemSelector],
  );

  // Keep exactly one item tabbable so Tab lands in the list once, then arrows take over.
  const syncTabIndex = useCallback(
    (active?: HTMLElement) => {
      const els = items();
      if (els.length === 0) return;
      const current = active ?? els.find((el) => el.tabIndex === 0) ?? els[0];
      for (const el of els) el.tabIndex = el === current ? 0 : -1;
    },
    [items],
  );

  // Establish (and re-establish, as items load or reorder) the single tabbable item.
  const ref = useCallback(
    (node: T | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      nodeRef.current = node;
      if (!node) return;
      syncTabIndex();
      const observer = new MutationObserver(() => syncTabIndex());
      observer.observe(node, { childList: true, subtree: true });
      observerRef.current = observer;
    },
    [syncTabIndex],
  );

  const focusItem = useCallback(
    (el: HTMLElement | undefined) => {
      if (!el) return;
      syncTabIndex(el);
      el.focus();
    },
    [syncTabIndex],
  );

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent) => {
      const target = event.target as HTMLElement;
      const els = items();
      const idx = els.indexOf(target);
      if (idx === -1) return; // focus is on a nested control or nothing — leave the keys alone.

      const key = event.key;

      if ((key === 'Enter' || key === ' ') && onActivate) {
        event.preventDefault();
        onActivate(target);
        return;
      }

      const step = (next: number) => {
        event.preventDefault();
        const clamped = loop
          ? (next + els.length) % els.length
          : Math.max(0, Math.min(els.length - 1, next));
        focusItem(els[clamped]);
      };

      if (key === 'Home') return step(0);
      if (key === 'End') return step(els.length - 1);

      if (orientation === 'grid') {
        const col = Number(target.dataset.col);
        const inColumn = (c: number) =>
          els
            .filter((el) => Number(el.dataset.col) === c)
            .sort((a, b) => Number(a.dataset.row) - Number(b.dataset.row));
        const columns = [...new Set(els.map((el) => Number(el.dataset.col)))].sort((a, b) => a - b);
        const column = inColumn(col);
        const rowPos = column.indexOf(target);

        if (key === 'ArrowUp' || key === 'k') {
          event.preventDefault();
          return focusItem(column[Math.max(0, rowPos - 1)]);
        }
        if (key === 'ArrowDown' || key === 'j') {
          event.preventDefault();
          return focusItem(column[Math.min(column.length - 1, rowPos + 1)]);
        }
        if (key === 'ArrowLeft' || key === 'ArrowRight') {
          const colPos = columns.indexOf(col);
          const nextCol =
            columns[
              key === 'ArrowLeft'
                ? Math.max(0, colPos - 1)
                : Math.min(columns.length - 1, colPos + 1)
            ];
          const next = inColumn(nextCol);
          if (next.length === 0) return;
          event.preventDefault();
          return focusItem(next[Math.min(rowPos, next.length - 1)]);
        }
        return;
      }

      const forward = orientation === 'horizontal' ? 'ArrowRight' : 'ArrowDown';
      const backward = orientation === 'horizontal' ? 'ArrowLeft' : 'ArrowUp';
      const vim = orientation === 'vertical';
      if (key === forward || (vim && key === 'j')) return step(idx + 1);
      if (key === backward || (vim && key === 'k')) return step(idx - 1);
    },
    [items, onActivate, orientation, loop, focusItem],
  );

  return { ref, onKeyDown };
}
