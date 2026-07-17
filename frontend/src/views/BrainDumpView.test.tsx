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
});
