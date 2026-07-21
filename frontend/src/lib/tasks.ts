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

/** The Activity lane: Slack leads, the rest of the non-code items follow. PRs and branches
 *  are pulled out into their own Code lane by `taskCode`. */
export function splitTaskItems(task: Task): { slack: Item[]; other: Item[] } {
  return {
    slack: task.items.filter((item) => item.source === 'slack'),
    other: task.items.filter(
      (item) => item.source !== 'slack' && !CODE_SOURCES.includes(item.source),
    ),
  };
}

/** A branch or PR at a depth in its git-spice stack — 0 is the base, deeper sits on top. */
export interface StackRow<T> {
  item: T;
  depth: number;
}
export interface PrStack {
  chain: string[];
  rows: StackRow<Item>[];
}
/** The Code lane, arranged like a git-spice stack rather than a flat list: every local branch
 *  in one tree, each PR stack as its own tree, and standalone PRs on their own. */
export interface TaskCode {
  branches: StackRow<Item>[];
  stacks: PrStack[];
  lonePrs: Item[];
}

/** A branch's git-spice stack base — the bottom of its chain, which every branch in the same
 *  stack shares. Null for a branch git-spice doesn't track. */
function stackBase(branch: Item): string | null {
  return branch.stack.length > 0 ? branch.stack[0] : null;
}

function groupBy<T>(items: T[], key: (item: T) => string): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    const bucket = groups.get(k);
    if (bucket) bucket.push(item);
    else groups.set(k, [item]);
  }
  return groups;
}

export function taskCode(task: Task): TaskCode {
  const branches = task.items.filter((item) => item.source === 'branch');
  const prs = task.items.filter((item) => item.source === 'pr');

  // Branches sharing a stack base belong to one stack; a branch git-spice doesn't track stands
  // alone. The full order is the longest chain in the group (the top branch carries the rest).
  const branchGroups = groupBy(branches, (b) => stackBase(b) ?? `loose:${b.id}`);
  const chains = new Map<string, string[]>();
  for (const [key, group] of branchGroups) {
    let chain: string[] = [];
    for (const b of group) if (b.stack.length > chain.length) chain = b.stack;
    chains.set(key, chain.length ? chain : group.map((b) => b.branch ?? b.id));
  }

  const branchRows: StackRow<Item>[] = [];
  for (const [key, group] of branchGroups) {
    const order = chains.get(key)!;
    const byName = new Map(group.map((b) => [b.branch, b]));
    let depth = 0;
    for (const name of order) {
      const branch = byName.get(name);
      if (branch) branchRows.push({ item: branch, depth: depth++ });
    }
    for (const b of group)
      if (!order.includes(b.branch ?? '')) branchRows.push({ item: b, depth: depth++ });
  }

  // A PR belongs to the stack of the branch it was pushed from. Two or more PRs in the same
  // stack make a tree; a PR alone (or one whose branch isn't a tracked stack) is on its own.
  const branchByName = new Map(branches.map((b) => [b.branch, b]));
  const prGroups = groupBy(prs, (pr) => {
    const branch = pr.head_branch ? branchByName.get(pr.head_branch) : undefined;
    return branch ? (stackBase(branch) ?? `loose:${branch.id}`) : `lone:${pr.id}`;
  });

  const stacks: PrStack[] = [];
  const lonePrs: Item[] = [];
  for (const [key, group] of prGroups) {
    const chain = chains.get(key);
    if (group.length >= 2 && chain) {
      const rows = group
        .map((pr) => ({ pr, at: chain.indexOf(pr.head_branch ?? '') }))
        .sort((a, b) => a.at - b.at)
        .map(({ pr }, depth) => ({ item: pr, depth }));
      stacks.push({ chain, rows });
    } else {
      lonePrs.push(...group);
    }
  }

  return { branches: branchRows, stacks, lonePrs };
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
