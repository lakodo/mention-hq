import axios from 'axios';
import type {
  AIStatus,
  AppSettings,
  AppSettingsPatch,
  Bucket,
  BucketCreate,
  BucketPatch,
  BucketSuggestion,
  Detection,
  IdentityInput,
  ItemWithLinks,
  Person,
  PersonCreate,
  PersonPatch,
  SourceCreate,
  SourceKind,
  SourcePatch,
  SourceStatus,
  SyncLogEntry,
  SyncResult,
  Task,
  TaskCreate,
  TaskFilters,
  TaskMatch,
  TaskPatch,
  TriageRule,
  TriageRuleCreate,
} from '../types';

// Relative, so the browser resolves it against wherever the app is served — behind the
// Caddy proxy on a bare local domain, the Vite dev proxy, or the API serving the built SPA
// itself. All three route /api to the backend, so the app never hardcodes a host or port.
export const API_URL: string = import.meta.env.VITE_API_URL ?? '/api';

export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

/** Ids carry colons and `~` (e.g. `branch:repo:owner~feature`), so they must be escaped. */
const seg = encodeURIComponent;

export async function fetchTasks(filters: TaskFilters = {}): Promise<Task[]> {
  const { data } = await api.get<Task[]>('/tasks', {
    params: {
      bucket: filters.bucket || undefined,
      source: filters.source || undefined,
      status: filters.status || undefined,
      unread: filters.unread ?? undefined,
      archived: filters.archived || undefined,
      q: filters.q || undefined,
    },
  });
  return data;
}

export async function fetchTask(id: string): Promise<Task> {
  const { data } = await api.get<Task>(`/tasks/${seg(id)}`);
  return data;
}

export async function createTask(payload: TaskCreate): Promise<Task> {
  const { data } = await api.post<Task>('/tasks', payload);
  return data;
}

export async function patchTask(id: string, patch: TaskPatch): Promise<Task> {
  const { data } = await api.patch<Task>(`/tasks/${seg(id)}`, patch);
  return data;
}

export async function deleteTask(id: string): Promise<void> {
  await api.delete(`/tasks/${seg(id)}`);
}

export async function fetchBuckets(): Promise<Bucket[]> {
  const { data } = await api.get<Bucket[]>('/buckets');
  return data;
}

export async function createBucket(payload: BucketCreate): Promise<Bucket> {
  const { data } = await api.post<Bucket>('/buckets', payload);
  return data;
}

export async function patchBucket(name: string, patch: BucketPatch): Promise<Bucket> {
  const { data } = await api.patch<Bucket>(`/buckets/${seg(name)}`, patch);
  return data;
}

export async function deleteBucket(name: string): Promise<void> {
  await api.delete(`/buckets/${seg(name)}`);
}

export async function reassignBuckets(): Promise<Bucket[]> {
  const { data } = await api.post<Bucket[]>('/buckets/reassign');
  return data;
}

export async function suggestBucket(taskId: string): Promise<BucketSuggestion> {
  const { data } = await api.post<BucketSuggestion>(`/buckets/suggest/${seg(taskId)}`);
  return data;
}

export async function fetchCatchup(limit?: number): Promise<ItemWithLinks[]> {
  const { data } = await api.get<ItemWithLinks[]>('/catchup', { params: { limit } });
  return data;
}

export async function fetchItems(limit?: number): Promise<ItemWithLinks[]> {
  const { data } = await api.get<ItemWithLinks[]>('/items', { params: { limit } });
  return data;
}

export async function fetchPeople(): Promise<Person[]> {
  const { data } = await api.get<Person[]>('/people');
  return data;
}

export async function createPerson(payload: PersonCreate): Promise<Person> {
  const { data } = await api.post<Person>('/people', payload);
  return data;
}

export async function updatePerson(id: string, patch: PersonPatch): Promise<Person> {
  const { data } = await api.patch<Person>(`/people/${seg(id)}`, patch);
  return data;
}

export async function deletePerson(id: string): Promise<void> {
  await api.delete(`/people/${seg(id)}`);
}

export async function addIdentity(id: string, identity: IdentityInput): Promise<Person> {
  const { data } = await api.post<Person>(`/people/${seg(id)}/identities`, identity);
  return data;
}

export async function removeIdentity(id: string, identityId: string): Promise<Person> {
  const { data } = await api.delete<Person>(`/people/${seg(id)}/identities/${seg(identityId)}`);
  return data;
}

