import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Providers } from '../test/utils';
import { db } from '../test/handlers';
import { PeopleStrip } from './PeopleStrip';
import type { ItemPerson } from '../types';

describe('PeopleStrip', () => {
  it('merges cross-source identities through the directory into one person', async () => {
    // One human in the directory, known by a Slack id and a GitHub login.
    db.people = [
      {
        id: 'p1',
        display_name: 'Ada Lovelace',
        email: null,
        note: null,
        identities: [
          { id: 'i1', kind: 'slack', value: 'U1', label: null },
          { id: 'i2', kind: 'github', value: 'ada', label: null },
        ],
      },
    ];
    const people: ItemPerson[] = [
      { kind: 'slack', value: 'U1', name: 'ada.l', role: 'mentioned' },
      { kind: 'github', value: 'ada', name: 'ada', role: 'author' },
    ];

    render(
      <Providers>
        <PeopleStrip people={people} />
      </Providers>,
    );

    // Once the directory loads, the two collapse into one avatar under the directory name —
    // the github raw-name initials ("AD") are gone, only the merged "AL" remains.
    await waitFor(() => expect(screen.queryByText('AD')).not.toBeInTheDocument());
    expect(screen.getByText('AL')).toBeInTheDocument();
  });

  it('renders a source avatar image when one is provided', async () => {
    db.people = [];
    const { container } = render(
      <Providers>
        <PeopleStrip
          people={[
            {
              kind: 'github',
              value: 'ada',
              name: 'ada',
              role: 'author',
              avatar: 'https://img/ada.png',
            },
          ]}
        />
      </Providers>,
    );

    await waitFor(() =>
      expect(container.querySelector('img')).toHaveAttribute('src', 'https://img/ada.png'),
    );
  });

  it('falls back to initials for someone not in the directory', async () => {
    db.people = [];
    render(
      <Providers>
        <PeopleStrip
          people={[{ kind: 'slack', value: 'U9', name: 'Bob Smith', role: 'mentioned' }]}
        />
      </Providers>,
    );

    expect(await screen.findByText('BS')).toBeInTheDocument();
  });
});
