import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';
import { PAYMENTS_TASK_ID } from '../test/fixtures';

describe('TimelineView', () => {
  it('yields one row per item, not per task', async () => {
    renderApp('/timeline');

    await waitFor(() => expect(screen.getAllByTestId('timeline-row')).toHaveLength(6));
    expect(screen.getByText('6 items, most recent first')).toBeInTheDocument();
  });

  it('shows each row with its source, bucket and item label', async () => {
    renderApp('/timeline');

    await screen.findAllByTestId('timeline-row');
    expect(screen.getByText('feat(payments): add Stripe webhook handler')).toBeInTheDocument();
    expect(screen.getByText('thread: webhook retries flaking on staging')).toBeInTheDocument();
    expect(screen.getAllByText('Payments').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Slack').length).toBeGreaterThan(0);
  });

  it('orders rows newest first', async () => {
    renderApp('/timeline');

    const rows = await screen.findAllByTestId('timeline-row');
    // The catch-up-free fixture's newest item is the 95m-old Slack thread.
    expect(rows[0]).toHaveTextContent('thread: webhook retries flaking on staging');
    expect(rows[rows.length - 1]).toHaveTextContent('Write tests for payments retry logic');
  });

  it('filters rows through the header search', async () => {
    const user = userEvent.setup();
    renderApp('/timeline');

    await screen.findAllByTestId('timeline-row');
    await user.type(screen.getByLabelText('Search'), 'bucket:auth');

    await waitFor(() => expect(screen.getAllByTestId('timeline-row')).toHaveLength(2));
  });

  it('toggles read straight from a row', async () => {
    const user = userEvent.setup();
    renderApp('/timeline');

    await screen.findAllByTestId('timeline-row');
    await user.click(screen.getAllByLabelText('Toggle read/unread')[0]);

    await waitFor(() =>
      expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(false),
    );
  });
});
