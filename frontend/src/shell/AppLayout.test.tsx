import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';

const SYNC = 'http://localhost:8000/sync';

describe('AppLayout sync', () => {
  it('reports a completed sync', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: /Sync/ }));

    expect(await screen.findByText('Sync complete')).toBeInTheDocument();
    expect(await screen.findByText(/Synced just now/)).toBeInTheDocument();
  });

  it('treats a 409 as "already running" rather than a failure', async () => {
    server.use(
      http.post(SYNC, () =>
        HttpResponse.json({ detail: 'A sync is already running' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: /Sync/ }));

    expect(await screen.findByText('Sync already running')).toBeInTheDocument();
    expect(screen.queryByText('Sync failed')).not.toBeInTheDocument();
  });

  it('still surfaces a real sync failure', async () => {
    server.use(
      http.post(SYNC, () => HttpResponse.json({ detail: 'Everything broke' }, { status: 500 })),
    );
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: /Sync/ }));

    expect(await screen.findByText('Sync failed')).toBeInTheDocument();
    expect(screen.getByText('Everything broke')).toBeInTheDocument();
  });

  it('titles the header from the app settings', async () => {
    server.use(
      http.get('http://localhost:8000/admin/settings', () =>
        HttpResponse.json({
          app_name: 'Mission Control',
          secret_backend: 'keyring',
          secret_backend_is_keychain: true,
        }),
      ),
    );
    renderApp('/');

    expect(await screen.findByText('Mission Control')).toBeInTheDocument();
  });

  it('counts the items and tasks in view', async () => {
    renderApp('/');
    expect(await screen.findByText('6 items across 3 tasks')).toBeInTheDocument();
  });

  it('recounts as the search narrows the board', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await screen.findByText('6 items across 3 tasks');
    await user.type(screen.getByLabelText('Search'), 'bucket:auth');

    await waitFor(() => expect(screen.getByText('2 items across 1 task')).toBeInTheDocument());
  });
});
