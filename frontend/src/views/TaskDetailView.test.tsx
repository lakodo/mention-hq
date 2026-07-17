import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';
import { db } from '../test/handlers';
import { AUTH_TASK_ID, PAYMENTS_TASK_ID } from '../test/fixtures';

const detailRoute = (id: string) => `/task/${encodeURIComponent(id)}`;

/** The sidebar repeats every task title, so assertions scope to the main panel. */
const panel = () => screen.findByTestId('task-detail');

describe('TaskDetailView', () => {
  it('shows the selected task with its bucket, status and tags', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    expect(
      within(detail).getByText('Stripe webhook handling for invoice payments'),
    ).toBeInTheDocument();
    expect(within(detail).getByText('Payments')).toBeInTheDocument();
    expect(within(detail).getByText('Open')).toBeInTheDocument();
    expect(within(detail).getByText('backend')).toBeInTheDocument();
  });

  it('lands on /task with nothing selected rather than opening the first task', async () => {
    renderApp('/task');

    const detail = await panel();
    expect(within(detail).getByText('Select a task from the list.')).toBeInTheDocument();
    // The first task must not be auto-opened into the panel...
    expect(
      within(detail).queryByText('Stripe webhook handling for invoice payments'),
    ).not.toBeInTheDocument();
    // ...but the sidebar still lists tasks to choose from.
    expect(
      screen.getAllByText('Stripe webhook handling for invoice payments').length,
    ).toBeGreaterThan(0);
  });

  it('gives Slack its own section ahead of the other sources', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    const headings = within(detail).getAllByTestId('section-heading');
    expect(headings.map((h) => h.textContent)).toEqual(['Slack', 'Other sources']);

    const slack = within(detail).getByTestId('slack-section');
    expect(within(slack).getAllByTestId('detail-item')).toHaveLength(1);
    expect(
      within(slack).getByText('thread: webhook retries flaking on staging'),
    ).toBeInTheDocument();

    const other = within(detail).getByTestId('other-section');
    expect(within(other).getAllByTestId('detail-item')).toHaveLength(2);
  });

  it('links an item out to its url in a new tab', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const link = await screen.findByRole('link', {
      name: /feat\(payments\): add Stripe webhook handler/,
    });
    expect(link).toHaveAttribute('href', 'https://github.com/alan-eu/alan-apps/pull/1201');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('renders an item with no url as plain text', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    expect(within(detail).getByText('Write tests for payments retry logic')).toBeInTheDocument();
    expect(
      within(detail).queryByRole('link', { name: /Write tests for payments retry logic/ }),
    ).not.toBeInTheDocument();
  });

  it('filters the sidebar by title', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    await user.type(await screen.findByLabelText('Search tasks'), 'refresh token');

    await waitFor(() =>
      expect(screen.getAllByText('Refresh token rotation on scope change')).toHaveLength(1),
    );
  });

  it('toggles read from the detail panel', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByLabelText('Toggle read/unread'));

    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(false),
    );
  });

  it('offers delete on a manual task only', async () => {
    renderApp(detailRoute(AUTH_TASK_ID));

    const detail = await panel();
    await within(detail).findByText('Refresh token rotation on scope change');
    expect(within(detail).getByRole('button', { name: /Delete/ })).toBeInTheDocument();
  });

  it('hides delete on an auto task, which the API would refuse', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await within(detail).findByText('Stripe webhook handling for invoice payments');
    expect(within(detail).queryByRole('button', { name: /Delete/ })).not.toBeInTheDocument();
  });

  it('argues an AI suggestion and never applies it on its own', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));

    expect(await screen.findByText('Suggested bucket')).toBeInTheDocument();
    expect(screen.getByText(/83% confident/)).toBeInTheDocument();
    expect(screen.getByText(/which is billing work/)).toBeInTheDocument();
    expect(screen.getByText('new bucket')).toBeInTheDocument();

    // Shown, but nothing moved until the user says so.
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.bucket).toBe('Payments');
  });

  it('creates the bucket and moves the task when a new-bucket suggestion is accepted', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));
    await user.click(await screen.findByRole('button', { name: 'Create bucket and move' }));

    await waitFor(() => {
      expect(db.buckets.find((b) => b.name === 'Billing')?.keywords).toEqual(['stripe', 'refund']);
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.bucket).toBe('Billing');
    });
  });

  it('dismisses a suggestion without touching the task', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));
    await user.click(await screen.findByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(screen.queryByText('Suggested bucket')).not.toBeInTheDocument());
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.bucket).toBe('Payments');
  });

  it('explains itself when no AI credentials are configured', async () => {
    server.use(
      http.post('http://localhost:8000/api/buckets/suggest/:taskId', () =>
        HttpResponse.json({ detail: 'No credentials. Run `ant auth login`.' }, { status: 503 }),
      ),
    );
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));

    expect(await screen.findByText('No credentials. Run `ant auth login`.')).toBeInTheDocument();
  });
});
