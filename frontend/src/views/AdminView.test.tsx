import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/utils';
import { db } from '../test/handlers';

describe('AdminView', () => {
  it('renders a card per source with its description and status', async () => {
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github');
    expect(
      within(github).getByText('Your open pull requests and assigned issues'),
    ).toBeInTheDocument();
    // The status badge and the detail line both read "Not configured" here.
    expect(within(github).getAllByText('Not configured').length).toBeGreaterThan(0);

    const slack = screen.getByTestId('source-card-slack');
    expect(within(slack).getByText('Connected')).toBeInTheDocument();
    expect(within(slack).getByText('4 channels watched')).toBeInTheDocument();
  });

  it('builds each source form from its own fields, secrets as password inputs', async () => {
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github');
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

    const slack = await screen.findByTestId('source-card-slack');
    const token = within(slack).getByLabelText(/User token/);
    expect(token).toHaveValue('');
    expect(token).toHaveAttribute('placeholder', '••••••••1234');
    expect(within(slack).getByText(/Stored/)).toBeInTheDocument();
  });

  it('saves only the fields the user actually edited', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const github = await screen.findByTestId('source-card-github');
    await user.type(within(github).getByLabelText(/Username/), 'octocat');
    await user.click(within(github).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const source = db.sources.find((s) => s.id === 'github');
      expect(source?.fields.find((f) => f.key === 'username')?.value).toBe('octocat');
      // The untouched secret must survive a save whose payload omits its key.
      expect(source?.fields.find((f) => f.key === 'token')?.is_set).toBe(false);
    });
  });

  it('tests a connection', async () => {
    const user = userEvent.setup();
    renderApp('/admin');

    const slack = await screen.findByTestId('source-card-slack');
    await user.click(within(slack).getByRole('button', { name: 'Test connection' }));

    await waitFor(() =>
      expect(db.sources.find((s) => s.id === 'slack')?.last_checked_at).toBeTruthy(),
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
});
