import { describe, expect, it } from 'vitest';
import { filterTasks, matchesQuery, matchesSidebarQuery } from './search';
import { makeTasks } from '../test/fixtures';
import type { Task } from '../types';

const tasks = makeTasks();
const [stripe, refund, auth] = tasks;

describe('matchesQuery', () => {
  it('matches everything when the query is blank', () => {
    expect(matchesQuery(stripe, '')).toBe(true);
    expect(matchesQuery(stripe, '   ')).toBe(true);
  });

  it('matches on the task title, case-insensitively', () => {
    expect(matchesQuery(stripe, 'STRIPE')).toBe(true);
    expect(matchesQuery(refund, 'stripe')).toBe(false);
  });

  it('matches on an item label, so a task is findable by what it holds', () => {
    expect(matchesQuery(auth, 'session-timeout')).toBe(true);
  });

  it('matches on the bucket name', () => {
    expect(matchesQuery(auth, 'auth')).toBe(true);
  });

  it('restricts `bucket:` to the bucket, not the title', () => {
    expect(matchesQuery(stripe, 'bucket:payments')).toBe(true);
    expect(matchesQuery(auth, 'bucket:payments')).toBe(false);
    // "Stripe" is in the title but never in a bucket name.
    expect(matchesQuery(stripe, 'bucket:stripe')).toBe(false);
  });

  it('matches `tag:` against tags and against source labels', () => {
    expect(matchesQuery(stripe, 'tag:backend')).toBe(true);
    expect(matchesQuery(stripe, 'tag:bug')).toBe(false);
    expect(matchesQuery(stripe, 'tag:slack')).toBe(true);
    expect(matchesQuery(refund, 'tag:slack')).toBe(false);
  });

  it('ANDs every whitespace-separated part', () => {
    expect(matchesQuery(stripe, 'bucket:payments tag:backend')).toBe(true);
    expect(matchesQuery(stripe, 'bucket:payments tag:security')).toBe(false);
  });

  it('never mistakes a prefix for a bare word', () => {
    expect(matchesQuery(refund, 'bucket:auth')).toBe(false);
  });
});

describe('filterTasks', () => {
  it('keeps only the matching tasks', () => {
    const result = filterTasks(tasks, 'bucket:payments');
    expect(result.map((t: Task) => t.id)).toEqual([stripe.id, refund.id]);
  });

  it('returns every task for a blank query', () => {
    expect(filterTasks(tasks, '')).toHaveLength(3);
  });
});

describe('matchesSidebarQuery', () => {
  it('matches title or bucket only', () => {
    expect(matchesSidebarQuery(stripe, 'stripe')).toBe(true);
    expect(matchesSidebarQuery(stripe, 'payments')).toBe(true);
    // Item labels are out of scope for the sidebar's simpler search.
    expect(matchesSidebarQuery(auth, 'session-timeout')).toBe(false);
  });
});
