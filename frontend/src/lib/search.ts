import { sourceMeta } from '../constants';
import type { ItemWithLinks, Task } from '../types';

/**
 * The query is lowercased and split on whitespace; EVERY part must match.
 * Supported prefixes:
 *   - `bucket:<x>` -> the task's bucket contains x
 *   - `tag:<x>`    -> a tag contains x, OR one of its items' source labels contains x
 *   - bare word    -> title, bucket, or any item label contains it
 */
export function matchesQuery(task: Task, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;

  return q.split(/\s+/).every((part) => {
    if (part.startsWith('bucket:')) {
      return task.bucket.toLowerCase().includes(part.slice('bucket:'.length));
    }

    if (part.startsWith('tag:')) {
      const t = part.slice('tag:'.length);
      return (
        task.tags.some((tag) => tag.toLowerCase().includes(t)) ||
        task.items.some((item) => sourceMeta(item.source).label.toLowerCase().includes(t))
      );
    }

    return (
      task.title.toLowerCase().includes(part) ||
      task.bucket.toLowerCase().includes(part) ||
      task.items.some((item) => item.label.toLowerCase().includes(part))
    );
  });
}

export function filterTasks(tasks: Task[], query: string): Task[] {
  return tasks.filter((task) => matchesQuery(task, query));
}

/** Simpler substring match over title + bucket, used by the detail sidebar. */
export function matchesSidebarQuery(task: Task, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return task.title.toLowerCase().includes(q) || task.bucket.toLowerCase().includes(q);
}

/**
 * The catch-up equivalent of {@link matchesQuery}, over an untriaged item rather than a task.
 *   - `bucket:<x>` -> a task this item is proposed for has a bucket containing x
 *   - `tag:<x>`    -> the item's source label contains x (items carry no tags)
 *   - bare word    -> the item's label, context or source, or a proposed task's title/bucket
 */
export function matchesItemQuery(item: ItemWithLinks, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;

  const sourceLabel = sourceMeta(item.source).label.toLowerCase();
  const context = item.context?.toLowerCase() ?? '';

  return q.split(/\s+/).every((part) => {
    if (part.startsWith('bucket:')) {
      const b = part.slice('bucket:'.length);
      return item.links.some((link) => link.task.bucket.toLowerCase().includes(b));
    }

    if (part.startsWith('tag:')) {
      return sourceLabel.includes(part.slice('tag:'.length));
    }

    return (
      item.label.toLowerCase().includes(part) ||
      context.includes(part) ||
      sourceLabel.includes(part) ||
      item.links.some(
        (link) =>
          link.task.title.toLowerCase().includes(part) ||
          link.task.bucket.toLowerCase().includes(part),
      )
    );
  });
}

export function filterItems(items: ItemWithLinks[], query: string): ItemWithLinks[] {
  return items.filter((item) => matchesItemQuery(item, query));
}
