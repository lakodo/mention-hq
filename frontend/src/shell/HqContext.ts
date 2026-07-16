import { createContext, useContext } from 'react';

export interface HqContextValue {
  appName: string;
  query: string;
  setQuery: (q: string) => void;
  autoSync: boolean;
  toggleAutoSync: () => void;
  lastSync: string | null;
  syncing: boolean;
  runSync: () => void;
  taskCount: number;
  itemCount: number;
}

export const HqContext = createContext<HqContextValue | null>(null);

export function useHq(): HqContextValue {
  const ctx = useContext(HqContext);
  if (!ctx) throw new Error('useHq must be used inside <AppLayout>');
  return ctx;
}
