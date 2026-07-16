import { http, HttpResponse } from 'msw';
import {
  makeAIStatus,
  makeBuckets,
  makeCatchupItems,
  makeSettings,
  makeSources,
  makeSyncLog,
  makeTasks,
} from './fixtures';
import type {
  AIStatus,
  AppSettings,
  Bucket,
  ItemWithLinks,
  SourceStatus,
  SyncLogEntry,
  Task,
  TaskPatch,
} from '../types';

const BASE = 'http://localhost:8000';

interface Db {
  tasks: Task[];
  buckets: Bucket[];
  catchup: ItemWithLinks[];
  sources: SourceStatus[];
  syncLog: SyncLogEntry[];
  settings: AppSettings;
  ai: AIStatus;
}

export const db: Db = {
  tasks: [],
  buckets: [],
  catchup: [],
  sources: [],
  syncLog: [],
  settings: makeSettings(),
  ai: makeAIStatus(),
};

export function resetDb(): void {
  db.tasks = makeTasks();
  db.buckets = makeBuckets();
  db.catchup = makeCatchupItems();
  db.sources = makeSources();
  db.syncLog = makeSyncLog();
  db.settings = makeSettings();
  db.ai = makeAIStatus();
}

const notFound = (detail: string) => HttpResponse.json({ detail }, { status: 404 });

