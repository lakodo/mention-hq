import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';

describe('TimelineView', () => {
  it('shows every item, whether or not it is on a task', async () => {
    renderApp('/timeline');

    // Six items live on the fixture's tasks; catch-up adds one more that isn't on any
    // (the other catch-up item is the same branch already filed under the Auth task).
    await waitFor(() => expect(screen.getAllByTestId('timeline-row')).toHaveLength(7));
    expect(screen.getByText('7 items, most recent first')).toBeInTheDocument();
  });

  it('shows each row with its source and item label', async () => {
    renderApp('/timeline');

    await screen.findAllByTestId('timeline-row');
    expect(screen.getByText('feat(payments): add Stripe webhook handler')).toBeInTheDocument();
    expect(
      screen.getByText('thread: can someone look at the webhook retry storm?'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Slack').length).toBeGreaterThan(0);
  });

  it('links a filed item to the task it belongs to', async () => {
    const user = userEvent.setup();
    renderApp('/timeline');

    const rows = await screen.findAllByTestId('timeline-row');
    const filed = rows.find((row) =>
      within(row).queryByText('feat(payments): add Stripe webhook handler'),
    )!;
    await user.click(within(filed).getByText('Stripe webhook handling for invoice payments'));

    await waitFor(() => expect(screen.getByTestId('task-detail')).toBeInTheDocument());
  });

  it('marks an untriaged item as still to triage', async () => {
    renderApp('/timeline');

    const rows = await screen.findAllByTestId('timeline-row');
    const untriaged = rows.find((row) =>
      within(row).queryByText('thread: can someone look at the webhook retry storm?'),
    )!;
    expect(within(untriaged).getByText('To triage')).toBeInTheDocument();
  });

  it('filters rows through the header search', async () => {
    const user = userEvent.setup();
    renderApp('/timeline');

    await screen.findAllByTestId('timeline-row');
    await user.type(screen.getByLabelText('Search'), 'auth-session');

    await waitFor(() => expect(screen.getAllByTestId('timeline-row')).toHaveLength(1));
  });
});
