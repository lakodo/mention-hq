import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { NAV_TARGETS, isTypingTarget } from '../lib/keyboard';

interface GlobalShortcutHandlers {
  onFocusSearch: () => void;
  onShowHelp: () => void;
}

// How long a `g` prefix waits for its second key before giving up.
const G_PREFIX_MS = 1200;

/**
 * The app-wide bare-key shortcuts: `g`-then-letter and `1`–`7` to jump to a view, `/` to focus
 * search, `?` for the shortcuts overlay. All are dormant while typing and never touch modifier
 * combos, so the browser's own Cmd/Ctrl shortcuts (and the palette's Cmd/Ctrl+K) are left alone.
 */
export function useGlobalShortcuts({ onFocusSearch, onShowHelp }: GlobalShortcutHandlers) {
  const navigate = useNavigate();

  const pendingG = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const clearG = () => {
      pendingG.current = false;
      if (timer.current) clearTimeout(timer.current);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      // Modifier combos belong to the browser, the OS, or the palette — never claim them here.
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;

      if (pendingG.current) {
        const target = NAV_TARGETS.find((t) => t.letter === event.key.toLowerCase());
        clearG();
        if (target) {
          event.preventDefault();
          navigate(target.path);
        }
        return;
      }

      if (event.key === 'g') {
        pendingG.current = true;
        timer.current = setTimeout(clearG, G_PREFIX_MS);
        return;
      }

      const digit = Number(event.key);
      if (Number.isInteger(digit) && digit >= 1) {
        const target = NAV_TARGETS.find((t) => t.number === digit);
        if (target) {
          event.preventDefault();
          navigate(target.path);
        }
        return;
      }

      if (event.key === '/') {
        event.preventDefault();
        onFocusSearch();
        return;
      }
      if (event.key === '?') {
        event.preventDefault();
        onShowHelp();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      clearG();
    };
  }, [navigate, onFocusSearch, onShowHelp]);
}
