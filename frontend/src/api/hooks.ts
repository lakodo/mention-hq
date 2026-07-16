import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  clearSourceConfig,
  confirmLinks,
  createBucket,
  createTask,
  createTaskFromItem,
  deleteBucket,
  deleteTask,
  fetchAIStatus,
  fetchBuckets,
  fetchCatchup,
  fetchSettings,
  fetchSources,
  fetchSyncStatus,
  fetchTask,
  fetchTasks,
  patchBucket,
  patchSettings,
  patchTask,
  postSync,
  putAIKey,
  putSourceConfig,
  reassignBuckets,
  rejectLink,
  suggestBucket,
  testSource,
  triageItem,
} from './client';
import type {
  AIStatus,
  AppSettings,
  Bucket,
  BucketCreate,
  BucketPatch,
  BucketSuggestion,
  ItemWithLinks,
  SourceStatus,
  SyncLogEntry,
  SyncResult,
  Task,
  TaskCreate,
  TaskFilters,
  TaskPatch,
} from '../types';

export const queryKeys = {
  tasks: (filters: TaskFilters = {}) => ['tasks', filters] as const,
  task: (id: string) => ['task', id] as const,
  buckets: () => ['buckets'] as const,
  catchup: () => ['catchup'] as const,
  syncStatus: () => ['sync', 'status'] as const,
  sources: () => ['admin', 'sources'] as const,
  settings: () => ['admin', 'settings'] as const,
  ai: () => ['admin', 'ai'] as const,
};

export function useTasks(filters: TaskFilters = {}): UseQueryResult<Task[]> {
  return useQuery({ queryKey: queryKeys.tasks(filters), queryFn: () => fetchTasks(filters) });
}

export function useTask(id: string | undefined): UseQueryResult<Task> {
  return useQuery({
    queryKey: queryKeys.task(id ?? ''),
    queryFn: () => fetchTask(id as string),
    enabled: Boolean(id),
  });
}

export function useBuckets(): UseQueryResult<Bucket[]> {
  return useQuery({ queryKey: queryKeys.buckets(), queryFn: fetchBuckets });
}

export function useCatchup(limit?: number): UseQueryResult<ItemWithLinks[]> {
  return useQuery({ queryKey: queryKeys.catchup(), queryFn: () => fetchCatchup(limit) });
}

export function useSyncStatus(limit?: number): UseQueryResult<SyncLogEntry[]> {
  return useQuery({ queryKey: queryKeys.syncStatus(), queryFn: () => fetchSyncStatus(limit) });
}

export function useSources(): UseQueryResult<SourceStatus[]> {
  return useQuery({ queryKey: queryKeys.sources(), queryFn: fetchSources });
}

export function useSettings(): UseQueryResult<AppSettings> {
  return useQuery({ queryKey: queryKeys.settings(), queryFn: fetchSettings });
}

export function useAIStatus(): UseQueryResult<AIStatus> {
  return useQuery({ queryKey: queryKeys.ai(), queryFn: fetchAIStatus });
}

function useInvalidateTasks() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ['tasks'] });
    void qc.invalidateQueries({ queryKey: ['task'] });
    void qc.invalidateQueries({ queryKey: queryKeys.buckets() });
  };
}

/**
 * Patch a task, updating every cached list plus the single-task entry up front so
 * the read/unread toggle lands instantly on Board and Timeline.
 */
export function useUpdateTask(): UseMutationResult<
  Task,
  Error,
  { id: string; patch: TaskPatch },
  { previous: [readonly unknown[], unknown][] }
> {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ id, patch }) => patchTask(id, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: ['tasks'] });
      await qc.cancelQueries({ queryKey: queryKeys.task(id) });
      const previous = [
        ...qc.getQueriesData({ queryKey: ['tasks'] }),
        ...qc.getQueriesData({ queryKey: queryKeys.task(id) }),
      ] as [readonly unknown[], unknown][];

      qc.setQueriesData<Task[]>({ queryKey: ['tasks'] }, (old) =>
        Array.isArray(old) ? old.map((t) => (t.id === id ? { ...t, ...patch } : t)) : old,
      );
      qc.setQueryData<Task>(queryKeys.task(id), (old) => (old ? { ...old, ...patch } : old));

      return { previous };
    },
    onError: (_err, _vars, context) => {
      for (const [key, data] of context?.previous ?? []) qc.setQueryData(key, data);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: ['task'] });
      void qc.invalidateQueries({ queryKey: queryKeys.buckets() });
    },
  });
}

export function useCreateTask(): UseMutationResult<Task, Error, TaskCreate> {
  const invalidate = useInvalidateTasks();
  return useMutation({ mutationFn: createTask, onSuccess: invalidate });
}

export function useDeleteTask(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidateTasks();
  return useMutation({ mutationFn: deleteTask, onSuccess: invalidate });
}

