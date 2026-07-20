import { describe, expect, it } from 'vitest';
import {
  groupByBucket,
  groupByTag,
  groupTasksByBucket,
  itemCountLabel,
  primarySource,
  splitSlackItems,
  splitTaskItems,
  taskIdFromParam,
  taskPath,
  uniqueSources,
} from './tasks';
import { makeBuckets, makeTasks } from '../test/fixtures';
import type { Bucket, Task } from '../types';

const tasks = makeTasks();
const buckets = makeBuckets();
const [stripe, refund, auth] = tasks;

describe('groupByBucket', () => {
  it('builds one column per bucket, ordered by position', () => {
    const columns = groupByBucket(tasks, buckets);
    expect(columns.map((c) => c.name)).toEqual(['Payments', 'Auth']);
  });

  it('orders columns by position rather than by array order', () => {
    const reordered: Bucket[] = [
      { name: 'Auth', keywords: [], position: 0, count: 1, archived: false },
      { name: 'Payments', keywords: [], position: 1, count: 2, archived: false },
    ];
    expect(groupByBucket(tasks, reordered).map((c) => c.name)).toEqual(['Auth', 'Payments']);
  });

  it('files each task under its own bucket and counts it', () => {
    const columns = groupByBucket(tasks, buckets);
    const payments = columns.find((c) => c.name === 'Payments');
    expect(payments?.count).toBe(2);
    expect(payments?.tasks.map((t) => t.id)).toEqual([stripe.id, refund.id]);
    expect(columns.find((c) => c.name === 'Auth')?.count).toBe(1);
  });

  it('yields no columns at all on a fresh install with no buckets', () => {
    expect(groupByBucket([], [])).toEqual([]);
  });

  it('keeps empty columns so the board still shows the bucket', () => {
    const columns = groupByBucket([], buckets);
    expect(columns).toHaveLength(2);
    expect(columns.every((c) => c.count === 0)).toBe(true);
  });

  it('folds a task whose bucket has no column into Uncategorized', () => {
    const orphan: Task = { ...auth, id: 'task:orphan', bucket: 'Ghost' };
    const columns = groupByBucket([...tasks, orphan], buckets);
    const uncategorized = columns.find((c) => c.name === 'Uncategorized');
    expect(uncategorized?.tasks.map((t) => t.id)).toEqual(['task:orphan']);
  });

  it('leads with Uncategorized so untriaged work is what you see first', () => {
    const orphan: Task = { ...auth, id: 'task:orphan', bucket: 'Ghost' };
    const columns = groupByBucket([...tasks, orphan], buckets);
    expect(columns.map((c) => c.name)).toEqual(['Uncategorized', 'Payments', 'Auth']);
  });

  it('does not invent an Uncategorized column when nothing lands there', () => {
    expect(groupByBucket(tasks, buckets).some((c) => c.name === 'Uncategorized')).toBe(false);
  });

  it('sorts tasks in a column by their most recent item', () => {
    const columns = groupByBucket(tasks, buckets);
    // The Stripe task's newest item is 95m old; the refund task's is 180m.
    expect(columns[0].tasks[0].id).toBe(stripe.id);
  });
});

describe('uniqueSources', () => {
  it('de-duplicates sources, preserving first-seen order', () => {
    expect(uniqueSources(stripe)).toEqual(['pr', 'slack', 'todo']);
  });
});

describe('itemCountLabel', () => {
  it('singularises one item', () => {
    expect(itemCountLabel(refund)).toBe('1 item');
    expect(itemCountLabel(stripe)).toBe('3 items');
  });
});

describe('splitSlackItems', () => {
  it('lifts Slack out so it can lead the detail view', () => {
    const { slack, other } = splitSlackItems(stripe);
    expect(slack.map((i) => i.source)).toEqual(['slack']);
    expect(other.map((i) => i.source)).toEqual(['pr', 'todo']);
  });
});

describe('splitTaskItems', () => {
  it('keeps Slack and non-code items in the Activity lane, PRs and branches in Code', () => {
    const { slack, other, code } = splitTaskItems(stripe);
    expect(slack.map((i) => i.source)).toEqual(['slack']);
    // The PR moved to the Code lane; only the non-code item is left in Activity.
    expect(other.map((i) => i.source)).toEqual(['todo']);
    expect(code).toHaveLength(1);
    expect(code[0].pr?.source).toBe('pr');
    expect(code[0].branch).toBeNull();
  });

  it('joins a branch to the PR whose head branch it is', () => {
    const { code } = splitTaskItems(auth);
    expect(code).toHaveLength(1);
    expect(code[0].pr?.id).toBe('pr:acme/webapp:1188');
    expect(code[0].branch?.branch).toBe('dev/auth-session-timeout');
  });

  it('leaves a branch with no matching PR standing on its own', () => {
    const orphanBranch: Task = {
      ...auth,
      items: [{ ...auth.items[1], head_branch: null }],
    };
    const { code } = splitTaskItems(orphanBranch);
    expect(code).toHaveLength(1);
    expect(code[0].pr).toBeNull();
    expect(code[0].branch?.branch).toBe('dev/auth-session-timeout');
  });
});

describe('primarySource', () => {
  it('prefers Slack when the task has any', () => {
    expect(primarySource(stripe)).toBe('slack');
  });

  it('falls back to the first item otherwise', () => {
    expect(primarySource(auth)).toBe('pr');
  });

  it('returns null when a task holds no items', () => {
    expect(primarySource({ ...auth, items: [] })).toBeNull();
  });
});

describe('groupByTag', () => {
  it('groups by tag, alphabetically', () => {
    expect(groupByTag(tasks).map((g) => g.tag)).toEqual(['backend', 'bug', 'security']);
  });

  it('collects untagged tasks under "untagged"', () => {
    const groups = groupByTag([{ ...stripe, tags: [] }]);
    expect(groups.map((g) => g.tag)).toEqual(['untagged']);
  });

  it('lists a task under each of its tags', () => {
    const groups = groupByTag([{ ...stripe, tags: ['a', 'b'] }]);
    expect(groups.map((g) => g.tag)).toEqual(['a', 'b']);
    expect(groups.every((g) => g.tasks.length === 1)).toBe(true);
  });
});

describe('groupTasksByBucket', () => {
  it('groups by bucket, alphabetically, Uncategorized last', () => {
    const orphan = { ...auth, id: 'task:orphan', bucket: 'Uncategorized' };
    const groups = groupTasksByBucket([...tasks, orphan]);
    expect(groups.map((g) => g.label)).toEqual(['Auth', 'Payments', 'Uncategorized']);
    expect(groups.find((g) => g.label === 'Payments')?.tasks.map((t) => t.id)).toEqual([
      stripe.id,
      refund.id,
    ]);
  });
});

describe('task url helpers', () => {
  it('keeps the colon out of the path and reads it back', () => {
    expect(taskPath('task:c71aa901e22d')).toBe('/task/c71aa901e22d');
    expect(taskIdFromParam('c71aa901e22d')).toBe('task:c71aa901e22d');
    // Idempotent when the param already carries the prefix (older links).
    expect(taskIdFromParam('task:c71aa901e22d')).toBe('task:c71aa901e22d');
    expect(taskIdFromParam(undefined)).toBeUndefined();
  });
});
