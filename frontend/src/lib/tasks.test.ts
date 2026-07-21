import { describe, expect, it } from 'vitest';
import {
  groupByBucket,
  groupByTag,
  groupTasksByBucket,
  itemCountLabel,
  primarySource,
  splitSlackItems,
  splitTaskItems,
  taskCode,
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
  it('keeps Slack and non-code items in the Activity lane, PRs and branches out', () => {
    const { slack, other } = splitTaskItems(stripe);
    expect(slack.map((i) => i.source)).toEqual(['slack']);
    // The PR moved to the Code lane; only the non-code item is left in Activity.
    expect(other.map((i) => i.source)).toEqual(['todo']);
  });
});

describe('taskCode', () => {
  it('puts a lone PR with no branch on its own, and lists no branches', () => {
    const { branches, stacks, lonePrs } = taskCode(stripe);
    expect(branches).toHaveLength(0);
    expect(stacks).toHaveLength(0);
    expect(lonePrs.map((p) => p.id)).toEqual(['pr:acme/webapp:1201']);
  });

  it('gathers every branch into one tree, base first', () => {
    const { branches } = taskCode(auth);
    expect(branches.map((r) => [r.item.branch, r.depth])).toEqual([
      ['dev/auth-base', 0],
      ['dev/auth-session-timeout', 1],
    ]);
  });

  it('groups a stack of PRs into one tree, ordered base to top', () => {
    const { stacks, lonePrs } = taskCode(auth);
    expect(lonePrs).toHaveLength(0);
    expect(stacks).toHaveLength(1);
    expect(stacks[0].rows.map((r) => [r.item.id, r.depth])).toEqual([
      ['pr:acme/webapp:1187', 0],
      ['pr:acme/webapp:1188', 1],
    ]);
  });

  it('treats a PR whose branch is a lone one as a lone PR, not a stack', () => {
    const soloBranch: Task = {
      ...auth,
      items: auth.items.filter(
        (i) => i.branch !== 'dev/auth-base' && i.head_branch !== 'dev/auth-base',
      ),
    };
    const { stacks, lonePrs } = taskCode(soloBranch);
    expect(stacks).toHaveLength(0);
    expect(lonePrs.map((p) => p.id)).toEqual(['pr:acme/webapp:1188']);
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
