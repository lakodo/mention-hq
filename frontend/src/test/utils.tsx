import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';

export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface ProvidersProps {
  children: ReactNode;
  route?: string;
  queryClient?: QueryClient;
}

export function Providers({ children, route = '/', queryClient }: ProvidersProps) {
  const client = queryClient ?? makeTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <MantineProvider>
        <ModalsProvider>
          <Notifications />
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </ModalsProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

/** Render the whole app (layout + routes) at a given route. */
export function renderApp(route = '/', queryClient?: QueryClient): RenderResult {
  const client = queryClient ?? makeTestQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <ModalsProvider>
          <Notifications />
          <MemoryRouter initialEntries={[route]}>
            <AppRoutes />
          </MemoryRouter>
        </ModalsProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}
