import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';

describe('LogView', () => {
  it('prints one summary line per sync run', async () => {
    renderApp('/log');

    const runs = await screen.findAllByTestId('log-run');
    expect(runs).toHaveLength(2);
    expect(
      screen.getByText(
        /Synced 2 sources · 5 items fetched · 2 tasks added · 1 tasks updated · 0.8s/,
      ),
    ).toBeInTheDocument();
  });

  it('breaks a run down per source', async () => {
    renderApp('/log');

    await screen.findAllByTestId('log-run');
    expect(screen.getByText(/github: 3 items/)).toBeInTheDocument();
    expect(screen.getByText(/slack: 2 items/)).toBeInTheDocument();
  });

  it('shows a failing run and its per-source error', async () => {
    renderApp('/log');

    await screen.findAllByTestId('log-run');
    expect(screen.getByText(/error: Linear rejected the token/)).toBeInTheDocument();
    expect(screen.getByText(/linear: error — HTTP 401/)).toBeInTheDocument();
  });

  it('puts the newest run last, just above the cursor', async () => {
    renderApp('/log');

    const runs = await screen.findAllByTestId('log-run');
    expect(runs[0]).toHaveTextContent('Linear rejected the token');
    expect(runs[1]).toHaveTextContent('2 tasks added');
  });

  it('says so when nothing has synced yet', async () => {
    server.use(http.get('http://localhost:8000/sync/status', () => HttpResponse.json([])));
    renderApp('/log');

    expect(await screen.findByText('No syncs yet.')).toBeInTheDocument();
  });
});
