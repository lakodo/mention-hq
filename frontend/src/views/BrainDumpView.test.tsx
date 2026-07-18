import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';

describe('BrainDumpView', () => {
  it('captures typed text as a new item in catch-up', async () => {
    const user = userEvent.setup();
    renderApp('/braindump');

    await user.type(await screen.findByLabelText('Brain dump text'), 'renew the SSL cert');
    await user.click(screen.getByRole('button', { name: 'Capture' }));

    await waitFor(() =>
      expect(db.catchup.some((i) => i.source === 'note' && i.label === 'renew the SSL cert')).toBe(
        true,
      ),
    );
  });

  it('will not capture empty text', async () => {
    renderApp('/braindump');
    expect(await screen.findByRole('button', { name: 'Capture' })).toBeDisabled();
  });

  it('captures a link as a clickable item with the text as its description', async () => {
    const user = userEvent.setup();
    renderApp('/braindump');

    await user.type(await screen.findByLabelText('Link URL'), 'https://example.com/spec');
    await user.type(await screen.findByLabelText('Link title'), 'The spec');
    await user.type(screen.getByLabelText('Brain dump text'), 'read before the review');
    await user.click(screen.getByRole('button', { name: 'Capture' }));

    await waitFor(() => {
      const item = db.catchup.find((i) => i.url === 'https://example.com/spec');
      expect(item).toBeTruthy();
      expect(item?.label).toBe('The spec');
      expect(item?.context).toBe('read before the review');
    });
  });

  it('can capture a link with no description', async () => {
    const user = userEvent.setup();
    renderApp('/braindump');

    await user.type(await screen.findByLabelText('Link URL'), 'https://example.com/x');
    // With a URL present, an empty body is fine — the button is enabled.
    expect(screen.getByRole('button', { name: 'Capture' })).toBeEnabled();
  });
});
