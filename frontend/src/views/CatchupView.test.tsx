import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { server } from '../test/server';
import { db } from '../test/handlers';
import { PAYMENTS_TASK_ID, SLACK_ITEM_ID } from '../test/fixtures';

describe('CatchupView', () => {
  it('lists the untriaged items', async () => {
    renderApp('/catchup');

    await waitFor(() => expect(screen.getAllByTestId('catchup-card')).toHaveLength(2));
    expect(screen.getByText('2 to triage')).toBeInTheDocument();
    expect(
      screen.getByText('thread: can someone look at the webhook retry storm?'),
    ).toBeInTheDocument();
    expect(screen.getByText('#payments-eng, 4 replies')).toBeInTheDocument();
  });

  it('files skipped items under the Skipped tab and un-skips them', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const cards = await screen.findAllByTestId('catchup-card');
    await user.click(within(cards[0]).getByRole('button', { name: 'Skip' }));

    await user.click(screen.getByText('Skipped'));

    const skippedCard = await screen.findByTestId('catchup-card');
    expect(within(skippedCard).getByText('Skipped')).toBeInTheDocument();
    await user.click(within(skippedCard).getByRole('button', { name: 'Un-skip' }));

    expect(await screen.findByText('Nothing skipped')).toBeInTheDocument();
  });

  it('shows matching progress and can stop it', async () => {
    const user = userEvent.setup();
    let stopped = false;
    server.use(
      http.get('http://localhost:8000/api/catchup/match-status', () =>
        HttpResponse.json({ running: true, total: 10, done: 3, remaining: 7 }),
      ),
      http.post('http://localhost:8000/api/catchup/match-stop', () => {
        stopped = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp('/catchup');

    expect(await screen.findByText('7 left')).toBeInTheDocument();
    // The Match all button gives way to the progress while a pass runs.
    expect(screen.queryByRole('button', { name: /Match all/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(stopped).toBe(true));
  });

  it('filters the items to triage by the header search', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');
    await waitFor(() => expect(screen.getAllByTestId('catchup-card')).toHaveLength(2));

    await user.type(screen.getByLabelText('Search'), 'auth-session');

    await waitFor(() => expect(screen.getAllByTestId('catchup-card')).toHaveLength(1));
    expect(screen.getByText('[webapp] dev/auth-session-timeout')).toBeInTheDocument();
    expect(screen.getByText('1 to triage (of 2)')).toBeInTheDocument();
  });

  it('says so when the search matches no items', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');
    await screen.findAllByTestId('catchup-card');

    await user.type(screen.getByLabelText('Search'), 'nothingmatchesthis');

    await waitFor(() => expect(screen.queryByTestId('catchup-card')).not.toBeInTheDocument());
    expect(screen.getByText(/No items match/)).toBeInTheDocument();

    // The way out of an over-narrow search is right there in the empty state (the header
    // carries the other clear control, so target the last one).
    const clears = screen.getAllByRole('button', { name: 'Clear search' });
    await user.click(clears[clears.length - 1]);
    await waitFor(() => expect(screen.getAllByTestId('catchup-card').length).toBeGreaterThan(0));
    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('stages a task made from an item in its attach box, still in the inbox', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const cards = await screen.findAllByTestId('catchup-card');
    await user.click(within(cards[0]).getByRole('button', { name: 'New task' }));
    const title = await screen.findByLabelText('Title');
    await user.clear(title);
    await user.type(title, 'Fresh subject');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    // New task doesn't file the item — it stays in the inbox with the new task staged as a
    // selected value in its attach box, waiting for Attach.
    const staged = await screen.findAllByTestId('catchup-card');
    expect(staged).toHaveLength(2);
    expect(await within(staged[0]).findByText('Fresh subject · Uncategorized')).toBeInTheDocument();
  });

  it('links an item out to its source', async () => {
    renderApp('/catchup');

    const link = await screen.findByRole('link', {
      name: /thread: can someone look at the webhook retry storm\?/,
    });
    expect(link).toHaveAttribute('href', 'https://acme.slack.com/archives/C01/p2');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('shows an already-attached task pre-selected in the attach box, not as a badge', async () => {
    db.catchup.push({
      id: 'slack:confirmed-1',
      source: 'slack',
      label: 'already filed thread',
      url: null,
      context: '#mo',
      occurred_at: new Date().toISOString(),
      triaged: false,
      triage_reason: null,
      triaged_at: null,
      pr_status: null,
      pr_review_requested: false,
      emoji: {},
      stack: [],
      people: [],
      links: [
        {
          task: {
            id: PAYMENTS_TASK_ID,
            title: 'Stripe webhook handling for invoice payments',
            bucket: 'Payments',
          },
          state: 'confirmed',
          engine: null,
          confidence: 1,
          reason: 'You said so',
        },
      ],
    });
    renderApp('/catchup');

    const card = (await screen.findByText('already filed thread')).closest(
      '[data-testid="catchup-card"]',
    ) as HTMLElement;
    // The confirmed task is a selected value in the attach box, not a CONFIRMED badge row.
    expect(within(card).queryByTestId('link-confirmed')).not.toBeInTheDocument();
    expect(
      within(card).getByText('Stripe webhook handling for invoice payments · Payments'),
    ).toBeInTheDocument();
  });

  it('edits a brain-dump note in place', async () => {
    const user = userEvent.setup();
    db.catchup.push({
      id: 'note:abc',
      source: 'note',
      label: 'old text',
      url: null,
      context: null,
      occurred_at: new Date().toISOString(),
      triaged: false,
      triage_reason: null,
      triaged_at: null,
      pr_status: null,
      pr_review_requested: false,
      emoji: {},
      stack: [],
      people: [],
      links: [],
    });
    renderApp('/catchup');

    const card = (await screen.findByText('old text')).closest(
      '[data-testid="catchup-card"]',
    ) as HTMLElement;
    await user.click(within(card).getByRole('button', { name: 'Edit note' }));
    const textarea = await screen.findByLabelText('Note text');
    await user.clear(textarea);
    await user.type(textarea, 'new text');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(db.catchup.find((i) => i.id === 'note:abc')?.label).toBe('new text'),
    );
  });

  it('argues a proposal with its engine, confidence and reason', async () => {
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    expect(within(proposed).getByText('Proposed')).toBeInTheDocument();
    expect(within(proposed).getByText(/72% confident/)).toBeInTheDocument();
    expect(within(proposed).getByText(/keyword/)).toBeInTheDocument();
    expect(
      within(proposed).getByText(/Shares the words "webhook" and "retry"/),
    ).toBeInTheDocument();
  });

  it('stages a confirmed proposal in the attach box, then Attach files it', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    const card = proposed.closest('[data-testid="catchup-card"]') as HTMLElement;
    await user.click(within(proposed).getByRole('button', { name: 'Confirm' }));

    // Accepting a proposal stages it — its row moves into the attach box and the item stays
    // in the inbox — rather than filing on the spot, so you can add more tasks first.
    await waitFor(() =>
      expect(within(card).queryByTestId('link-proposed')).not.toBeInTheDocument(),
    );
    expect(db.catchup.find((i) => i.id === SLACK_ITEM_ID)?.triaged).toBe(false);

    await user.click(within(card).getByRole('button', { name: 'Attach' }));

    await waitFor(() => {
      const item = db.catchup.find((i) => i.id === SLACK_ITEM_ID);
      expect(item?.triaged).toBe(true);
      expect(item?.links.some((l) => l.state === 'confirmed')).toBe(true);
    });
  });

  it('rejects a proposal but keeps the item to decide on', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    await user.click(within(proposed).getByRole('button', { name: 'Reject' }));

    await waitFor(() => expect(screen.getByTestId('link-rejected')).toBeInTheDocument());

    const item = db.catchup.find((i) => i.id === SLACK_ITEM_ID);
    expect(item?.links[0].state).toBe('rejected');
    expect(item?.triaged).toBe(false);
    expect(screen.getAllByTestId('catchup-card')).toHaveLength(2);
  });

  it('attaches one item to several tasks at once', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const cards = await screen.findAllByTestId('catchup-card');
    const card = cards[0];

    const input = within(card).getByPlaceholderText('Attach to tasks…');
    await user.click(input);
    const listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    await user.click(await within(listbox).findByText(/Refund flow throws on partial captures/));
    await user.click(await within(listbox).findByText(/Refresh token rotation on scope change/));
    await user.click(within(card).getByRole('button', { name: 'Attach' }));

    await waitFor(() => {
      const item = db.catchup.find((i) => i.id === SLACK_ITEM_ID);
      const confirmed = item?.links.filter((l) => l.state === 'confirmed').map((l) => l.task.id);
      expect(confirmed).toHaveLength(2);
      expect(item?.triaged).toBe(true);
    });
  });

  it('skips an item without attaching it anywhere', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const cards = await screen.findAllByTestId('catchup-card');
    await user.click(within(cards[1]).getByRole('button', { name: 'Skip' }));

    await waitFor(() => expect(screen.getAllByTestId('catchup-card')).toHaveLength(1));
  });

  it('creates a new task from an item', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const cards = await screen.findAllByTestId('catchup-card');
    await user.click(within(cards[0]).getByRole('button', { name: 'New task' }));

    const title = await screen.findByLabelText('Title');
    expect(title).toHaveValue('thread: can someone look at the webhook retry storm?');

    await user.clear(title);
    await user.type(title, 'Webhook retry storm');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(db.tasks.some((t) => t.title === 'Webhook retry storm')).toBe(true));
  });

  it('celebrates an empty inbox', async () => {
    server.use(http.get('http://localhost:8000/api/catchup', () => HttpResponse.json([])));
    renderApp('/catchup');

    expect(await screen.findByText('Inbox zero')).toBeInTheDocument();
  });

  it('surfaces the API detail when an action fails', async () => {
    server.use(
      http.post(
        `http://localhost:8000/api/catchup/${encodeURIComponent(SLACK_ITEM_ID)}/confirm`,
        () => HttpResponse.json({ detail: `Task not found: ${PAYMENTS_TASK_ID}` }, { status: 404 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    const card = proposed.closest('[data-testid="catchup-card"]') as HTMLElement;
    await user.click(within(proposed).getByRole('button', { name: 'Confirm' }));
    // The failure only happens on Attach now — Confirm just stages the task.
    await user.click(within(card).getByRole('button', { name: 'Attach' }));

    expect(await screen.findByText(`Task not found: ${PAYMENTS_TASK_ID}`)).toBeInTheDocument();
  });
});
