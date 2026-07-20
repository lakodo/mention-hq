import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { Providers } from '../test/utils';
import { RepoBrowser } from './RepoBrowser';

function renderBrowser(onPick = vi.fn()) {
  render(
    <Providers>
      <RepoBrowser opened onClose={() => {}} onPick={onPick} />
    </Providers>,
  );
  return onPick;
}

describe('RepoBrowser', () => {
  it('lists folders and marks the git repositories', async () => {
    renderBrowser();

    expect(await screen.findByText('webapp')).toBeInTheDocument();
    expect(screen.getByText('notes')).toBeInTheDocument();
    // Only the repo carries the git badge.
    expect(screen.getByText('git')).toBeInTheDocument();
  });

  it('hands the picked folder back and nothing before', async () => {
    const user = userEvent.setup();
    const onPick = renderBrowser();

    await screen.findByText('webapp');
    expect(onPick).not.toHaveBeenCalled();

    await user.click(screen.getAllByRole('button', { name: 'Add' })[0]);

    await waitFor(() => expect(onPick).toHaveBeenCalledWith('/Users/you/webapp'));
  });

  it('descends into a folder when its name is clicked', async () => {
    const user = userEvent.setup();
    renderBrowser();

    await user.click(await screen.findByText('notes'));

    // The path line now reflects the folder we walked into.
    await waitFor(() => expect(screen.getByText('/Users/you/notes')).toBeInTheDocument());
  });
});
