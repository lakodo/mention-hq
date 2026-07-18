import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';
import { makeSourceFields } from '../test/fixtures';
import type { SourceStatus } from '../types';

/** Walk the Add-a-source picker: pick a kind, name the instance, submit. */
async function addSource(user: ReturnType<typeof userEvent.setup>, kind: string, name: string) {
  await user.click(await screen.findByRole('button', { name: 'Add a source' }));
  await user.click(await screen.findByRole('menuitem', { name: new RegExp(kind) }));
  const input = await screen.findByLabelText('Name');
  await user.clear(input);
  await user.type(input, name);
  await user.click(screen.getByRole('button', { name: 'Add' }));
}

describe('AdminView', () => {
  it('renders a card per source with its description and status', async () => {
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    expect(within(github).getByText('Work GitHub')).toBeInTheDocument();
    expect(
      within(github).getByText('Your open pull requests and assigned issues'),
    ).toBeInTheDocument();
    // The status badge and the detail line both read "Not configured" here.
    expect(within(github).getAllByText('Not configured').length).toBeGreaterThan(0);

    const slack = screen.getByTestId('source-card-slack-slack');
    expect(within(slack).getByText('Connected')).toBeInTheDocument();
    expect(within(slack).getByText('4 channels watched')).toBeInTheDocument();
  });

  it('shows the manifest to copy when a source has one', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack-slack');
    expect(within(slack).getByText(/From a manifest/)).toBeInTheDocument();
    expect(within(slack).getByText(/display_information/)).toBeInTheDocument();

    const github = screen.getByTestId('source-card-github-work-github');
    expect(within(github).queryByText(/From a manifest/)).not.toBeInTheDocument();

    await user.click(within(slack).getByRole('button', { name: 'Copy' }));
    expect(await within(slack).findByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('tells a fresh install it has no sources yet', async () => {
    db.sources = [];
    renderApp('/admin');

    expect(await screen.findByText('No sources yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a source' })).toBeInTheDocument();
    expect(screen.queryByText(/0\/0 connected/)).not.toBeInTheDocument();
  });

  it('adds a source the user picked and named', async () => {
    const user = userEvent.setup();
    db.sources = [];
    renderApp('/admin');

    await addSource(user, 'Slack', 'Team Slack');

    await waitFor(() => expect(db.sources).toHaveLength(1));
    expect(db.sources[0].kind).toBe('slack');
    expect(db.sources[0].name).toBe('Team Slack');
    expect(await screen.findByTestId('source-card-slack-team-slack')).toBeInTheDocument();
  });

  it('reports a name that is already taken', async () => {
    const user = userEvent.setup();
    renderApp('/admin');
    await screen.findByTestId('source-card-github-work-github');

    await addSource(user, 'GitHub', 'Work GitHub');

    expect(
      await screen.findByText('You already have a source called Work GitHub'),
    ).toBeInTheDocument();
    expect(db.sources.filter((s) => s.kind === 'github')).toHaveLength(1);
  });

  it('keeps two sources of the same kind independent', async () => {
    const user = userEvent.setup();
    renderApp('/admin');
    await screen.findByTestId('source-card-github-work-github');

    await addSource(user, 'GitHub', 'Personal GitHub');

    const work = await screen.findByTestId('source-card-github-work-github');
    const personal = await screen.findByTestId('source-card-github-personal-github');

    await user.type(within(personal).getByLabelText(/Username/), 'octocat');
    await user.click(within(personal).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const one = db.sources.find((s) => s.id === 'github-personal-github');
      expect(one?.fields.find((f) => f.key === 'username')?.value).toBe('octocat');
    });
    // The other GitHub shares a kind, not a config.
    expect(db.sources.find((s) => s.id === 'github-work-github')?.fields[1].value).toBeNull();
    expect(within(work).getByLabelText(/Username/)).toHaveValue('');
  });

  it('renames a source', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    await user.click(within(github).getByLabelText('Rename Work GitHub'));
    const input = within(github).getByLabelText('Name for Work GitHub');
    await user.clear(input);
    await user.type(input, 'Day job GitHub');
    await user.click(within(github).getByRole('button', { name: 'Rename' }));

    await waitFor(() =>
      expect(db.sources.find((s) => s.id === 'github-work-github')?.name).toBe('Day job GitHub'),
    );
  });

  it('removes a source once the user confirms', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack-slack');
    await user.click(within(slack).getByLabelText('Remove Slack'));
    expect(await screen.findByText(/Its credentials are deleted with it/)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(db.sources.some((s) => s.id === 'slack-slack')).toBe(false));
    await waitFor(() =>
      expect(screen.queryByTestId('source-card-slack-slack')).not.toBeInTheDocument(),
    );
  });

  it('offers Detect only where a CLI can answer, and fills the form in from it', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack-slack');
    expect(within(slack).queryByRole('button', { name: 'Detect' })).not.toBeInTheDocument();

    const github = await screen.findByTestId('source-card-github-work-github');
    await user.click(within(github).getByRole('button', { name: 'Detect' }));

    expect(await within(github).findByText('Read your GitHub CLI login.')).toBeInTheDocument();
    // What the tool found lands in the form: the username visibly, the token as a mask.
    await waitFor(() => expect(within(github).getByLabelText(/Username/)).toHaveValue('9hgg'));
    expect(within(github).getByText(/Stored/)).toBeInTheDocument();
  });

  it('leaves the form alone when the CLI cannot answer, and says why', async () => {
    const user = userEvent.setup();
    db.detections.github = {
      available: false,
      detail: 'The GitHub CLI is not logged in — run `gh auth login`.',
      applied: {},
      choices: {},
      source: null,
    };
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    await user.click(within(github).getByRole('button', { name: 'Detect' }));

    expect(
      await within(github).findByText('The GitHub CLI is not logged in — run `gh auth login`.'),
    ).toBeInTheDocument();
    expect(within(github).getByLabelText(/Username/)).toHaveValue('');
    expect(within(github).getByLabelText(/Organisation/)).toBeInTheDocument();
  });

  it('turns what the CLI could not decide into a pick', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    await user.click(within(github).getByRole('button', { name: 'Detect' }));

    // `org` came back as choices, so it stops being a free-text field.
    const org = await within(github).findByLabelText(/Organisation/);
    expect(org).toHaveAttribute('readonly');
    await user.click(org);
    // The dropdown portals out of the card, so the option is picked at the screen.
    await user.click(await screen.findByText('widgets'));
    await user.click(within(github).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(
        db.sources.find((s) => s.id === 'github-work-github')?.fields.find((f) => f.key === 'org')
          ?.value,
      ).toBe('widgets'),
    );
  });

  it('shows where a credential comes from, as a link', async () => {
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    expect(within(github).getByText(/Press Detect if you use the GitHub CLI/)).toBeInTheDocument();
    const link = within(github).getByRole('link', { name: 'Create a token' });
    expect(link).toHaveAttribute('href', 'https://github.com/settings/tokens/new');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('builds each source form from its own fields, secrets as password inputs', async () => {
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    // Nothing here is hardcoded per source — both inputs come from `fields`.
    expect(within(github).getByLabelText(/Personal access token/)).toHaveAttribute(
      'type',
      'password',
    );
    expect(within(github).getByLabelText(/Username/)).not.toHaveAttribute('type', 'password');
    expect(within(github).getByText(/Needs the `repo` scope/)).toBeInTheDocument();
  });

  it('shows a stored secret as a mask, never a value', async () => {
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack-slack');
    const token = within(slack).getByLabelText(/User token/);
    expect(token).toHaveValue('');
    expect(token).toHaveAttribute('placeholder', '••••••••1234');
    expect(within(slack).getByText(/Stored/)).toBeInTheDocument();
  });

  it('saves only the fields the user actually edited', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github-work-github');
    await user.type(within(github).getByLabelText(/Username/), 'octocat');
    await user.click(within(github).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const source = db.sources.find((s) => s.id === 'github-work-github');
      expect(source?.fields.find((f) => f.key === 'username')?.value).toBe('octocat');
      // The untouched secret must survive a save whose payload omits its key.
      expect(source?.fields.find((f) => f.key === 'token')?.is_set).toBe(false);
    });
  });

  it('tests a connection', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack-slack');
    await user.click(within(slack).getByRole('button', { name: 'Test connection' }));

    await waitFor(() =>
      expect(db.sources.find((s) => s.id === 'slack-slack')?.last_checked_at).toBeTruthy(),
    );
  });

  it('renames the app and drives the header title from it', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const input = await screen.findByLabelText('App name');
    await user.clear(input);
    await user.type(input, 'Command Centre');
    await user.click(screen.getAllByRole('button', { name: 'Save' })[0]);

    await waitFor(() => expect(db.settings.app_name).toBe('Command Centre'));
    expect(await screen.findByText('Command Centre')).toBeInTheDocument();
  });

  it('backs up the database on demand and names the saved file', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    await user.click(await screen.findByRole('button', { name: 'Back up now' }));

    expect(await screen.findByText(/hq-20260717-220000\.db/)).toBeInTheDocument();
  });

  it('lists the buckets with their keywords and task counts', async () => {
    renderApp('/admin');

    const payments = await screen.findByTestId('bucket-row-Payments');
    expect(within(payments).getByText('2 tasks')).toBeInTheDocument();
    expect(within(payments).getByLabelText('Keywords for Payments')).toHaveValue('stripe, invoice');
  });

  it('creates a bucket', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    await user.type(await screen.findByLabelText('New bucket'), 'Infra');
    await user.type(screen.getByLabelText('Keywords'), 'terraform, k8s');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      const bucket = db.buckets.find((b) => b.name === 'Infra');
      expect(bucket?.keywords).toEqual(['terraform', 'k8s']);
    });
  });

  it('edits a bucket keyword list', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const payments = await screen.findByTestId('bucket-row-Payments');
    const input = within(payments).getByLabelText('Keywords for Payments');
    await user.clear(input);
    await user.type(input, 'stripe, refund, invoice');
    await user.click(within(payments).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(db.buckets.find((b) => b.name === 'Payments')?.keywords).toEqual([
        'stripe',
        'refund',
        'invoice',
      ]),
    );
  });

  it('deletes a bucket', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const auth = await screen.findByTestId('bucket-row-Auth');
    await user.click(within(auth).getByLabelText('Delete Auth'));

    await waitFor(() => expect(db.buckets.some((b) => b.name === 'Auth')).toBe(false));
  });

  it('re-applies keywords across every task', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    await user.click(await screen.findByRole('button', { name: 'Re-apply keywords' }));
    expect(await screen.findByText(/matched against the keywords again/)).toBeInTheDocument();
  });

  it('reports the AI status and stores a key', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    expect(await screen.findByText(/No credentials\. Run `ant auth login`/)).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();

    await user.type(screen.getByLabelText('API key'), 'sk-ant-test');
    await user.click(screen.getAllByRole('button', { name: 'Save' }).at(-1)!);

    await waitFor(() => expect(db.ai.available).toBe(true));
    expect(await screen.findByText('Available')).toBeInTheDocument();
  });

  it('offers OAuth Connect for a Notion source, with the detected redirect URI', async () => {
    const fields = makeSourceFields('notion').map((field) =>
      field.key === 'client_id' || field.key === 'client_secret'
        ? { ...field, is_set: true }
        : field,
    );
    const notion: SourceStatus = {
      id: 'notion-notion',
      kind: 'notion',
      name: 'Notion',
      position: 1,
      description: 'Pages you created, own, or are mentioned in',
      status: 'unconfigured',
      detail: 'Not configured',
      last_checked_at: null,
      error: null,
      fields,
      setup: '',
      setup_url: '',
      manifest: '',
      manifest_hint: '',
      detectable: false,
    };
    db.sources = [notion];
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    const user = userEvent.setup();
    renderApp('/admin');

    const card = await screen.findByTestId('source-card-notion-notion');
    expect(
      await within(card).findByText('http://jojohq/api/admin/oauth/notion/callback'),
    ).toBeInTheDocument();

    const connect = within(card).getByRole('button', { name: 'Connect to Notion' });
    expect(connect).toBeEnabled();
    await user.click(connect);

    await waitFor(() => expect(openSpy).toHaveBeenCalled());
    expect(openSpy.mock.calls[0][0]).toContain('api.notion.com/v1/oauth/authorize');
    openSpy.mockRestore();
  });
});
