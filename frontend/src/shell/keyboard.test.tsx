import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';

describe('global keyboard shortcuts', () => {
  it('jumps to a view with g then a letter', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.keyboard('gc');

    expect(await screen.findByText(/to triage/)).toBeInTheDocument();
  });

  it('jumps to a view with a number key', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.keyboard('1'); // first tab — Catch-up

    expect(await screen.findByText(/to triage/)).toBeInTheDocument();
  });

  it('opens the shortcuts help with ?', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.keyboard('?');

    expect(await screen.findByText('Keyboard shortcuts')).toBeInTheDocument();
    expect(screen.getByText('Open the command palette')).toBeInTheDocument();
  });

  it('opens the command palette on Cmd/Ctrl+K', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.keyboard('{Control>}k{/Control}');

    expect(await screen.findByPlaceholderText('Type a command or search…')).toBeInTheDocument();
  });

  it('stays dormant while typing in a field', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const search = await screen.findByLabelText('Search');
    await user.click(search);
    await user.keyboard('2'); // a nav shortcut, but we are typing

    expect(search).toHaveValue('2');
    // Still on the board — the number did not navigate to Tasks.
    expect(screen.queryByText(/to triage/)).not.toBeInTheDocument();
  });
});

describe('roving arrow navigation', () => {
  it('moves focus between nav tabs with the arrow keys', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const catchup = await screen.findByRole('button', { name: /Catch-up/ });
    const tasks = screen.getByRole('button', { name: 'Tasks' });
    catchup.focus();

    await user.keyboard('{ArrowRight}');

    expect(tasks).toHaveFocus();
  });

  it('moves down a board column with ↓ and opens the card with Enter', async () => {
    const user = userEvent.setup();
    const { container } = renderApp('/');

    // Wait for cards, then take a column that has at least two (Payments holds two in fixtures).
    await screen.findAllByText(/Stripe webhook|Refund flow|Refresh token/);
    const cards = Array.from(
      container.querySelectorAll<HTMLElement>('[data-roving-item][data-col]'),
    );
    const byColumn = new Map<string, HTMLElement[]>();
    for (const card of cards) {
      const col = card.dataset.col ?? '';
      byColumn.set(col, [...(byColumn.get(col) ?? []), card]);
    }
    const column = [...byColumn.values()].find((list) => list.length >= 2)!;

    column[0].focus();
    await user.keyboard('{ArrowDown}');
    expect(column[1]).toHaveFocus();

    await user.keyboard('{Enter}');

    // Enter opens the task — the header switches to its detail (the "← All tasks" back link).
    expect(await screen.findByText('← All tasks')).toBeInTheDocument();
  });
});
