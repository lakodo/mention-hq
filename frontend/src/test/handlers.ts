import { http, HttpResponse } from 'msw';
import {
  makeAIStatus,
  makeBuckets,
  makeCatchupItems,
  makePeople,
  makeSettings,
  makeSourceFields,
  makeSourceKinds,
  makeSources,
  makeSyncLog,
  makeTasks,
} from './fixtures';
import type {
  AIStatus,
  AppSettings,
  Bucket,
  Detection,
  ItemWithLinks,
  Link,
  Person,
  SourceKind,
  TriageRule,
  SourceStatus,
  SyncLogEntry,
  Task,
  TaskPatch,
} from '../types';

const BASE = 'http://localhost:8000/api';

interface Db {
  tasks: Task[];
  buckets: Bucket[];
  catchup: ItemWithLinks[];
  people: Person[];
  triageRules: TriageRule[];
  sources: SourceStatus[];
  sourceKinds: SourceKind[];
  /** What a local CLI would answer, per kind. A test overwrites it to steer detection. */
  detections: Record<string, Detection>;
  syncLog: SyncLogEntry[];
  settings: AppSettings;
  ai: AIStatus;
}

export const db: Db = {
  tasks: [],
  buckets: [],
  catchup: [],
  people: [],
  triageRules: [],
  sources: [],
  sourceKinds: [],
  detections: {},
  syncLog: [],
  settings: makeSettings(),
  ai: makeAIStatus(),
};

/** Mirrors the backend's `new_instance_id`: config is keyed by it, so it must match. */
function instanceId(kind: string, name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return slug ? `${kind}-${slug}` : kind;
}

