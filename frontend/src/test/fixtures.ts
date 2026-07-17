import type {
  AIStatus,
  AppSettings,
  Bucket,
  ConfigField,
  ItemWithLinks,
  Person,
  SourceKind,
  SourceStatus,
  SyncLogEntry,
  Task,
} from '../types';

export const ADA_ID = 'person:ada';

export function makePeople(): Person[] {
  return [
    {
      id: ADA_ID,
      display_name: 'Ada Lovelace',
      email: 'ada@acme.dev',
      note: null,
      identities: [
        { id: 'pid:1', kind: 'slack', value: 'U9', label: 'ada.l' },
        { id: 'pid:2', kind: 'github', value: 'adal', label: null },
      ],
    },
    {
      id: 'person:grace',
      display_name: 'Grace Hopper',
      email: null,
      note: null,
      identities: [{ id: 'pid:3', kind: 'slack', value: 'U0AERGW78CX', label: null }],
    },
  ];
}

const minutesAgo = (mins: number) => new Date(Date.now() - mins * 60_000).toISOString();

export const PAYMENTS_TASK_ID = 'task:pay-1';
export const REFUND_TASK_ID = 'task:pay-2';
export const AUTH_TASK_ID = 'task:auth-1';

/** Ids from real sources carry colons and `~`, which every URL has to escape. */
export const BRANCH_ITEM_ID = 'branch:webapp:dev~auth-session-timeout';
export const SLACK_ITEM_ID = 'slack:C01:p1700000000';

export function makeTasks(): Task[] {
  return [
    {
      id: PAYMENTS_TASK_ID,
      title: 'Stripe webhook handling for invoice payments',
      description: null,
      bucket: 'Payments',
      status: 'open',
      priority: 50,
      tags: ['backend'],
      unread: true,
      origin: 'auto',
      archived: false,
      next_action: null,
      updated_at: minutesAgo(95),
      candidates: [],
      items: [
        {
          id: 'pr:acme/webapp:1201',
          source: 'pr',
          label: 'feat(payments): add Stripe webhook handler',
          url: 'https://github.com/acme/webapp/pull/1201',
          context: '#1201',
          occurred_at: minutesAgo(120),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [{ kind: 'github', value: 'ada', name: 'ada', role: 'author' }],
        },
        {
          id: 'slack:C01:p1699999999',
          source: 'slack',
          label: 'thread: webhook retries flaking on staging',
          url: 'https://acme.slack.com/archives/C01/p1',
          context: '#payments-eng, 6 replies',
          occurred_at: minutesAgo(95),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [],
        },
        {
          id: 'todo:todo.md:12',
          source: 'todo',
          label: 'Write tests for payments retry logic',
          url: null,
          context: null,
          occurred_at: minutesAgo(7200),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [],
        },
      ],
    },
    {
      id: REFUND_TASK_ID,
      title: 'Refund flow throws on partial captures',
      description: null,
      bucket: 'Payments',
      status: 'in_progress',
      priority: 50,
      tags: ['bug'],
      unread: false,
      origin: 'auto',
      archived: false,
      next_action: null,
      updated_at: minutesAgo(180),
      candidates: [],
      items: [
        {
          id: 'linear:PAY-88',
          source: 'linear',
          label: 'Refund flow throws on partial captures',
          url: 'https://linear.app/alan/issue/PAY-88',
          context: 'PAY-88',
          occurred_at: minutesAgo(180),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [],
        },
      ],
    },
    {
      id: AUTH_TASK_ID,
      title: 'Refresh token rotation on scope change',
      description: null,
      bucket: 'Auth',
      status: 'merged',
      priority: 50,
      tags: ['security'],
      unread: false,
      origin: 'manual',
      archived: false,
      next_action: null,
      updated_at: minutesAgo(1440),
      candidates: [],
      items: [
        {
          id: 'pr:acme/webapp:1188',
          source: 'pr',
          label: 'fix(auth): rotate refresh tokens on scope change',
          url: 'https://github.com/acme/webapp/pull/1188',
          context: '#1188',
          occurred_at: minutesAgo(1440),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [],
        },
        {
          id: BRANCH_ITEM_ID,
          source: 'branch',
          label: '[webapp] dev/auth-session-timeout',
          url: null,
          context: null,
          occurred_at: minutesAgo(1500),
          triaged: true,
          triage_reason: null,
          triaged_at: null,
          pr_status: null,
          pr_review_requested: false,
          emoji: {},
          people: [],
        },
      ],
    },
  ];
}

export function makeBuckets(): Bucket[] {
  return [
    { name: 'Payments', keywords: ['stripe', 'invoice'], position: 0, count: 2, archived: false },
    { name: 'Auth', keywords: ['token', 'sso'], position: 1, count: 1, archived: false },
  ];
}

export function makeCatchupItems(): ItemWithLinks[] {
  return [
    {
      id: SLACK_ITEM_ID,
      source: 'slack',
      label: 'thread: can someone look at the webhook retry storm?',
      url: 'https://acme.slack.com/archives/C01/p2',
      context: '#payments-eng, 4 replies',
      occurred_at: minutesAgo(20),
      triaged: false,
      triage_reason: null,
      triaged_at: null,
      pr_status: null,
      pr_review_requested: false,
      emoji: {},
      people: [],
      links: [
        {
          task: {
            id: PAYMENTS_TASK_ID,
            title: 'Stripe webhook handling for invoice payments',
            bucket: 'Payments',
          },
          state: 'proposed',
          engine: 'keyword',
          confidence: 0.72,
          reason: 'Shares the words "webhook" and "retry" with the task title',
        },
      ],
    },
    {
      id: BRANCH_ITEM_ID,
      source: 'branch',
      label: '[webapp] dev/auth-session-timeout',
      url: null,
      context: 'last commit 2h ago',
      occurred_at: minutesAgo(120),
      triaged: false,
      triage_reason: null,
      triaged_at: null,
      pr_status: null,
      pr_review_requested: false,
      emoji: {},
      people: [],
      links: [],
    },
  ];
}

