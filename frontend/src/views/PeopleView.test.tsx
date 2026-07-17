import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';
import { BRUNO_ID } from '../test/fixtures';

const cardFor = async (name: string) => {
  const cards = await screen.findAllByTestId('person-card');
  return cards.find((card) => within(card).queryByText(name))!;
};

describe('PeopleView', () => {
  it('lists people with their handles across sources', async () => {
    renderApp('/people');

    const bruno = await cardFor('Bruno Vegreville');
    expect(within(bruno).getByText('bruno@acme.dev')).toBeInTheDocument();
    expect(within(bruno).getByText('slack:U9')).toBeInTheDocument();
    expect(within(bruno).getByText('github:brunov')).toBeInTheDocument();
  });

  it('adds a handle to a person', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const bruno = await cardFor('Bruno Vegreville');
    await user.type(within(bruno).getByLabelText(/New handle for Bruno/), 'BRU-1');
    await user.click(within(bruno).getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(db.people.find((p) => p.id === BRUNO_ID)?.identities.map((i) => i.value)).toContain(
        'BRU-1',
      ),
    );
  });

  it('removes a handle', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const bruno = await cardFor('Bruno Vegreville');
    await user.click(within(bruno).getByLabelText('Remove github brunov'));

    await waitFor(() =>
      expect(
        db.people.find((p) => p.id === BRUNO_ID)?.identities.some((i) => i.kind === 'github'),
      ).toBe(false),
    );
  });

  it('adds a new person', async () => {
    const user = userEvent.setup();
    renderApp('/people');
    await screen.findAllByTestId('person-card');

    await user.click(screen.getByRole('button', { name: /Add person/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'Gabrielle Bastet');
    await user.click(within(dialog).getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(db.people.some((p) => p.display_name === 'Gabrielle Bastet')).toBe(true),
    );
  });

  it('merges one person into another', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const alex = await cardFor('Alexandre Bermudez');
    await user.click(within(alex).getByLabelText('Actions for Alexandre Bermudez'));
    await user.click(await screen.findByRole('menuitem', { name: /Merge into/ }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByPlaceholderText('Keep this person'));
    await user.click(await within(dialog).findByText('Bruno Vegreville'));
    await user.click(within(dialog).getByRole('button', { name: 'Merge' }));

    await waitFor(() => expect(db.people.some((p) => p.id === 'person:alex')).toBe(false));
    expect(db.people.find((p) => p.id === BRUNO_ID)?.identities.map((i) => i.value)).toContain(
      'U0AERGW78CX',
    );
  });
});
