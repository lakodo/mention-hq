import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  addIdentity,
  backupDatabase,
  addSource,
  archiveBucket,
  confirmLinks,
  createBucket,
  createPerson,
  createTask,
  createTaskFromItem,
  deleteBucket,
  deletePerson,
  deleteTask,
  detectSource,
  fetchAIStatus,
  fetchBuckets,
  fetchCatchup,
  fetchItems,
  fetchPeople,
  fetchSettings,
  fetchSkippedItems,
  fetchSourceKinds,
  fetchSources,
  fetchMatchStatus,
  fetchSyncStatus,
  fetchTask,
  fetchTasks,
  matchAllItems,
  stopMatching,
  mergePeople,
  patchBucket,
  patchSettings,
  patchSource,
  patchTask,
  postSync,
  putAIKey,
  putSourceConfig,
  reassignBuckets,
  rejectLink,
  removeIdentity,
  removeSource,
  restoreBucket,
  suggestBucket,
  suggestItemTasks,
  createTriageRule,
  deleteTriageRule,
  fetchTriageRules,
  testSource,
  triageItem,
  updatePerson,
} from './client';
import type {
  AIStatus,
  AppSettings,
  AppSettingsPatch,
  Backup,
  Bucket,
  BucketArchive,
  BucketCreate,
  BucketPatch,
  BucketSuggestion,
  Detection,
  ItemWithLinks,
  MatchStatus,
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
  TaskMatch,
  TaskFilters,
  TaskPatch,
  TriageRule,
  TriageRuleCreate,
} from '../types';

export const queryKeys = {
  tasks: (filters: TaskFilters = {}) => ['tasks', filters] as const,
  task: (id: string) => ['task', id] as const,
  buckets: () => ['buckets'] as const,
  catchup: () => ['catchup'] as const,
  matchStatus: () => ['catchup', 'match-status'] as const,
  items: () => ['items'] as const,
  skipped: (since?: string) => ['items', 'skipped', since] as const,
  people: () => ['people'] as const,
  syncStatus: () => ['sync', 'status'] as const,
  sources: () => ['admin', 'sources'] as const,
  sourceKinds: () => ['admin', 'source-kinds'] as const,
  settings: () => ['admin', 'settings'] as const,
  ai: () => ['admin', 'ai'] as const,
  triageRules: () => ['triage-rules'] as const,
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

export function useItems(limit?: number): UseQueryResult<ItemWithLinks[]> {
  return useQuery({ queryKey: queryKeys.items(), queryFn: () => fetchItems(limit) });
}

export function useSkippedItems(since?: string): UseQueryResult<ItemWithLinks[]> {
  return useQuery({
    queryKey: queryKeys.skipped(since),
    queryFn: () => fetchSkippedItems(since),
  });
}

export function useSyncStatus(limit?: number): UseQueryResult<SyncLogEntry[]> {
  return useQuery({ queryKey: queryKeys.syncStatus(), queryFn: () => fetchSyncStatus(limit) });
}

export function useSources(): UseQueryResult<SourceStatus[]> {
  return useQuery({ queryKey: queryKeys.sources(), queryFn: fetchSources });
}

export function useSourceKinds(): UseQueryResult<SourceKind[]> {
  return useQuery({ queryKey: queryKeys.sourceKinds(), queryFn: fetchSourceKinds });
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
      void qc.invalidateQueries({ queryKey: queryKeys.items() });
      void qc.invalidateQueries({ queryKey: queryKeys.syncStatus() });
    },
  });
}

function useCatchupInvalidation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
    void qc.invalidateQueries({ queryKey: queryKeys.items() });
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

export function useUnSkipItem(): UseMutationResult<ItemWithLinks, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => triageItem(itemId, false),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['items', 'skipped'] });
      void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
    },
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

export function useDeleteBucket(): UseMutationResult<
  void,
  Error,
  { name: string; cascadeTasks?: boolean }
> {
  const invalidate = useBucketInvalidation();
  return useMutation({
    mutationFn: ({ name, cascadeTasks }) => deleteBucket(name, cascadeTasks),
    onSuccess: invalidate,
  });
}

export function useArchiveBucket(): UseMutationResult<
  Bucket,
  Error,
  { name: string; payload: BucketArchive }
> {
  const invalidate = useBucketInvalidation();
  return useMutation({
    mutationFn: ({ name, payload }) => archiveBucket(name, payload),
    onSuccess: invalidate,
  });
}

export function useRestoreBucket(): UseMutationResult<Bucket, Error, string> {
  const invalidate = useBucketInvalidation();
  return useMutation({ mutationFn: restoreBucket, onSuccess: invalidate });
}

export function useReassignBuckets(): UseMutationResult<Bucket[], Error, void> {
  const invalidate = useBucketInvalidation();
  return useMutation({ mutationFn: reassignBuckets, onSuccess: invalidate });
}

export function useSuggestBucket(): UseMutationResult<BucketSuggestion, Error, string> {
  return useMutation({ mutationFn: suggestBucket });
}

export function useSuggestItemTasks(): UseMutationResult<TaskMatch[], Error, string> {
  return useMutation({ mutationFn: suggestItemTasks });
}

