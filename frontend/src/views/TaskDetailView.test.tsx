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

  it('edits the task priority and persists it', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    const input = within(detail).getByLabelText('Priority');
    expect(input).toHaveValue('50');

    await user.clear(input);
    await user.type(input, '90');

    await waitFor(() => expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.priority).toBe(90));
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

  it('archives a task straight from its row menu', async () => {
    const user = userEvent.setup();
    renderApp('/task');

    await screen.findByText('Select a task from the list.');
    await user.click(
      screen.getByRole('button', { name: 'Actions for Refresh token rotation on scope change' }),
    );
    await user.click(await screen.findByRole('menuitem', { name: /Archive/ }));

    await waitFor(() => expect(db.tasks.find((t) => t.id === AUTH_TASK_ID)?.archived).toBe(true));
  });

  it('bulk-archives the tasks ticked in the sidebar', async () => {
    const user = userEvent.setup();
    renderApp('/task');

    await screen.findByText('Select a task from the list.');
    await user.click(
      screen.getByRole('checkbox', {
        name: 'Select Stripe webhook handling for invoice payments',
      }),
    );
    await user.click(
      screen.getByRole('checkbox', { name: 'Select Refresh token rotation on scope change' }),
    );
    expect(screen.getByText('2 selected')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() => {
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.archived).toBe(true);
      expect(db.tasks.find((t) => t.id === AUTH_TASK_ID)?.archived).toBe(true);
    });
  });

  it('offers a handle to resize the task list', async () => {
    renderApp('/task');
    expect(await screen.findByLabelText('Resize task list')).toBeInTheDocument();
  });

  it('shows the people an item concerns, merged onto the task', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    // The task's merged People strip and the per-item avatar both name the author.
    expect(within(detail).getByText('People')).toBeInTheDocument();
    expect(within(detail).getAllByText('AD').length).toBeGreaterThan(0);
  });

  it('select-all ticks only the shown rows and keeps them when the filter clears', async () => {
    const user = userEvent.setup();
    renderApp('/task');
    await screen.findByText('Select a task from the list.');

    // Narrow to one task, then select all shown.
    const search = screen.getByLabelText('Search tasks');
    await user.type(search, 'refresh token');
    await waitFor(() =>
      expect(screen.getAllByText('Refresh token rotation on scope change')).toHaveLength(1),
    );
    await user.click(screen.getByRole('checkbox', { name: 'Select all shown tasks' }));
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Clearing the filter keeps that one selected among the full list.
    await user.clear(search);
    await waitFor(() =>
      expect(screen.getByText('Stripe webhook handling for invoice payments')).toBeInTheDocument(),
    );
    expect(screen.getByText('1 selected')).toBeInTheDocument();
  });

  it('splits the task into an Activity lane (Slack first) and a Code lane', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    const headings = within(detail).getAllByTestId('section-heading');
    expect(headings.map((h) => h.textContent)).toEqual(['Slack', 'Activity', 'Code']);

    const slack = within(detail).getByTestId('slack-section');
    expect(within(slack).getAllByTestId('detail-item')).toHaveLength(1);
    expect(
      within(slack).getByText('thread: webhook retries flaking on staging'),
    ).toBeInTheDocument();

    // The PR left the Activity lane for the Code lane; only the todo remains there.
    const activity = within(detail).getByTestId('other-section');
    expect(within(activity).getAllByTestId('detail-item')).toHaveLength(1);
    expect(within(activity).getByText('Write tests for payments retry logic')).toBeInTheDocument();

    const codeLane = within(detail).getByTestId('code-lane');
    expect(within(codeLane).getAllByTestId('code-item')).toHaveLength(1);
    expect(
      within(codeLane).getByText('feat(payments): add Stripe webhook handler'),
    ).toBeInTheDocument();
  });

  it('gathers the branches into one card and the PR stack into another', async () => {
    renderApp(detailRoute(AUTH_TASK_ID));

    const detail = await panel();

    // Every local branch reads once, in a single Branches card.
    const branches = within(detail).getByTestId('branches-card');
    expect(within(branches).getByText('dev/auth-base')).toBeInTheDocument();
    expect(within(branches).getByText('dev/auth-session-timeout')).toBeInTheDocument();

    // Both PRs of the stack sit in one code card, not two.
    const codeItems = within(detail).getAllByTestId('code-item');
    expect(codeItems).toHaveLength(1);
    const stack = codeItems[0];
    expect(within(stack).getByText('feat(auth): base session store')).toBeInTheDocument();
    expect(
      within(stack).getByText('fix(auth): rotate refresh tokens on scope change'),
    ).toBeInTheDocument();
    expect(within(stack).getByText('git-spice stack')).toBeInTheDocument();
  });

  it('flags a filed branch as deleted once the source stops reporting it', async () => {
    const auth = db.tasks.find((t) => t.id === AUTH_TASK_ID)!;
    auth.items.find((i) => i.branch === 'dev/auth-session-timeout')!.gone = true;
    renderApp(detailRoute(AUTH_TASK_ID));

    const detail = await panel();
    const branches = within(detail).getByTestId('branches-card');
    expect(within(branches).getByText('deleted')).toBeInTheDocument();
    expect(within(branches).getByText('dev/auth-session-timeout')).toBeInTheDocument();
  });

  it('links an item out to its url in a new tab', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const link = await screen.findByRole('link', {
      name: /feat\(payments\): add Stripe webhook handler/,
    });
    expect(link).toHaveAttribute('href', 'https://github.com/acme/webapp/pull/1201');
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

  it('reads a task on open, and the toggle flips it back to unread', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    // Opening the (unread) task marks it read.
    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(false),
    );

    await user.click(within(detail).getByLabelText('Toggle read/unread'));
    await waitFor(() => expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(true));
  });

  it('offers archive and delete on any task', async () => {
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await within(detail).findByText('Stripe webhook handling for invoice payments');
    expect(within(detail).getByRole('button', { name: /Archive/ })).toBeInTheDocument();
    expect(within(detail).getByRole('button', { name: /Delete/ })).toBeInTheDocument();
  });

  it('archives a task, keeping it out of the active list but not deleting it', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Archive/ }));

    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.archived).toBe(true),
    );
    // Archived, not deleted — the row is still there.
    expect(db.tasks.some((t) => t.id === PAYMENTS_TASK_ID)).toBe(true);
  });

  it('reveals archived tasks behind a toggle and restores them', async () => {
    const user = userEvent.setup();
    db.tasks[0].archived = true;
    renderApp('/task');

    // Hidden from the default sidebar…
    await screen.findByText('Select a task from the list.');
    expect(
      screen.queryByText('Stripe webhook handling for invoice payments'),
    ).not.toBeInTheDocument();

    // …until the Archived toggle brings them in.
    await user.click(screen.getByRole('button', { name: /Archived/ }));
    await user.click(await screen.findByText('Stripe webhook handling for invoice payments'));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Restore/ }));
    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.archived).toBe(false),
    );
  });

  it('keeps the sidebar and toggle when the Archived view is empty', async () => {
    const user = userEvent.setup();
    renderApp('/task'); // no archived tasks in the default fixtures

    await screen.findByText('Select a task from the list.');
    await user.click(screen.getByRole('button', { name: /Archived/ }));

    // Empty archived view must not take over the whole screen — the toggle has to stay so
    // there's a way back to your tasks.
    await waitFor(() =>
      expect(
        screen.queryByText('Stripe webhook handling for invoice payments'),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText('No tasks yet.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Archived/ })).toBeInTheDocument();
    expect(screen.getByText('Select a task from the list.')).toBeInTheDocument();
  });

  it('deletes a task only after confirming in the dialog', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(AUTH_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Delete/ }));

    // A confirm dialog stands between the click and the deletion.
    const dialog = await screen.findByRole('dialog');
    expect(db.tasks.some((t) => t.id === AUTH_TASK_ID)).toBe(true);
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(db.tasks.some((t) => t.id === AUTH_TASK_ID)).toBe(false));
  });

  // Suggest bucket only appears next to the badge on an uncategorized task, so these open
  // the Payments task after clearing its bucket.
  const makeUncategorized = () =>
    (db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)!.bucket = 'Uncategorized');

  it('argues an AI suggestion and never applies it on its own', async () => {
    const user = userEvent.setup();
    makeUncategorized();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));

    expect(await screen.findByText('Suggested bucket')).toBeInTheDocument();
    expect(screen.getByText(/83% confident/)).toBeInTheDocument();
    expect(screen.getByText(/which is billing work/)).toBeInTheDocument();
    expect(screen.getByText('new bucket')).toBeInTheDocument();

    // Shown, but nothing moved until the user says so.
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.bucket).toBe('Uncategorized');
  });

  it('creates the bucket and moves the task when a new-bucket suggestion is accepted', async () => {
    const user = userEvent.setup();
    makeUncategorized();
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
    makeUncategorized();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));
    await user.click(await screen.findByRole('button', { name: 'Dismiss' }));

    await waitFor(() => expect(screen.queryByText('Suggested bucket')).not.toBeInTheDocument());
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.bucket).toBe('Uncategorized');
  });

  it('explains itself when no AI credentials are configured', async () => {
    server.use(
      http.post('http://localhost:8000/api/buckets/suggest/:taskId', () =>
        HttpResponse.json({ detail: 'No credentials. Run `ant auth login`.' }, { status: 503 }),
      ),
    );
    const user = userEvent.setup();
    makeUncategorized();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    await user.click(within(detail).getByRole('button', { name: /Suggest bucket/ }));

    expect(await screen.findByText('No credentials. Run `ant auth login`.')).toBeInTheDocument();
  });

  it('shows a Next action button, then the card with a refresh once produced', async () => {
    const user = userEvent.setup();
    renderApp(detailRoute(PAYMENTS_TASK_ID));

    const detail = await panel();
    // No next action yet → a button stands in for the card.
    await user.click(within(detail).getByRole('button', { name: 'Next action' }));

    // Once produced, the card shows with a refresh control and the standalone button is gone.
    expect(await within(detail).findByText(/Review the latest PR comments/)).toBeInTheDocument();
    expect(within(detail).getByRole('button', { name: 'Refresh next action' })).toBeInTheDocument();
    expect(within(detail).queryByRole('button', { name: 'Next action' })).not.toBeInTheDocument();
  });
});
