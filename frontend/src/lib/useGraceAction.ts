import { useCallback, useEffect, useRef, useState } from 'react';

const STEP_MS = 50;

interface GraceState {
  timer?: ReturnType<typeof setInterval>;
  elapsed: number;
  paused: boolean;
  commit?: () => void;
}

/**
 * A "commit after a grace window" action: `start(commit)` shows a progress that fills over
 * `durationMs`, then runs `commit`. While paused (the card is hovered) the fill holds, so nothing
 * commits and the item stays fully interactive — you can still click through to its source. The
 * action isn't run until the window elapses, so `cancel()` simply calls it off.
 */
export function useGraceAction(durationMs = 3500) {
  const [progress, setProgress] = useState(0);
  const [active, setActive] = useState(false);
  const state = useRef<GraceState>({ elapsed: 0, paused: false });

  const cancel = useCallback(() => {
    const s = state.current;
    if (s.timer) clearInterval(s.timer);
    s.timer = undefined;
    s.elapsed = 0;
    s.paused = false;
    s.commit = undefined;
    setActive(false);
    setProgress(0);
  }, []);

  const start = useCallback(
    (commit: () => void, startPaused = false) => {
      const s = state.current;
      if (s.timer) clearInterval(s.timer);
      s.elapsed = 0;
      s.paused = startPaused;
      s.commit = commit;
      setActive(true);
      setProgress(0);
      s.timer = setInterval(() => {
        const cur = state.current;
        if (cur.paused) return;
        cur.elapsed += STEP_MS;
        const pct = Math.min(100, (cur.elapsed / durationMs) * 100);
        setProgress(pct);
        if (pct >= 100) {
          const run = cur.commit;
          cancel();
          run?.();
        }
      }, STEP_MS);
    },
    [durationMs, cancel],
  );

  const pause = useCallback(() => {
    state.current.paused = true;
  }, []);
  const resume = useCallback(() => {
    state.current.paused = false;
  }, []);

  // On unmount, flush any still-pending action rather than dropping it — so navigating away (or
  // the list re-rendering the card out) mid-grace still commits what you asked for. `cancel` clears
  // `commit`, so an explicit cancel leaves nothing to flush.
  useEffect(() => {
    const s = state.current;
    return () => {
      if (s.timer) clearInterval(s.timer);
      const run = s.commit;
      s.timer = undefined;
      s.commit = undefined;
      run?.();
    };
  }, []);

  return { active, progress, start, pause, resume, cancel };
}