export function useMatchAllItems(): UseMutationResult<void, Error, void> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: matchAllItems,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
      void qc.invalidateQueries({ queryKey: queryKeys.matchStatus() });
    },
  });
}

export function useMatchStatus(): UseQueryResult<MatchStatus> {
  return useQuery({
    queryKey: queryKeys.matchStatus(),
    queryFn: fetchMatchStatus,
    // Poll only while a pass is running, so an idle app isn't hitting the endpoint.
    refetchInterval: (query) => (query.state.data?.running ? 1000 : false),
  });
}

export function useStopMatching(): UseMutationResult<void, Error, void> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: stopMatching,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.matchStatus() }),
  });
}

export function useTriageRules(): UseQueryResult<TriageRule[]> {
  return useQuery({ queryKey: queryKeys.triageRules(), queryFn: fetchTriageRules });
}

function useTriageRulesInvalidation() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.triageRules() });
    // A rule skips inbox items on apply, so the catch-up list changes too.
    void qc.invalidateQueries({ queryKey: queryKeys.catchup() });
    void qc.invalidateQueries({ queryKey: queryKeys.items() });
  };
}

export function useCreateTriageRule(): UseMutationResult<TriageRule, Error, TriageRuleCreate> {
  const invalidate = useTriageRulesInvalidation();
  return useMutation({ mutationFn: createTriageRule, onSuccess: invalidate });
}

export function useDeleteTriageRule(): UseMutationResult<void, Error, string> {
  const invalidate = useTriageRulesInvalidation();
  return useMutation({ mutationFn: deleteTriageRule, onSuccess: invalidate });
}

export function useUpdateSettings(): UseMutationResult<AppSettings, Error, AppSettingsPatch> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: patchSettings,
    onSuccess: (settings) => qc.setQueryData(queryKeys.settings(), settings),
  });
}

export function useBackupDatabase(): UseMutationResult<Backup, Error, void> {
  return useMutation({ mutationFn: backupDatabase });
}

function useInvalidateSources() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.sources() });
  };
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

export function useAddSource(): UseMutationResult<SourceStatus, Error, SourceCreate> {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: addSource, onSuccess: invalidate });
}

export function useRenameSource(): UseMutationResult<
  SourceStatus,
  Error,
  { id: string; patch: SourcePatch }
> {
  const write = useWriteSourceStatus();
  return useMutation({ mutationFn: ({ id, patch }) => patchSource(id, patch), onSuccess: write });
}

export function useRemoveSource(): UseMutationResult<void, Error, string> {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: removeSource, onSuccess: invalidate });
}

/** Detection saves what it found server-side, so the refreshed source comes back with it. */
export function useDetectSource(): UseMutationResult<Detection, Error, string> {
  const write = useWriteSourceStatus();
  return useMutation({
    mutationFn: detectSource,
    onSuccess: (detection) => {
      if (detection.source) write(detection.source);
    },
  });
}

export function useUpdateAIKey(): UseMutationResult<AIStatus, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: putAIKey,
    onSuccess: (status) => qc.setQueryData(queryKeys.ai(), status),
  });
}

export function usePeople(): UseQueryResult<Person[]> {
  return useQuery({ queryKey: queryKeys.people(), queryFn: fetchPeople });
}

function usePeopleInvalidation() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: queryKeys.people() });
}

export function useCreatePerson(): UseMutationResult<Person, Error, PersonCreate> {
  const invalidate = usePeopleInvalidation();
  return useMutation({ mutationFn: createPerson, onSuccess: invalidate });
}

export function useUpdatePerson(): UseMutationResult<
  Person,
  Error,
  { id: string; patch: PersonPatch }
> {
  const invalidate = usePeopleInvalidation();
  return useMutation({
    mutationFn: ({ id, patch }) => updatePerson(id, patch),
    onSuccess: invalidate,
  });
}

export function useDeletePerson(): UseMutationResult<void, Error, string> {
  const invalidate = usePeopleInvalidation();
  return useMutation({ mutationFn: deletePerson, onSuccess: invalidate });
}

export function useAddIdentity(): UseMutationResult<
  Person,
  Error,
  { id: string; kind: string; value: string; label?: string | null }
> {
  const invalidate = usePeopleInvalidation();
  return useMutation({
    mutationFn: ({ id, kind, value, label }) => addIdentity(id, { kind, value, label }),
    onSuccess: invalidate,
  });
}

export function useRemoveIdentity(): UseMutationResult<
  Person,
  Error,
  { id: string; identityId: string }
> {
  const invalidate = usePeopleInvalidation();
  return useMutation({
    mutationFn: ({ id, identityId }) => removeIdentity(id, identityId),
    onSuccess: invalidate,
  });
}

export function useMergePeople(): UseMutationResult<
  Person,
  Error,
  { sourceId: string; into: string }
> {
  const invalidate = usePeopleInvalidation();
  return useMutation({
    mutationFn: ({ sourceId, into }) => mergePeople(sourceId, into),
    onSuccess: invalidate,
  });
}
