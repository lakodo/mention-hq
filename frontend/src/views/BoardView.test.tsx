import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';
import { db } from '../test/handlers';
import { PAYMENTS_TASK_ID } from '../test/fixtures';

describe('BoardView', () => {
  it('renders one column per bucket with its task count', async () => {
    renderApp('/');

    const payments = await screen.findByTestId('bucket-column-Payments');
    expect(within(payments).getByText('Payments')).toBeInTheDocument();
    expect(within(payments).getByText('2')).toBeInTheDocument();

    const auth = screen.getByTestId('bucket-column-Auth');
    expect(within(auth).getByText('1')).toBeInTheDocument();
  });

  it('places each task card in its own bucket column', async () => {
    renderApp('/');

    const payments = await screen.findByTestId('bucket-column-Payments');
    expect(
      within(payments).getByText('Stripe webhook handling for invoice payments'),
    ).toBeInTheDocument();
    expect(
      within(payments).getByText('Refund flow throws on partial captures'),
    ).toBeInTheDocument();

    const auth = screen.getByTestId('bucket-column-Auth');
    expect(within(auth).getByText('Refresh token rotation on scope change')).toBeInTheDocument();
  });

  it('shows the item count on a card', async () => {
    renderApp('/');
    expect(await screen.findByText('3 items')).toBeInTheDocument();
    expect(screen.getByText('1 item')).toBeInTheDocument();
  });

  it('lets the user make their first bucket on a fresh install', async () => {
    server.use(
      http.get('http://localhost:8000/api/buckets', () => HttpResponse.json([])),
      http.get('http://localhost:8000/api/tasks', () => HttpResponse.json([])),
    );
    renderApp('/');

    expect(await screen.findByText('No buckets yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add a bucket/ })).toBeInTheDocument();
  });

  it('creates a bucket from the board', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByTestId('bucket-column-Payments');

    await user.click(screen.getByRole('button', { name: /New bucket/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'Infra');
    await user.type(within(dialog).getByLabelText('Keywords'), 'deploy, ci');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(db.buckets.some((b) => b.name === 'Infra')).toBe(true));
  });

  it('still shows tasks under Uncategorized when no bucket claims them', async () => {
    server.use(http.get('http://localhost:8000/api/buckets', () => HttpResponse.json([])));
    renderApp('/');

    // Nothing may disappear from the board just because its bucket is gone.
    const uncategorized = await screen.findByTestId('bucket-column-Uncategorized');
    expect(
      within(uncategorized).getByText('Stripe webhook handling for invoice payments'),
    ).toBeInTheDocument();
    expect(screen.queryByText('No buckets yet')).not.toBeInTheDocument();
  });

  it('filters the board through the header search', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await screen.findByTestId('bucket-column-Payments');
    await user.type(screen.getByLabelText('Search'), 'bucket:auth');

    await waitFor(() =>
      expect(
        screen.queryByText('Stripe webhook handling for invoice payments'),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Refresh token rotation on scope change')).toBeInTheDocument();
  });

  it('marks a task read from its card', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const payments = await screen.findByTestId('bucket-column-Payments');
    const [toggle] = within(payments).getAllByLabelText('Toggle read/unread');
    await user.click(toggle);

    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(false),
    );
  });

  it('navigates to the task detail on card click', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByText('Stripe webhook handling for invoice payments'));

    // The detail view's sidebar search only exists on that route.
    expect(await screen.findByLabelText('Search tasks')).toBeInTheDocument();
  });
});