export async function mergePeople(sourceId: string, into: string): Promise<Person> {
  const { data } = await api.post<Person>(`/people/${seg(sourceId)}/merge`, { into });
  return data;
}

export async function confirmLinks(itemId: string, taskIds: string[]): Promise<ItemWithLinks> {
  const { data } = await api.post<ItemWithLinks>(`/catchup/${seg(itemId)}/confirm`, {
    task_ids: taskIds,
  });
  return data;
}

export async function rejectLink(itemId: string, taskId: string): Promise<ItemWithLinks> {
  const { data } = await api.post<ItemWithLinks>(`/catchup/${seg(itemId)}/reject/${seg(taskId)}`);
  return data;
}

export async function createTaskFromItem(
  itemId: string,
  title: string,
  bucket?: string,
): Promise<Task> {
  const { data } = await api.post<Task>(`/catchup/${seg(itemId)}/new-task`, { title, bucket });
  return data;
}

export async function suggestItemTasks(itemId: string): Promise<TaskMatch[]> {
  const { data } = await api.post<TaskMatch[]>(`/catchup/${seg(itemId)}/suggest-tasks`);
  return data;
}

export async function fetchTriageRules(): Promise<TriageRule[]> {
  const { data } = await api.get<TriageRule[]>('/triage-rules');
  return data;
}

export async function createTriageRule(payload: TriageRuleCreate): Promise<TriageRule> {
  const { data } = await api.post<TriageRule>('/triage-rules', payload);
  return data;
}

export async function deleteTriageRule(id: string): Promise<void> {
  await api.delete(`/triage-rules/${seg(id)}`);
}

export async function triageItem(itemId: string, triaged: boolean): Promise<ItemWithLinks> {
  const { data } = await api.post<ItemWithLinks>(`/catchup/${seg(itemId)}/triage`, { triaged });
  return data;
}

export async function postSync(source?: string): Promise<SyncResult> {
  const { data } = await api.post<SyncResult>('/sync', source ? { source } : {});
  return data;
}

export async function fetchSyncStatus(limit?: number): Promise<SyncLogEntry[]> {
  const { data } = await api.get<SyncLogEntry[]>('/sync/status', { params: { limit } });
  return data;
}

export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await api.get<AppSettings>('/admin/settings');
  return data;
}

export async function patchSettings(patch: AppSettingsPatch): Promise<AppSettings> {
  const { data } = await api.patch<AppSettings>('/admin/settings', patch);
  return data;
}

export async function fetchSourceKinds(): Promise<SourceKind[]> {
  const { data } = await api.get<SourceKind[]>('/admin/source-kinds');
  return data;
}

export async function fetchSources(): Promise<SourceStatus[]> {
  const { data } = await api.get<SourceStatus[]>('/admin/sources');
  return data;
}

export async function addSource(payload: SourceCreate): Promise<SourceStatus> {
  const { data } = await api.post<SourceStatus>('/admin/sources', payload);
  return data;
}

export async function patchSource(id: string, patch: SourcePatch): Promise<SourceStatus> {
  const { data } = await api.patch<SourceStatus>(`/admin/sources/${seg(id)}`, patch);
  return data;
}

export async function removeSource(id: string): Promise<void> {
  await api.delete(`/admin/sources/${seg(id)}`);
}

export async function testSource(id: string): Promise<SourceStatus> {
  const { data } = await api.post<SourceStatus>(`/admin/sources/${seg(id)}/test`);
  return data;
}

export async function detectSource(id: string): Promise<Detection> {
  const { data } = await api.post<Detection>(`/admin/sources/${seg(id)}/detect`);
  return data;
}

/** Only the keys present are written. Send "" to clear one. */
export async function putSourceConfig(
  id: string,
  values: Record<string, string>,
): Promise<SourceStatus> {
  const { data } = await api.put<SourceStatus>(`/admin/sources/${seg(id)}/config`, { values });
  return data;
}

export async function fetchAIStatus(): Promise<AIStatus> {
  const { data } = await api.get<AIStatus>('/admin/ai');
  return data;
}

/** Send "" to clear the key and fall back to the CLI login or the environment. */
export async function putAIKey(apiKey: string): Promise<AIStatus> {
  const { data } = await api.put<AIStatus>('/admin/ai/key', { api_key: apiKey });
  return data;
}

/**
 * A 409 from /sync means a run is already in flight. It is not a failure: that run
 * refreshes the same data, so the caller has nothing to do but let it finish.
 */
export function isSyncAlreadyRunning(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 409;
}

/** Pulls the `detail` a FastAPI error carries, for surfacing in a toast. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}
