import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';
import { ADA_ID } from '../test/fixtures';

const cardFor = async (name: string) => {
  const cards = await screen.findAllByTestId('person-card');
  return cards.find((card) => within(card).queryByText(name))!;
};

describe('PeopleView', () => {
  it('lists people with their handles across sources', async () => {
    renderApp('/people');

    const ada = await cardFor('Ada Lovelace');
    expect(within(ada).getByText('ada@acme.dev')).toBeInTheDocument();
    expect(within(ada).getByText('slack:U9')).toBeInTheDocument();
    expect(within(ada).getByText('github:adal')).toBeInTheDocument();
  });

  it('adds a handle to a person', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const ada = await cardFor('Ada Lovelace');
    await user.type(within(ada).getByLabelText(/New handle for Ada/), 'BRU-1');
    await user.click(within(ada).getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(db.people.find((p) => p.id === ADA_ID)?.identities.map((i) => i.value)).toContain(
        'BRU-1',
      ),
    );
  });

  it('removes a handle', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const ada = await cardFor('Ada Lovelace');
    await user.click(within(ada).getByLabelText('Remove github adal'));

    await waitFor(() =>
      expect(
        db.people.find((p) => p.id === ADA_ID)?.identities.some((i) => i.kind === 'github'),
      ).toBe(false),
    );
  });

  it('adds a new person', async () => {
    const user = userEvent.setup();
    renderApp('/people');
    await screen.findAllByTestId('person-card');

    await user.click(screen.getByRole('button', { name: /Add person/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'Katherine Johnson');
    await user.click(within(dialog).getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(db.people.some((p) => p.display_name === 'Katherine Johnson')).toBe(true),
    );
  });

  it('merges one person into another', async () => {
    const user = userEvent.setup();
    renderApp('/people');

    const grace = await cardFor('Grace Hopper');
    await user.click(within(grace).getByLabelText('Actions for Grace Hopper'));
    await user.click(await screen.findByRole('menuitem', { name: /Merge into/ }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByPlaceholderText('Keep this person'));
    // The dropdown portals out of the dialog; the name also heads a person card, so take the
    // "Ada Lovelace" that isn't inside a card — the option — once the dropdown has opened.
    const option = await waitFor(() => {
      const match = screen
        .getAllByText('Ada Lovelace')
        .find((el) => !el.closest('[data-testid="person-card"]'));
      if (!match) throw new Error('dropdown not open yet');
      return match;
    });
    await user.click(option);
    await user.click(within(dialog).getByRole('button', { name: 'Merge' }));

    await waitFor(() => expect(db.people.some((p) => p.id === 'person:grace')).toBe(false));
    expect(db.people.find((p) => p.id === ADA_ID)?.identities.map((i) => i.value)).toContain(
      'U0AERGW78CX',
    );
  });

  it('picks an identity avatar for a person', async () => {
    const user = userEvent.setup();
    db.people.find((p) => p.id === ADA_ID)!.identities[1].avatar_url = 'https://github/adal.png';
    renderApp('/people');

    const ada = await cardFor('Ada Lovelace');
    await user.click(await within(ada).findByRole('button', { name: 'Use this avatar' }));

    await waitFor(() =>
      expect(db.people.find((p) => p.id === ADA_ID)?.avatar_url).toBe('https://github/adal.png'),
    );
  });
});
