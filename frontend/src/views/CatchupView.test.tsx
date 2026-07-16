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
    expect(screen.getByText('2 items to triage')).toBeInTheDocument();
    expect(
      screen.getByText('thread: can someone look at the webhook retry storm?'),
    ).toBeInTheDocument();
    expect(screen.getByText('#payments-eng, 4 replies')).toBeInTheDocument();
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

  it('confirms a proposal, taking the item out of the inbox', async () => {
    const user = userEvent.setup();
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    await user.click(within(proposed).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      const item = db.catchup.find((i) => i.id === SLACK_ITEM_ID);
      expect(item?.triaged).toBe(true);
      expect(item?.links[0].state).toBe('confirmed');
    });

    await waitFor(() => expect(screen.getAllByTestId('catchup-card')).toHaveLength(1));
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

    // Every card owns a combobox, so the options have to be picked within this one.
    await user.click(within(card).getByPlaceholderText('Attach to tasks…'));
    await user.click(await within(card).findByText(/Refund flow throws on partial captures/));
    await user.click(await within(card).findByText(/Refresh token rotation on scope change/));
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
    server.use(http.get('http://localhost:8000/catchup', () => HttpResponse.json([])));
    renderApp('/catchup');

    expect(await screen.findByText('Inbox zero')).toBeInTheDocument();
  });

  it('surfaces the API detail when an action fails', async () => {
    server.use(
      http.post(`http://localhost:8000/catchup/${encodeURIComponent(SLACK_ITEM_ID)}/confirm`, () =>
        HttpResponse.json({ detail: `Task not found: ${PAYMENTS_TASK_ID}` }, { status: 404 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/catchup');

    const proposed = await screen.findByTestId('link-proposed');
    await user.click(within(proposed).getByRole('button', { name: 'Confirm' }));

    expect(await screen.findByText(`Task not found: ${PAYMENTS_TASK_ID}`)).toBeInTheDocument();
  });
});
