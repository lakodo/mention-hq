import { Box } from '@mantine/core';
import { useHotkeys } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from '../components/Header';
import { AUTO_SYNC_INTERVAL_MS, CLOCK_TICK_MS, DEFAULT_APP_NAME } from '../constants';
import { errorMessage, isSyncAlreadyRunning } from '../api/client';
import { useSettings, useSync, useTasks, useUpdateSettings } from '../api/hooks';
import { filterTasks } from '../lib/search';
import { countItems } from '../lib/tasks';
import { HqContext, type HqContextValue } from './HqContext';
import type { SyncResult } from '../types';

function syncMessage(result: SyncResult): string {
  const parts = [`${result.sources_synced.length} sources`];
  if (result.items_added) parts.push(`${result.items_added} new`);
  if (result.proposals) parts.push(`${result.proposals} proposed`);
  return parts.join(' · ');
}

export function AppLayout() {
  const [query, setQuery] = useState('');
  const [lastSync, setLastSync] = useState<string | null>(null);

  const { data: tasks } = useTasks();
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();
  const sync = useSync();

  // Persisted like the app's name, so the timer's on/off survives a reload.
  const autoSync = settings?.auto_sync ?? false;

  // Held in a ref so the auto-sync interval survives the mutation object changing identity.
  const syncRef = useRef(sync);
  syncRef.current = sync;

  const runSync = useCallback((auto = false) => {
    if (syncRef.current.isPending) return;

    syncRef.current.mutate(undefined, {
      onSuccess: (result) => {
        setLastSync(new Date().toISOString());
        notifications.show({
          title: auto ? 'Auto-sync complete' : 'Sync complete',
          message: syncMessage(result),
          color: result.errors.length ? 'orange' : 'teal',
        });
      },
      onError: (error) => {
        if (isSyncAlreadyRunning(error)) {
          // The run already under way refreshes the same data, so there is nothing to report.
          if (!auto) {
            notifications.show({
              title: 'Sync already running',
              message: 'A sync is in flight. Its results will land shortly.',
              color: 'gray',
            });
          }
          return;
        }
        notifications.show({ title: 'Sync failed', message: errorMessage(error), color: 'red' });
      },
    });
  }, []);

  useEffect(() => {
    if (!autoSync) return;
    const id = setInterval(() => runSync(true), AUTO_SYNC_INTERVAL_MS);
    return () => clearInterval(id);
  }, [autoSync, runSync]);

  // ⌘/Ctrl+K jumps to whatever search box the current screen has — the header search on the
  // board/catch-up/timeline, the task-list search on Tasks. Focus the first visible one.
  useHotkeys(
    [
      [
        'mod+K',
        () => {
          const candidates = Array.from(
            document.querySelectorAll<HTMLInputElement>('input'),
          ).filter(
            (el) =>
              /search/i.test(el.getAttribute('aria-label') ?? '') ||
              /search/i.test(el.placeholder ?? ''),
          );
          // Prefer a laid-out (visible) one; fall back to the first match where layout is
          // unavailable (only one search renders per screen anyway).
          const search = candidates.find((el) => el.offsetParent !== null) ?? candidates[0];
          search?.focus();
          search?.select();
        },
      ],
    ],
    [],
  );

  // Keeps the "Synced Xm ago" label honest without refetching anything.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), CLOCK_TICK_MS);
    return () => clearInterval(id);
  }, []);

  const visible = useMemo(() => filterTasks(tasks ?? [], query), [tasks, query]);

  const appName = settings?.app_name ?? DEFAULT_APP_NAME;

  useEffect(() => {
    document.title = appName;
  }, [appName]);

  const value: HqContextValue = useMemo(
    () => ({
      appName,
      query,
      setQuery,
      autoSync,
      toggleAutoSync: () => updateSettings.mutate({ auto_sync: !autoSync }),
      lastSync,
      syncing: sync.isPending,
      runSync: () => runSync(false),
      taskCount: visible.length,
      itemCount: countItems(visible),
    }),
    [appName, query, autoSync, updateSettings, lastSync, sync.isPending, runSync, visible],
  );

  return (
    <HqContext.Provider value={value}>
      <Box
        style={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: 'var(--mantine-color-gray-0)',
        }}
      >
        <Header />
        <Outlet />
      </Box>
    </HqContext.Provider>
  );
}
