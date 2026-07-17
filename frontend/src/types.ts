export type Source = 'pr' | 'issue' | 'linear' | 'slack' | 'branch' | 'todo' | 'markdown' | 'dust';

export type Status = 'open' | 'in_progress' | 'merged' | 'done';

export type LinkState = 'proposed' | 'confirmed' | 'rejected';

export type Origin = 'auto' | 'manual';

export interface TaskRef {
  id: string;
  title: string;
  bucket: string;
}

export interface Item {
  id: string;
  source: Source;
  label: string;
  url: string | null;
  context: string | null;
  occurred_at: string;
  triaged: boolean;
  triage_reason: string | null;
  triaged_at: string | null;
  pr_status: string | null;
}

/** One item's attachment to one task, and who decided it. */
export interface Link {
  task: TaskRef;
  state: LinkState;
  engine: string | null;
  confidence: number;
  reason: string | null;
}

export interface ItemWithLinks extends Item {
  links: Link[];
}

export interface TaskMatch {
  task: TaskRef;
  confidence: number;
  reason: string;
}

export type TriageCondition = 'starts_with' | 'contains';

export interface TriageRule {
  id: string;
  name: string;
  sources: string[];
  condition: TriageCondition;
  value: string;
  enabled: boolean;
}

export interface TriageRuleCreate {
  name?: string;
  sources: string[];
  condition: TriageCondition;
  value: string;
}

export interface TaskCandidate {
  item: Item;
  engine: string | null;
  confidence: number;
  reason: string | null;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  bucket: string;
  status: Status;
  tags: string[];
  unread: boolean;
  origin: Origin;
  archived: boolean;
  updated_at: string;
  items: Item[];
  candidates: TaskCandidate[];
}

export interface NextAction {
  action: string;
  confidence: number;
}

export interface Bucket {
  name: string;
  keywords: string[];
  position: number;
  count: number;
  archived: boolean;
}

export interface PersonIdentity {
  id: string;
  kind: string;
  value: string;
  label: string | null;
}

export interface Person {
  id: string;
  display_name: string;
  email: string | null;
  note: string | null;
  identities: PersonIdentity[];
}

export interface PersonCreate {
  display_name: string;
  email?: string | null;
  note?: string | null;
  identities?: { kind: string; value: string; label?: string | null }[];
}

export interface PersonPatch {
  display_name?: string;
  email?: string | null;
  note?: string | null;
}

export interface IdentityInput {
  kind: string;
  value: string;
  label?: string | null;
}

export type ConfigFieldKind = 'text' | 'secret';

export interface ConfigField {
  key: string;
  label: string;
  kind: ConfigFieldKind;
  required: boolean;
  placeholder: string;
  help: string;
  /** Where this value comes from, "" when the field speaks for itself. */
  help_url: string;
  /** For secrets this is a mask like "••••••••1234", never the value itself. */
  value: string | null;
  is_set: boolean;
}

export type SourceConnectionStatus = 'connected' | 'error' | 'unconfigured';

/** A source you can add. Drives the Add-a-source picker. */
export interface SourceKind {
  kind: string;
  name: string;
  description: string;
  setup: string;
  setup_url: string;
  manifest: string;
  manifest_hint: string;
  detectable: boolean;
  needs_credentials: boolean;
}

/** One source the user added. Several may share a kind, told apart by `name`. */
export interface SourceStatus {
  id: string;
  kind: string;
  name: string;
  position: number;
  description: string;
  status: SourceConnectionStatus;
  detail: string;
  last_checked_at: string | null;
  error: string | null;
  fields: ConfigField[];
  setup: string;
  setup_url: string;
  manifest: string;
  manifest_hint: string;
  detectable: boolean;
}

export interface SourceCreate {
  kind: string;
  name?: string;
}

export interface SourcePatch {
  name?: string;
  position?: number;
}

/** What a local CLI knew. Secrets it found are saved, never returned. */
export interface Detection {
  available: boolean;
  detail: string;
  applied: Record<string, string>;
  choices: Record<string, string[]>;
  source: SourceStatus | null;
}

export interface SyncLogSource {
  source: string;
  kind: string;
  items_fetched: number;
  configured: boolean;
  error: string | null;
}

export interface SyncLogEntry {
  id: number;
  started_at: string;
  finished_at: string | null;
  sources: SyncLogSource[];
  items_fetched: number;
  items_added: number;
  items_updated: number;
  proposals: number;
  tasks_updated: number;
  duration_seconds: number;
  error: string | null;
}

export interface SyncResult {
  sources_synced: string[];
  items_added: number;
  items_updated: number;
  proposals: number;
  tasks_updated: number;
  duration_seconds: number;
  errors: string[];
}

export interface AppSettings {
  app_name: string;
  auto_sync: boolean;
  secret_backend: string;
  secret_backend_is_keychain: boolean;
}

export interface AppSettingsPatch {
  app_name?: string;
  auto_sync?: boolean;
}

export type AICredentialSource = 'keychain' | 'environment' | 'cli-login' | 'claude-cli' | 'none';

export interface AIStatus {
  available: boolean;
  source: AICredentialSource;
  detail: string;
  model: string;
}

export interface BucketSuggestion {
  bucket: string;
  is_new: boolean;
  keywords: string[];
  confidence: number;
  reasoning: string;
}

export interface TaskFilters {
  bucket?: string;
  source?: Source;
  status?: Status;
  unread?: boolean;
  archived?: boolean;
  q?: string;
}

export interface TaskPatch {
  bucket?: string;
  unread?: boolean;
  status?: Status;
  title?: string;
  description?: string | null;
  tags?: string[];
  archived?: boolean;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  bucket?: string;
  tags?: string[];
}

export interface BucketCreate {
  name: string;
  keywords: string[];
  position?: number;
}

export interface BucketPatch {
  keywords?: string[];
  position?: number;
}

export interface BucketArchive {
  cascade_tasks: boolean;
}
