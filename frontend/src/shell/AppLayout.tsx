import { Box } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from '../components/Header';
import { CLOCK_TICK_MS, DEFAULT_APP_NAME } from '../constants';
import { errorMessage, isSyncAlreadyRunning } from '../api/client';
import { useSettings, useSync, useSyncStatus, useTasks, useUpdateSettings } from '../api/hooks';
import { filterTasks } from '../lib/search';
import { countItems } from '../lib/tasks';
import { CommandPalette } from './CommandPalette';
import { HqContext, type HqContextValue } from './HqContext';
import { ShortcutsHelp } from './ShortcutsHelp';
import { useGlobalShortcuts } from './useGlobalShortcuts';
import type { SyncResult } from '../types';

function syncMessage(result: SyncResult): string {
  const parts = [`${result.sources_synced.length} sources`];
  if (result.items_added) parts.push(`${result.items_added} new`);
  if (result.proposals) parts.push(`${result.proposals} proposed`);
  return parts.join(' · ');
}

export function AppLayout() {
  const [query, setQuery] = useState('');

  const { data: tasks } = useTasks();
  const { data: settings } = useSettings();
  const { data: syncLog } = useSyncStatus();
  const updateSettings = useUpdateSettings();
  const sync = useSync();

  // "Last synced" comes from the server's sync log, so it survives a reload — rather than local
  // state that reset to "Never synced" on every refresh even after syncs had run.
  const lastSync = syncLog?.[0]?.finished_at ?? syncLog?.[0]?.started_at ?? null;
  // Persisted server-side, so the on/off survives a reload. The backend runs the timer now, so
  // auto-sync fires whether or not a tab is open.
  const autoSync = settings?.auto_sync ?? false;

  // Held in a ref so the auto-sync interval survives the mutation object changing identity.
  const syncRef = useRef(sync);
  syncRef.current = sync;

  const runSync = useCallback(() => {
    if (syncRef.current.isPending) return;

    syncRef.current.mutate(undefined, {
      onSuccess: (result) => {
        notifications.show({
          title: 'Sync complete',
          message: syncMessage(result),
          color: result.errors.length ? 'orange' : 'teal',
        });
      },
      onError: (error) => {
        if (isSyncAlreadyRunning(error)) {
          notifications.show({
            title: 'Sync already running',
            message: 'A sync is in flight. Its results will land shortly.',
            color: 'gray',
          });
          return;
        }
        notifications.show({ title: 'Sync failed', message: errorMessage(error), color: 'red' });
      },
    });
  }, []);

  // `/` focuses whatever search box the current screen has — the header search on the
  // board/catch-up/timeline, the task-list search on Tasks. Focus the first visible one.
  const focusSearch = useCallback(() => {
    const candidates = Array.from(document.querySelectorAll<HTMLInputElement>('input')).filter(
      (el) =>
        /search/i.test(el.getAttribute('aria-label') ?? '') || /search/i.test(el.placeholder ?? ''),
    );
    // Prefer a laid-out (visible) one; fall back to the first match where layout is
    // unavailable (only one search renders per screen anyway).
    const search = candidates.find((el) => el.offsetParent !== null) ?? candidates[0];
    search?.focus();
    search?.select();
  }, []);

  const [helpOpened, helpHandlers] = useDisclosure(false);
  useGlobalShortcuts({ onFocusSearch: focusSearch, onShowHelp: helpHandlers.open });

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
      runSync,
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
      <CommandPalette onShowHelp={helpHandlers.open} />
      <ShortcutsHelp opened={helpOpened} onClose={helpHandlers.close} />
    </HqContext.Provider>
  );
}
