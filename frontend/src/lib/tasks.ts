import { UNCATEGORIZED } from '../constants';
import { ageMs } from './time';
import type { Bucket, Item, ItemRow, Source, Task } from '../types';

export interface BucketColumn {
  name: string;
  count: number;
  tasks: Task[];
}

/** The age a task is sorted by: its most recent item, falling back to updated_at. */
export function taskRecency(task: Task, now: number = Date.now()): number {
  if (task.items.length === 0) return ageMs(task.updated_at, now);
  return Math.min(...task.items.map((item) => ageMs(item.occurred_at, now)));
}

export function sortTasksByRecency(tasks: Task[], now: number = Date.now()): Task[] {
  return [...tasks].sort((a, b) => taskRecency(a, now) - taskRecency(b, now));
}

/**
 * Build the board's columns from the buckets the API reports, ordered by position.
 * A task whose bucket has no column of its own is folded into Uncategorized, which
 * is appended only when something actually lands there — so nothing disappears from
 * the board, and an install with no buckets yields no columns.
 */
export function groupByBucket(
  tasks: Task[],
  buckets: Bucket[],
  now: number = Date.now(),
): BucketColumn[] {
  const ordered = [...buckets].sort(
    (a, b) => a.position - b.position || a.name.localeCompare(b.name),
  );
  const byBucket = new Map<string, Task[]>(ordered.map((b) => [b.name, []]));
  const orphans: Task[] = [];

  for (const task of tasks) {
    const column = byBucket.get(task.bucket);
    if (column) column.push(task);
    else orphans.push(task);
  }

  const columns = ordered.map((bucket) => ({
    name: bucket.name,
    tasks: sortTasksByRecency(byBucket.get(bucket.name) ?? [], now),
  }));

  if (orphans.length) {
    const existing = columns.find((c) => c.name === UNCATEGORIZED);
    if (existing) existing.tasks = sortTasksByRecency([...existing.tasks, ...orphans], now);
    else columns.push({ name: UNCATEGORIZED, tasks: sortTasksByRecency(orphans, now) });
  }

  return columns.map((c) => ({ ...c, count: c.tasks.length }));
}

/** ISO timestamp of the task's most recent item, falling back to updated_at. */
export function newestItemAt(task: Task, now: number = Date.now()): string {
  if (task.items.length === 0) return task.updated_at;
  return task.items.reduce((newest, item) =>
    ageMs(item.occurred_at, now) < ageMs(newest.occurred_at, now) ? item : newest,
  ).occurred_at;
}

/** Unique sources across a task's items, in first-seen order (for the overlapping dots). */
export function uniqueSources(task: Task): Source[] {
  return [...new Set(task.items.map((item) => item.source))];
}

export function itemCountLabel(task: Task): string {
  const n = task.items.length;
  return `${n} item${n === 1 ? '' : 's'}`;
}

/**
 * Flatten every item of every task into one chronological feed, most recent
 * first. A task with 3 items yields 3 rows.
 */
export function flattenItems(tasks: Task[], now: number = Date.now()): ItemRow[] {
  const rows: ItemRow[] = tasks.flatMap((task) =>
    task.items.map((item) => ({ key: `${task.id}:${item.id}`, task, item })),
  );
  return rows.sort((a, b) => ageMs(a.item.occurred_at, now) - ageMs(b.item.occurred_at, now));
}

/** Slack items get their own section and lead the detail view. */
export function splitSlackItems(task: Task): { slack: Item[]; other: Item[] } {
  return {
    slack: task.items.filter((item) => item.source === 'slack'),
    other: task.items.filter((item) => item.source !== 'slack'),
  };
}

/** The dot colour source for a sidebar row: Slack if present, else the first item. */
export function primarySource(task: Task): Source | null {
  const slack = task.items.find((item) => item.source === 'slack');
  if (slack) return slack.source;
  return task.items[0]?.source ?? null;
}

export interface TagGroup {
  tag: string;
  tasks: Task[];
}

/** Group tasks by tag for the sidebar; untagged tasks collect under "untagged". */
export function groupByTag(tasks: Task[]): TagGroup[] {
  const byTag = new Map<string, Task[]>();
  for (const task of tasks) {
    const tags = task.tags.length ? task.tags : ['untagged'];
    for (const tag of tags) {
      const list = byTag.get(tag) ?? [];
      list.push(task);
      byTag.set(tag, list);
    }
  }
  return [...byTag.keys()].sort().map((tag) => ({ tag, tasks: byTag.get(tag) ?? [] }));
}

export function countItems(tasks: Task[]): number {
  return tasks.reduce((total, task) => total + task.items.length, 0);
}
