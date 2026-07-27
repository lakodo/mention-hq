import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';

/**
 * jsdom has no layout, so spatial navigation (which reads getBoundingClientRect) needs the
 * elements under test given explicit rects. Only elements laid out here become candidates —
 * collectFocusables drops anything with no client rects — which keeps each test's geometry small.
 */
function layout(el: Element, left: number, top: number, width = 100, height = 24) {
  const rect = {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
  const target = el as HTMLElement;
  target.getBoundingClientRect = () => rect;
  target.getClientRects = () => [rect] as unknown as DOMRectList;
}

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
    await user.keyboard('1');
    expect(await screen.findByText(/to triage/)).toBeInTheDocument();
  });

  it('opens the shortcuts help with ?', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await user.keyboard('?');
    expect(await screen.findByText('Keyboard shortcuts')).toBeInTheDocument();
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
    await user.keyboard('2');
    expect(search).toHaveValue('2');
    expect(screen.queryByText(/to triage/)).not.toBeInTheDocument();
  });

  it('shows each tab its go-to key while g is armed', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByRole('button', { name: /Catch-up/ });

    await user.keyboard('g');

    await waitFor(() => expect(document.querySelectorAll('kbd').length).toBeGreaterThan(0));
    const keys = [...document.querySelectorAll('kbd')].map((k) => k.textContent);
    expect(keys).toContain('c');
    expect(keys).toContain('a');
  });
});

describe('spatial navigation', () => {
  it('crosses the header: a tab to the brain-dump on the left, to search on the right', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const bulb = await screen.findByLabelText('Brain dump');
    const catchup = screen.getByRole('button', { name: /Catch-up/ });
    const admin = screen.getByRole('button', { name: 'Admin' });
    const search = screen.getByLabelText('Search');
    layout(bulb, 0, 0, 40);
    layout(catchup, 60, 0);
    layout(admin, 600, 0);
    layout(search, 720, 0, 200);

    catchup.focus();
    await user.keyboard('{ArrowLeft}');
    expect(bulb).toHaveFocus();

    admin.focus();
    await user.keyboard('{ArrowRight}');
    expect(search).toHaveFocus();
  });

  it('leaves the search box rightward to the auto-sync toggle when the caret is at the end', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const search = await screen.findByLabelText('Search');
    const autoSync = screen.getByLabelText('Auto-sync');
    layout(search, 720, 0, 200);
    layout(autoSync, 960, 0, 60);

    search.focus(); // empty value → caret sits at both start and end
    await user.keyboard('{ArrowRight}');
    expect(autoSync).toHaveFocus();
  });

  it('moves between a task row checkbox and its title', async () => {
    const user = userEvent.setup();
    renderApp('/task');

    const title = 'Stripe webhook handling for invoice payments';
    const checkbox = await screen.findByLabelText(`Select ${title}`);
    const taskName = screen.getByLabelText(title);
    layout(checkbox, 0, 40, 20, 20);
    layout(taskName, 30, 40, 240, 20);

    checkbox.focus();
    await user.keyboard('{ArrowRight}');
    expect(taskName).toHaveFocus();

    await user.keyboard('{ArrowLeft}');
    expect(checkbox).toHaveFocus();
  });
});