export function resetDb(): void {
  db.tasks = makeTasks();
  db.buckets = makeBuckets();
  db.catchup = makeCatchupItems();
  db.people = makePeople();
  db.triageRules = [];
  db.sources = makeSources();
  db.sourceKinds = makeSourceKinds();
  db.detections = {
    github: {
      available: true,
      detail: 'Read your GitHub CLI login.',
      applied: { token: 'saved', username: '9hgg' },
      choices: { org: ['acme', 'widgets'] },
      source: null,
    },
  };
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
    const archived = url.searchParams.get('archived') === 'true';
    const q = url.searchParams.get('q');

    let tasks = db.tasks.filter((t) => Boolean(t.archived) === archived);
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
      description: null,
      bucket: body.bucket ?? 'Uncategorized',
      status: 'open',
      tags: body.tags ?? [],
      unread: false,
      origin: 'manual',
      archived: false,
      updated_at: new Date().toISOString(),
      items: [],
      candidates: [],
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
      archived: false,
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

  // Every item, with its links — items filed on a task carry a confirmed link to it, plus
  // the untriaged ones still in the catch-up inbox. The real backend reads one items table.
  http.get(`${BASE}/items`, () => {
    const byId = new Map<string, ItemWithLinks>();
    for (const task of db.tasks) {
      for (const it of task.items) {
        const existing = byId.get(it.id);
        const link: Link = {
          task: { id: task.id, title: task.title, bucket: task.bucket },
          state: 'confirmed',
          engine: null,
          confidence: 1,
          reason: null,
        };
        if (existing) existing.links.push(link);
        else byId.set(it.id, { ...it, links: [link] });
      }
    }
    for (const it of db.catchup) {
      if (!byId.has(it.id)) byId.set(it.id, { ...it, links: it.links });
    }
    const all = [...byId.values()].sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
    return HttpResponse.json(all);
  }),

  http.get(`${BASE}/items/skipped`, () =>
    HttpResponse.json(db.catchup.filter((item) => item.triaged && item.triage_reason)),
  ),

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
    item.triage_reason = null;
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
      description: null,
      bucket: body.bucket ?? 'Uncategorized',
      status: 'open',
      tags: [],
      unread: false,
      origin: 'manual',
      archived: false,
      updated_at: item.occurred_at,
      items: [item],
      candidates: [],
    };
    db.tasks.push(task);
    // The item stays in the inbox on purpose — a new task doesn't triage it away.
    return HttpResponse.json(task);
  }),

  http.post(`${BASE}/catchup/:itemId/suggest-tasks`, () => HttpResponse.json([])),

  http.get(`${BASE}/catchup/match-status`, () =>
    HttpResponse.json({ running: false, total: 0, done: 0, remaining: 0 }),
  ),

  http.post(`${BASE}/catchup/match-stop`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${BASE}/triage-rules`, () => HttpResponse.json(db.triageRules)),

  http.post(`${BASE}/triage-rules`, async ({ request }) => {
    const body = (await request.json()) as Partial<TriageRule>;
    const rule: TriageRule = {
      id: `rule:${Math.random().toString(16).slice(2, 10)}`,
      name: body.name || (body.value ?? ''),
      sources: body.sources ?? [],
      condition: body.condition ?? 'contains',
      value: body.value ?? '',
      enabled: true,
    };
    db.triageRules.push(rule);
    return HttpResponse.json(rule, { status: 201 });
  }),

  http.delete(`${BASE}/triage-rules/:id`, ({ params }) => {
    db.triageRules = db.triageRules.filter((r) => r.id !== params.id);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${BASE}/catchup/:itemId/triage`, async ({ params, request }) => {
    const item = db.catchup.find((i) => i.id === params.itemId);
    if (!item) return notFound(`Item not found: ${String(params.itemId)}`);
    const { triaged } = (await request.json()) as { triaged: boolean };
    item.triaged = triaged;
    item.triage_reason = triaged ? 'Skipped' : null;
    item.triaged_at = triaged ? new Date().toISOString() : null;
    return HttpResponse.json(item);
  }),

  http.get(`${BASE}/people`, () => HttpResponse.json(db.people)),

  http.post(`${BASE}/people`, async ({ request }) => {
    const body = (await request.json()) as Partial<Person> & {
      identities?: { kind: string; value: string; label?: string | null }[];
    };
    const person: Person = {
      id: `person:${Math.random().toString(16).slice(2, 10)}`,
      display_name: body.display_name ?? '',
      email: body.email ?? null,
      note: body.note ?? null,
      identities: (body.identities ?? []).map((i, n) => ({
        id: `pid:${Math.random().toString(16).slice(2, 8)}${n}`,
        kind: i.kind,
        value: i.value,
        label: i.label ?? null,
      })),
    };
    db.people.push(person);
    return HttpResponse.json(person, { status: 201 });
  }),

  http.get(`${BASE}/people/:id`, ({ params }) => {
    const person = db.people.find((p) => p.id === params.id);
    return person ? HttpResponse.json(person) : notFound(`Person not found: ${String(params.id)}`);
  }),

  http.patch(`${BASE}/people/:id`, async ({ params, request }) => {
    const person = db.people.find((p) => p.id === params.id);
    if (!person) return notFound(`Person not found: ${String(params.id)}`);
    Object.assign(person, await request.json());
    return HttpResponse.json(person);
  }),

  http.delete(`${BASE}/people/:id`, ({ params }) => {
    if (!db.people.some((p) => p.id === params.id)) {
      return notFound(`Person not found: ${String(params.id)}`);
    }
    db.people = db.people.filter((p) => p.id !== params.id);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${BASE}/people/:id/identities`, async ({ params, request }) => {
    const person = db.people.find((p) => p.id === params.id);
    if (!person) return notFound(`Person not found: ${String(params.id)}`);
    const identity = (await request.json()) as {
      kind: string;
      value: string;
      label?: string | null;
    };
    const taken = db.people.some((p) =>
      p.identities.some((i) => i.kind === identity.kind && i.value === identity.value),
    );
    if (taken) {
      return HttpResponse.json(
        { detail: `${identity.kind}:${identity.value} already belongs to someone` },
        { status: 409 },
      );
    }
    person.identities.push({
      id: `pid:${Math.random().toString(16).slice(2, 8)}`,
      kind: identity.kind,
      value: identity.value,
      label: identity.label ?? null,
    });
    return HttpResponse.json(person, { status: 201 });
  }),

  http.delete(`${BASE}/people/:id/identities/:identityId`, ({ params }) => {
    const person = db.people.find((p) => p.id === params.id);
    if (!person) return notFound(`Person not found: ${String(params.id)}`);
    person.identities = person.identities.filter((i) => i.id !== params.identityId);
    return HttpResponse.json(person);
  }),

  http.post(`${BASE}/people/:id/merge`, async ({ params, request }) => {
    const source = db.people.find((p) => p.id === params.id);
    const { into } = (await request.json()) as { into: string };
    const target = db.people.find((p) => p.id === into);
    if (!source || !target) return notFound('Both people must exist to merge');
    target.identities = [...target.identities, ...source.identities];
    db.people = db.people.filter((p) => p.id !== source.id);
    return HttpResponse.json(target);
  }),

  http.post(`${BASE}/sync`, () => {
    db.syncLog.unshift({
      id: db.syncLog.length + 1,
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      sources: [
        { source: 'github', kind: 'github', items_fetched: 1, configured: true, error: null },
      ],
      items_fetched: 1,
      items_added: 1,
      items_updated: 0,
      proposals: 0,
      tasks_updated: 0,
      duration_seconds: 0.4,
      error: null,
    });
    return HttpResponse.json({
      sources_synced: ['github', 'slack'],
      items_added: 1,
      items_updated: 0,
      proposals: 0,
      tasks_updated: 0,
      duration_seconds: 0.4,
      errors: [],
    });
  }),

  http.get(`${BASE}/sync/status`, () => HttpResponse.json(db.syncLog)),

  http.get(`${BASE}/admin/settings`, () => HttpResponse.json(db.settings)),

  http.patch(`${BASE}/admin/settings`, async ({ request }) => {
    const body = (await request.json()) as Partial<AppSettings>;
    db.settings = { ...db.settings, ...body };
    return HttpResponse.json(db.settings);
  }),

  http.post(`${BASE}/admin/backup`, () =>
    HttpResponse.json({
      filename: 'hq-20260717-220000.db',
      path: '/app/backups/hq-20260717-220000.db',
      size_bytes: 40960,
      created_at: '2026-07-17T22:00:00Z',
    }),
  ),

  http.get(`${BASE}/admin/source-kinds`, () => HttpResponse.json(db.sourceKinds)),

  http.get(`${BASE}/admin/sources`, () => HttpResponse.json(db.sources)),

  http.post(`${BASE}/admin/sources`, async ({ request }) => {
    const body = (await request.json()) as { kind: string; name?: string };
    const kind = db.sourceKinds.find((k) => k.kind === body.kind);
    if (!kind) return HttpResponse.json({ detail: `Unknown kind: ${body.kind}` }, { status: 400 });

    const name = body.name?.trim() || kind.name;
    const id = instanceId(body.kind, name);
    if (db.sources.some((s) => s.id === id)) {
      return HttpResponse.json(
        { detail: `You already have a source called ${name}` },
        { status: 409 },
      );
    }

    const source: SourceStatus = {
      id,
      kind: kind.kind,
      name,
      position: db.sources.length + 1,
      description: kind.description,
      status: 'unconfigured',
      detail: 'Not configured',
      last_checked_at: null,
      error: null,
      fields: makeSourceFields(kind.kind),
      setup: kind.setup,
      setup_url: kind.setup_url,
      manifest: kind.manifest,
      manifest_hint: kind.manifest_hint,
      detectable: kind.detectable,
    };
    db.sources.push(source);
    return HttpResponse.json(source, { status: 201 });
  }),

  http.patch(`${BASE}/admin/sources/:id`, async ({ params, request }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`No source: ${String(params.id)}`);
    const patch = (await request.json()) as { name?: string; position?: number };
    if (patch.name?.trim()) source.name = patch.name.trim();
    if (patch.position !== undefined) source.position = patch.position;
    return HttpResponse.json(source);
  }),

  http.delete(`${BASE}/admin/sources/:id`, ({ params }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`No source: ${String(params.id)}`);
    db.sources = db.sources.filter((s) => s.id !== params.id);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${BASE}/admin/sources/:id/detect`, ({ params }) => {
    const source = db.sources.find((s) => s.id === params.id);
    if (!source) return notFound(`No source: ${String(params.id)}`);
    const detection = db.detections[source.kind];
    if (!detection) {
      return HttpResponse.json({
        available: false,
        detail: 'Nothing to detect for this source.',
        applied: {},
        choices: {},
        source: null,
      });
    }
    if (!detection.available) return HttpResponse.json(detection);

    // Detection saves what it found, so the source comes back already filled in.
    for (const field of source.fields) {
      const applied = detection.applied[field.key];
      if (applied === undefined) continue;
      field.is_set = true;
      field.value = field.kind === 'secret' ? '••••••••cli1' : applied;
    }
    return HttpResponse.json({ ...detection, source });
  }),

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