export const handlers = [
  http.get(`${BASE}/tasks`, ({ request }) => {
    const url = new URL(request.url);
    const bucket = url.searchParams.get('bucket');
    const status = url.searchParams.get('status');
    const unread = url.searchParams.get('unread');
    const q = url.searchParams.get('q');

    let tasks = db.tasks;
    if (bucket) tasks = tasks.filter((t) => t.bucket === bucket);
    if (status) tasks = tasks.filter((t) => t.status === status);
    if (unread !== null) tasks = tasks.filter((t) => String(t.unread) === unread);
    if (q) tasks = tasks.filter((t) => t.title.toLowerCase().includes(q.toLowerCase()));
    return HttpResponse.json(tasks);
  }),

  http.get(`${BASE}/tasks/:id`, ({ params }) => {
    const task = db.tasks.find((t) => t.id === params.id);
    return task ? HttpResponse.json(task) : notFound(`Task not found: ${String(params.id)}`);
  }),

  http.post(`${BASE}/tasks`, async ({ request }) => {
    const body = (await request.json()) as { title: string; bucket?: string; tags?: string[] };
    const task: Task = {
      id: `task:${Math.random().toString(16).slice(2, 10)}`,
      title: body.title,
      bucket: body.bucket ?? 'Uncategorized',
      status: 'open',
      tags: body.tags ?? [],
      unread: false,
      origin: 'manual',
      updated_at: new Date().toISOString(),
      items: [],
    };
    db.tasks.push(task);
    return HttpResponse.json(task, { status: 201 });
  }),

  http.patch(`${BASE}/tasks/:id`, async ({ params, request }) => {
    const task = db.tasks.find((t) => t.id === params.id);
    if (!task) return notFound(`Task not found: ${String(params.id)}`);
    const patch = (await request.json()) as TaskPatch;
    Object.assign(task, patch);
    return HttpResponse.json(task);
  }),

  http.delete(`${BASE}/tasks/:id`, ({ params }) => {
    const task = db.tasks.find((t) => t.id === params.id);
    if (!task) return notFound(`Task not found: ${String(params.id)}`);
    if (task.origin === 'auto') {
      return HttpResponse.json({ detail: 'Auto tasks cannot be deleted' }, { status: 400 });
    }
    db.tasks = db.tasks.filter((t) => t.id !== params.id);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(`${BASE}/buckets`, () => HttpResponse.json(db.buckets)),

  http.post(`${BASE}/buckets`, async ({ request }) => {
    const body = (await request.json()) as { name: string; keywords: string[]; position?: number };
    if (body.name === 'Uncategorized') {
      return HttpResponse.json({ detail: 'Uncategorized is reserved' }, { status: 400 });
    }
    if (db.buckets.some((b) => b.name === body.name)) {
      return HttpResponse.json({ detail: `Bucket already exists: ${body.name}` }, { status: 409 });
    }
    const bucket: Bucket = {
      name: body.name,
      keywords: body.keywords,
      position: body.position ?? db.buckets.length,
      count: 0,
    };
    db.buckets.push(bucket);
    return HttpResponse.json(bucket, { status: 201 });
  }),

  http.patch(`${BASE}/buckets/:name`, async ({ params, request }) => {
    const bucket = db.buckets.find((b) => b.name === params.name);
    if (!bucket) return notFound(`Bucket not found: ${String(params.name)}`);
    const patch = (await request.json()) as { keywords?: string[]; position?: number };
    if (patch.keywords) bucket.keywords = patch.keywords;
    if (patch.position !== undefined) bucket.position = patch.position;
    return HttpResponse.json(bucket);
  }),

  http.delete(`${BASE}/buckets/:name`, ({ params }) => {
    const bucket = db.buckets.find((b) => b.name === params.name);
    if (!bucket) return notFound(`Bucket not found: ${String(params.name)}`);
    db.buckets = db.buckets.filter((b) => b.name !== params.name);
    for (const task of db.tasks) {
      if (task.bucket === params.name) task.bucket = 'Uncategorized';
    }
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${BASE}/buckets/reassign`, () => HttpResponse.json(db.buckets)),

  http.post(`${BASE}/buckets/suggest/:taskId`, ({ params }) => {
    const task = db.tasks.find((t) => t.id === params.taskId);
    if (!task) return notFound(`Task not found: ${String(params.taskId)}`);
    return HttpResponse.json({
      bucket: 'Billing',
      is_new: true,
      keywords: ['stripe', 'refund'],
      confidence: 0.83,
      reasoning: 'The task is about payment webhooks, which is billing work.',
    });
  }),

  http.get(`${BASE}/catchup`, () => HttpResponse.json(db.catchup.filter((item) => !item.triaged))),

  http.post(`${BASE}/catchup/:itemId/confirm`, async ({ params, request }) => {
    const item = db.catchup.find((i) => i.id === params.itemId);
    if (!item) return notFound(`Item not found: ${String(params.itemId)}`);
    const { task_ids: taskIds } = (await request.json()) as { task_ids: string[] };

    for (const taskId of taskIds) {
      const task = db.tasks.find((t) => t.id === taskId);
      if (!task) return notFound(`Task not found: ${taskId}`);
      const existing = item.links.find((l) => l.task.id === taskId);
      if (existing) existing.state = 'confirmed';
      else {
        item.links.push({
          task: { id: task.id, title: task.title, bucket: task.bucket },
          state: 'confirmed',
          engine: null,
          confidence: 1,
          reason: 'You said so',
        });
      }
    }
    item.triaged = true;
    return HttpResponse.json(item);
  }),

  http.post(`${BASE}/catchup/:itemId/reject/:taskId`, ({ params }) => {
    const item = db.catchup.find((i) => i.id === params.itemId);
    if (!item) return notFound(`Item not found: ${String(params.itemId)}`);
    const link = item.links.find((l) => l.task.id === params.taskId);
    if (link) link.state = 'rejected';
    return HttpResponse.json(item);
  }),

  http.post(`${BASE}/catchup/:itemId/new-task`, async ({ params, request }) => {
    const item = db.catchup.find((i) => i.id === params.itemId);
    if (!item) return notFound(`Item not found: ${String(params.itemId)}`);
    const body = (await request.json()) as { title: string; bucket?: string };
    const task: Task = {
      id: `task:${Math.random().toString(16).slice(2, 10)}`,
      title: body.title || item.label,
      bucket: body.bucket ?? 'Uncategorized',
      status: 'open',
      tags: [],
      unread: false,
      origin: 'manual',
      updated_at: item.occurred_at,
      items: [item],
    };
    db.tasks.push(task);
    item.triaged = true;
    return HttpResponse.json(task);
  }),

  http.post(`${BASE}/catchup/:itemId/triage`, async ({ params, request }) => {
    const item = db.catchup.find((i) => i.id === params.itemId);
    if (!item) return notFound(`Item not found: ${String(params.itemId)}`);
    const { triaged } = (await request.json()) as { triaged: boolean };
    item.triaged = triaged;
    return HttpResponse.json(item);
  }),

  http.post(`${BASE}/sync`, () => {
    db.syncLog.unshift({
      id: db.syncLog.length + 1,
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      sources: [{ source: 'github', items_fetched: 1, configured: true, error: null }],
      items_fetched: 1,
      tasks_added: 1,
      tasks_updated: 0,
      duration_seconds: 0.4,
      error: null,
    });
    return HttpResponse.json({
      sources_synced: ['github', 'slack'],
      tasks_added: 1,
      tasks_updated: 0,
      duration_seconds: 0.4,
      errors: [],
    });
  }),

  http.get(`${BASE}/sync/status`, () => HttpResponse.json(db.syncLog)),

  http.get(`${BASE}/admin/settings`, () => HttpResponse.json(db.settings)),

  http.patch(`${BASE}/admin/settings`, async ({ request }) => {
    const body = (await request.json()) as { app_name: string };
    db.settings = { ...db.settings, app_name: body.app_name };
    return HttpResponse.json(db.settings);
  }),

  http.get(`${BASE}/admin/sources`, () => HttpResponse.json(db.sources)),

  http.post(`${BASE}/admin/sources/:id/test`, ({ params }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`Source not found: ${String(params.id)}`);
    source.last_checked_at = new Date().toISOString();
    return HttpResponse.json(source);
  }),

  http.put(`${BASE}/admin/sources/:id/config`, async ({ params, request }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`Source not found: ${String(params.id)}`);
    const { values } = (await request.json()) as { values: Record<string, string> };

    for (const field of source.fields) {
      const next = values[field.key];
      if (next === undefined) continue;
      if (next === '') {
        field.value = null;
        field.is_set = false;
      } else {
        field.is_set = true;
        field.value = field.kind === 'secret' ? `••••••••${next.slice(-4)}` : next;
      }
    }
    source.status = source.fields.every((f) => !f.required || f.is_set)
      ? 'connected'
      : 'unconfigured';
    source.detail = source.status === 'connected' ? 'Configured' : 'Not configured';
    return HttpResponse.json(source);
  }),

  http.delete(`${BASE}/admin/sources/:id/config`, ({ params }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`Source not found: ${String(params.id)}`);
    for (const field of source.fields) {
      field.value = null;
      field.is_set = false;
    }
    source.status = 'unconfigured';
    source.detail = 'Not configured';
    return HttpResponse.json(source);
  }),

  http.get(`${BASE}/admin/ai`, () => HttpResponse.json(db.ai)),

  http.put(`${BASE}/admin/ai/key`, async ({ request }) => {
    const { api_key: apiKey } = (await request.json()) as { api_key: string };
    db.ai = apiKey
      ? {
          available: true,
          source: 'keychain',
          detail: 'Using the API key stored in your keychain.',
          model: db.ai.model,
        }
      : makeAIStatus();
    return HttpResponse.json(db.ai);
  }),
];
