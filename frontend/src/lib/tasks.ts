import { UNCATEGORIZED } from '../constants';
import { ageMs } from './time';
import type { Bucket, Item, Source, Task } from '../types';

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
 * leads the board when anything lands there — untriaged work is what you act on
 * first — and is absent otherwise, so an install with no buckets yields no columns.
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
    else columns.unshift({ name: UNCATEGORIZED, tasks: sortTasksByRecency(orphans, now) });
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

/** Slack items get their own section and lead the detail view. */
export function splitSlackItems(task: Task): { slack: Item[]; other: Item[] } {
  return {
    slack: task.items.filter((item) => item.source === 'slack'),
    other: task.items.filter((item) => item.source !== 'slack'),
  };
}

const CODE_SOURCES: Source[] = ['pr', 'branch'];

/** A code reference in the task's Code lane: a PR, a local branch, or the two joined when
 *  the branch is the one the PR was pushed from. At least one of the two is always set. */
export interface CodeUnit {
  pr: Item | null;
  branch: Item | null;
}

/** The task detail splits three ways: Slack leads the Activity lane, other non-code items
 *  follow it, and PRs and branches move to a Code lane — a PR joined to its local branch. */
export function splitTaskItems(task: Task): {
  slack: Item[];
  other: Item[];
  code: CodeUnit[];
} {
  const slack = task.items.filter((item) => item.source === 'slack');
  const other = task.items.filter(
    (item) => item.source !== 'slack' && !CODE_SOURCES.includes(item.source),
  );
  const prs = task.items.filter((item) => item.source === 'pr');
  const branches = task.items.filter((item) => item.source === 'branch');

  const joined = new Set<string>();
  const code: CodeUnit[] = prs.map((pr) => {
    const match = pr.head_branch
      ? branches.find((b) => !joined.has(b.id) && b.branch === pr.head_branch)
      : undefined;
    if (match) joined.add(match.id);
    return { pr, branch: match ?? null };
  });
  for (const branch of branches) {
    if (!joined.has(branch.id)) code.push({ pr: null, branch });
  }

  return { slack, other, code };
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

export function groupTasksByBucket(tasks: Task[]): { label: string; tasks: Task[] }[] {
  const byBucket = new Map<string, Task[]>();
  for (const task of tasks) {
    const bucket = task.bucket || UNCATEGORIZED;
    const list = byBucket.get(bucket) ?? [];
    list.push(task);
    byBucket.set(bucket, list);
  }
  // Alphabetical, with Uncategorized last so a fully-filed board reads cleanly.
  return [...byBucket.keys()]
    .sort((a, b) => (a === UNCATEGORIZED ? 1 : b === UNCATEGORIZED ? -1 : a.localeCompare(b)))
    .map((label) => ({ label, tasks: byBucket.get(label) ?? [] }));
}

export function countItems(tasks: Task[]): number {
  return tasks.reduce((total, task) => total + task.items.length, 0);
}

/** Task ids are `task:<hex>`; keep the colon out of the URL so it doesn't show as %3A. */
export function taskPath(taskId: string): string {
  return `/task/${taskId.replace(/^task:/, '')}`;
}

export function taskIdFromParam(param: string | undefined): string | undefined {
  if (!param) return undefined;
  return param.startsWith('task:') ? param : `task:${param}`;
}
