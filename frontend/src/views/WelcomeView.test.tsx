import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';

const CATCHUP = 'http://localhost:8000/api/catchup';

describe('WelcomeView', () => {
  it('lists the top-priority tasks, each linking to its detail', async () => {
    renderApp('/welcome');

    const cards = await screen.findAllByTestId('welcome-task');
    expect(cards.length).toBeGreaterThan(0);

    const link = await screen.findByRole('link', { name: /Stripe webhook handling/ });
    expect(link).toHaveAttribute('href', expect.stringContaining('/task/'));
  });

  it('shows a catch-up CTA with the count when the inbox has items', async () => {
    renderApp('/welcome');

    expect(await screen.findByText('2 items to catch up on')).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: /Catch up/ });

    const user = userEvent.setup();
    await user.click(cta);

    // It takes you to the catch-up screen.
    await waitFor(() => expect(screen.getByText(/to triage/)).toBeInTheDocument());
  });

  it('celebrates instead when the inbox is empty', async () => {
    server.use(http.get(CATCHUP, () => HttpResponse.json([])));
    renderApp('/welcome');

    expect(await screen.findByText(/all caught up/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Catch up/ })).not.toBeInTheDocument();
  });

  it('is where the header title takes you', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByRole('link', { name: 'Personal HQ' }));

    expect(await screen.findByText('Top priorities')).toBeInTheDocument();
  });
});
