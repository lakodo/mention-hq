import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { Route, Routes } from 'react-router-dom';
import { createQueryClient } from './queryClient';
import { AppLayout } from './shell/AppLayout';
import { AdminView } from './views/AdminView';
import { BoardView } from './views/BoardView';
import { CatchupView } from './views/CatchupView';
import { LogView } from './views/LogView';
import { TaskDetailView } from './views/TaskDetailView';
import { TimelineView } from './views/TimelineView';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<BoardView />} />
        <Route path="timeline" element={<TimelineView />} />
        <Route path="catchup" element={<CatchupView />} />
        <Route path="log" element={<LogView />} />
        <Route path="admin" element={<AdminView />} />
        <Route path="task/:id" element={<TaskDetailView />} />
        <Route path="task" element={<TaskDetailView />} />
      </Route>
    </Routes>
  );
}

interface AppProps {
  queryClient?: QueryClient;
}

export function App({ queryClient }: AppProps) {
  const client = queryClient ?? createQueryClient();

  return (
    <QueryClientProvider client={client}>
      <MantineProvider defaultColorScheme="light">
        <Notifications position="top-right" />
        <AppRoutes />
      </MantineProvider>
    </QueryClientProvider>
  );
}
