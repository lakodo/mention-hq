import type {
  AIStatus,
  AppSettings,
  Bucket,
  ItemWithLinks,
  SourceStatus,
  SyncLogEntry,
  Task,
} from '../types';

const minutesAgo = (mins: number) => new Date(Date.now() - mins * 60_000).toISOString();

export const PAYMENTS_TASK_ID = 'task:pay-1';
export const REFUND_TASK_ID = 'task:pay-2';
export const AUTH_TASK_ID = 'task:auth-1';

/** Ids from real sources carry colons and `~`, which every URL has to escape. */
export const BRANCH_ITEM_ID = 'branch:alan-apps:joris~auth-session-timeout';
export const SLACK_ITEM_ID = 'slack:C01:p1700000000';

export function makeTasks(): Task[] {
  return [
    {
      id: PAYMENTS_TASK_ID,
      title: 'Stripe webhook handling for invoice payments',
      bucket: 'Payments',
      status: 'open',
      tags: ['backend'],
      unread: true,
      origin: 'auto',
      updated_at: minutesAgo(95),
      items: [
        {
          id: 'pr:alan-eu/alan-apps:1201',
          source: 'pr',
          label: 'feat(payments): add Stripe webhook handler',
          url: 'https://github.com/alan-eu/alan-apps/pull/1201',
          context: '#1201',
          occurred_at: minutesAgo(120),
          triaged: true,
        },
        {
          id: 'slack:C01:p1699999999',
          source: 'slack',
          label: 'thread: webhook retries flaking on staging',
          url: 'https://alan.slack.com/archives/C01/p1',
          context: '#payments-eng, 6 replies',
          occurred_at: minutesAgo(95),
          triaged: true,
        },
        {
          id: 'todo:todo.md:12',
          source: 'todo',
          label: 'Write tests for payments retry logic',
          url: null,
          context: null,
          occurred_at: minutesAgo(7200),
          triaged: true,
        },
      ],
    },
    {
      id: REFUND_TASK_ID,
      title: 'Refund flow throws on partial captures',
      bucket: 'Payments',
      status: 'in_progress',
      tags: ['bug'],
      unread: false,
      origin: 'auto',
      updated_at: minutesAgo(180),
      items: [
        {
          id: 'linear:PAY-88',
          source: 'linear',
          label: 'Refund flow throws on partial captures',
          url: 'https://linear.app/alan/issue/PAY-88',
          context: 'PAY-88',
          occurred_at: minutesAgo(180),
          triaged: true,
        },
      ],
    },
    {
      id: AUTH_TASK_ID,
      title: 'Refresh token rotation on scope change',
      bucket: 'Auth',
      status: 'merged',
      tags: ['security'],
      unread: false,
      origin: 'manual',
      updated_at: minutesAgo(1440),
      items: [
        {
          id: 'pr:alan-eu/alan-apps:1188',
          source: 'pr',
          label: 'fix(auth): rotate refresh tokens on scope change',
          url: 'https://github.com/alan-eu/alan-apps/pull/1188',
          context: '#1188',
          occurred_at: minutesAgo(1440),
          triaged: true,
        },
        {
          id: BRANCH_ITEM_ID,
          source: 'branch',
          label: '[alan-apps] joris/auth-session-timeout',
          url: null,
          context: null,
          occurred_at: minutesAgo(1500),
          triaged: true,
        },
      ],
    },
  ];
}

export function makeBuckets(): Bucket[] {
  return [
    { name: 'Payments', keywords: ['stripe', 'invoice'], position: 0, count: 2 },
    { name: 'Auth', keywords: ['token', 'sso'], position: 1, count: 1 },
  ];
}

export function makeCatchupItems(): ItemWithLinks[] {
  return [
    {
      id: SLACK_ITEM_ID,
      source: 'slack',
      label: 'thread: can someone look at the webhook retry storm?',
      url: 'https://alan.slack.com/archives/C01/p2',
      context: '#payments-eng, 4 replies',
      occurred_at: minutesAgo(20),
      triaged: false,
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
      label: '[alan-apps] joris/auth-session-timeout',
      url: null,
      context: 'last commit 2h ago',
      occurred_at: minutesAgo(120),
      triaged: false,
      links: [],
    },
  ];
}

export function makeSources(): SourceStatus[] {
  return [
    {
      id: 'github',
      name: 'GitHub',
      description: 'Your open pull requests and assigned issues',
      status: 'unconfigured',
      detail: 'Not configured',
      last_checked_at: null,
      error: null,
      fields: [
        {
          key: 'token',
          label: 'Personal access token',
          kind: 'secret',
          required: true,
          placeholder: 'ghp_…',
          help: 'Needs the `repo` scope.',
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
          value: null,
          is_set: false,
        },
      ],
    },
    {
      id: 'slack',
      name: 'Slack',
      description: 'Threads that name you',
      status: 'connected',
      detail: '4 channels watched',
      last_checked_at: minutesAgo(4),
      error: null,
      fields: [
        {
          key: 'token',
          label: 'User token',
          kind: 'secret',
          required: true,
          placeholder: 'xoxp-…',
          help: '',
          value: '••••••••1234',
          is_set: true,
        },
      ],
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
        { source: 'github', items_fetched: 3, configured: true, error: null },
        { source: 'slack', items_fetched: 2, configured: true, error: null },
      ],
      items_fetched: 5,
      tasks_added: 2,
      tasks_updated: 1,
      duration_seconds: 0.8,
      error: null,
    },
    {
      id: 1,
      started_at: minutesAgo(51),
      finished_at: minutesAgo(51),
      sources: [{ source: 'linear', items_fetched: 0, configured: true, error: 'HTTP 401' }],
      items_fetched: 0,
      tasks_added: 0,
      tasks_updated: 0,
      duration_seconds: 0.2,
      error: 'Linear rejected the token',
    },
  ];
}

export function makeSettings(): AppSettings {
  return { app_name: 'Personal HQ', secret_backend: 'keyring', secret_backend_is_keychain: true };
}

export function makeAIStatus(): AIStatus {
  return {
    available: false,
    source: 'none',
    detail: 'No credentials. Run `ant auth login`, or add an API key in Admin.',
    model: 'claude-opus-4-8',
  };
}