const GITHUB_SETUP = 'Press Detect if you use the GitHub CLI, or create a personal access token.';
const GITHUB_SETUP_URL = 'https://github.com/settings/tokens/new';

export function makeSourceKinds(): SourceKind[] {
  return [
    {
      kind: 'github',
      name: 'GitHub',
      description: 'Your open pull requests and assigned issues',
      setup: GITHUB_SETUP,
      setup_url: GITHUB_SETUP_URL,
      manifest: '',
      manifest_hint: '',
      detectable: true,
      needs_credentials: true,
    },
    {
      kind: 'slack',
      name: 'Slack',
      description: 'Threads that name you',
      setup: 'Create an app, add the search:read user scope, copy the User OAuth Token.',
      setup_url: 'https://api.slack.com/apps',
      manifest:
        'display_information:\n  name: Personal HQ\noauth_config:\n  scopes:\n    user:\n      - search:read',
      manifest_hint: 'Slack \u2192 Create an app \u2192 From a manifest \u2192 paste this',
      detectable: false,
      needs_credentials: true,
    },
    {
      kind: 'todo',
      name: 'Todo list',
      description: 'Lines you have not ticked off yet',
      setup: 'No credentials — it reads a folder on this machine.',
      setup_url: '',
      manifest: '',
      manifest_hint: '',
      detectable: false,
      needs_credentials: false,
    },
  ];
}

/** Fields as the backend hands them over: a fresh source has nothing filled in. */
export function makeSourceFields(kind: string): ConfigField[] {
  if (kind === 'github') {
    return [
      {
        key: 'token',
        label: 'Personal access token',
        kind: 'secret',
        required: true,
        placeholder: 'ghp_…',
        help: 'Needs the `repo` scope.',
        help_url: GITHUB_SETUP_URL,
        value: null,
        is_set: false,
      },
      {
        key: 'username',
        label: 'Username',
        kind: 'text',
        required: true,
        placeholder: 'your-username',
        help: '',
        help_url: '',
        value: null,
        is_set: false,
      },
      {
        key: 'org',
        label: 'Organisation',
        kind: 'text',
        required: false,
        placeholder: 'acme',
        help: '',
        help_url: '',
        value: null,
        is_set: false,
      },
    ];
  }
  if (kind === 'slack') {
    return [
      {
        key: 'token',
        label: 'User token',
        kind: 'secret',
        required: true,
        placeholder: 'xoxp-…',
        help: '',
        help_url: '',
        value: null,
        is_set: false,
      },
    ];
  }
  return [
    {
      key: 'path',
      label: 'Folder',
      kind: 'text',
      required: true,
      placeholder: '~/todos',
      help: '',
      help_url: '',
      value: null,
      is_set: false,
    },
  ];
}

export function makeSources(): SourceStatus[] {
  const github = makeSourceFields('github');
  const slack = makeSourceFields('slack');
  slack[0] = { ...slack[0], value: '••••••••1234', is_set: true };

  return [
    {
      id: 'github-work-github',
      kind: 'github',
      name: 'Work GitHub',
      position: 1,
      description: 'Your open pull requests and assigned issues',
      status: 'unconfigured',
      detail: 'Not configured',
      last_checked_at: null,
      error: null,
      fields: github,
      setup: GITHUB_SETUP,
      setup_url: GITHUB_SETUP_URL,
      manifest: '',
      manifest_hint: '',
      detectable: true,
    },
    {
      id: 'slack-slack',
      kind: 'slack',
      name: 'Slack',
      position: 2,
      description: 'Threads that name you',
      status: 'connected',
      detail: '4 channels watched',
      last_checked_at: minutesAgo(4),
      error: null,
      fields: slack,
      setup: 'Create an app, add the search:read user scope, copy the User OAuth Token.',
      setup_url: 'https://api.slack.com/apps',
      manifest: 'display_information:\n  name: Personal HQ',
      manifest_hint: 'Slack \u2192 From a manifest \u2192 paste this',
      detectable: false,
    },
  ];
}

export function makeSyncLog(): SyncLogEntry[] {
  return [
    {
      id: 2,
      started_at: minutesAgo(6),
      finished_at: minutesAgo(6),
      sources: [
        { source: 'github', kind: 'github', items_fetched: 3, configured: true, error: null },
        { source: 'slack', kind: 'slack', items_fetched: 2, configured: true, error: null },
      ],
      items_fetched: 5,
      items_added: 2,
      items_updated: 1,
      proposals: 1,
      tasks_updated: 1,
      duration_seconds: 0.8,
      error: null,
    },
    {
      id: 1,
      started_at: minutesAgo(51),
      finished_at: minutesAgo(51),
      sources: [
        { source: 'linear', kind: 'linear', items_fetched: 0, configured: true, error: 'HTTP 401' },
      ],
      items_fetched: 0,
      items_added: 0,
      items_updated: 0,
      proposals: 0,
      tasks_updated: 0,
      duration_seconds: 0.2,
      error: 'Linear rejected the token',
    },
  ];
}

export function makeSettings(): AppSettings {
  return {
    app_name: 'Personal HQ',
    auto_sync: false,
    secret_backend: 'keyring',
    secret_backend_is_keychain: true,
  };
}

export function makeAIStatus(): AIStatus {
  return {
    available: false,
    source: 'none',
    detail: 'No credentials. Run `ant auth login`, or add an API key in Admin.',
    model: 'claude-opus-4-8',
  };
}