export function useSync(): UseMutationResult<SyncResult, Error, string | undefined> {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (source) => postSync(source),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tasks'] });
      void qc.invalidateQueries({ queryKey: ['task'] });
      void qc.invalidateQueries({ queryKey: queryKeys.buckets() });
      void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
      void qc.invalidateQueries({ queryKey: queryKeys.syncStatus() });
    },
  });
}

function useCatchupInvalidation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
    void qc.invalidateQueries({ queryKey: ['tasks'] });
    void qc.invalidateQueries({ queryKey: ['task'] });
    void qc.invalidateQueries({ queryKey: queryKeys.buckets() });
  };
}

/** Attaching an item to one or more tasks also triages it, so it leaves the inbox. */
export function useConfirmLinks(): UseMutationResult<
  ItemWithLinks,
  Error,
  { itemId: string; taskIds: string[] }
> {
  const invalidate = useCatchupInvalidation();
  return useMutation({
    mutationFn: ({ itemId, taskIds }) => confirmLinks(itemId, taskIds),
    onSuccess: invalidate,
  });
}

/**
 * Rejecting one link leaves the item untriaged, so it stays in the inbox with the
 * refreshed links written straight back into the cached list.
 */
export function useRejectLink(): UseMutationResult<
  ItemWithLinks,
  Error,
  { itemId: string; taskId: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, taskId }) => rejectLink(itemId, taskId),
    onSuccess: (updated) => {
      qc.setQueryData<ItemWithLinks[]>(queryKeys.catchup(), (old) =>
        old?.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
  });
}

export function useCreateTaskFromItem(): UseMutationResult<
  Task,
  Error,
  { itemId: string; title: string; bucket?: string }
> {
  const invalidate = useCatchupInvalidation();
  return useMutation({
    mutationFn: ({ itemId, title, bucket }) => createTaskFromItem(itemId, title, bucket),
    onSuccess: invalidate,
  });
}

export function useTriageItem(): UseMutationResult<
  ItemWithLinks,
  Error,
  { itemId: string; triaged: boolean }
> {
  const invalidate = useCatchupInvalidation();
  return useMutation({
    mutationFn: ({ itemId, triaged }) => triageItem(itemId, triaged),
    onSuccess: invalidate,
  });
}

function useBucketInvalidation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.buckets() });
    void qc.invalidateQueries({ queryKey: ['tasks'] });
    void qc.invalidateQueries({ queryKey: ['task'] });
  };
}

export function useCreateBucket(): UseMutationResult<Bucket, Error, BucketCreate> {
  const invalidate = useBucketInvalidation();
  return useMutation({ mutationFn: createBucket, onSuccess: invalidate });
}

export function useUpdateBucket(): UseMutationResult<
  Bucket,
  Error,
  { name: string; patch: BucketPatch }
> {
  const invalidate = useBucketInvalidation();
  return useMutation({
    mutationFn: ({ name, patch }) => patchBucket(name, patch),
    onSuccess: invalidate,
  });
}

export function useDeleteBucket(): UseMutationResult<void, Error, string> {
  const invalidate = useBucketInvalidation();
  return useMutation({ mutationFn: deleteBucket, onSuccess: invalidate });
}

export function useReassignBuckets(): UseMutationResult<Bucket[], Error, void> {
  const invalidate = useBucketInvalidation();
  return useMutation({ mutationFn: reassignBuckets, onSuccess: invalidate });
}

export function useSuggestBucket(): UseMutationResult<BucketSuggestion, Error, string> {
  return useMutation({ mutationFn: suggestBucket });
}

export function useUpdateSettings(): UseMutationResult<AppSettings, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: patchSettings,
    onSuccess: (settings) => qc.setQueryData(queryKeys.settings(), settings),
  });
}

function useWriteSourceStatus() {
  const qc = useQueryClient();
  return (result: SourceStatus) => {
    qc.setQueryData<SourceStatus[]>(queryKeys.sources(), (old) =>
      old?.map((s) => (s.id === result.id ? result : s)),
    );
  };
}

export function useTestSource(): UseMutationResult<SourceStatus, Error, string> {
  const write = useWriteSourceStatus();
  return useMutation({ mutationFn: testSource, onSuccess: write });
}

export function useUpdateSourceConfig(): UseMutationResult<
  SourceStatus,
  Error,
  { id: string; values: Record<string, string> }
> {
  const write = useWriteSourceStatus();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, values }) => putSourceConfig(id, values),
    onSuccess: (result) => {
      write(result);
      void qc.invalidateQueries({ queryKey: queryKeys.ai() });
    },
  });
}

export function useClearSourceConfig(): UseMutationResult<SourceStatus, Error, string> {
  const write = useWriteSourceStatus();
  return useMutation({ mutationFn: clearSourceConfig, onSuccess: write });
}

export function useUpdateAIKey(): UseMutationResult<AIStatus, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: putAIKey,
    onSuccess: (status) => qc.setQueryData(queryKeys.ai(), status),
  });
}
