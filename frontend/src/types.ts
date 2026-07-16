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

export interface Task {
  id: string;
  title: string;
  bucket: string;
  status: Status;
  tags: string[];
  unread: boolean;
  origin: Origin;
  updated_at: string;
  items: Item[];
}

export interface Bucket {
  name: string;
  keywords: string[];
  position: number;
  count: number;
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
  tasks_added: number;
  tasks_updated: number;
  duration_seconds: number;
  error: string | null;
}

export interface SyncResult {
  sources_synced: string[];
  tasks_added: number;
  tasks_updated: number;
  duration_seconds: number;
  errors: string[];
}

export interface AppSettings {
  app_name: string;
  secret_backend: string;
  secret_backend_is_keychain: boolean;
}

export type AICredentialSource = 'keychain' | 'environment' | 'cli-login' | 'none';

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
  q?: string;
}

export interface TaskPatch {
  bucket?: string;
  unread?: boolean;
  status?: Status;
  title?: string;
  tags?: string[];
}

export interface TaskCreate {
  title: string;
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

/** A single item lifted out of its task, for the flat Timeline feed. */
export interface ItemRow {
  key: string;
  task: Task;
  item: Item;
}
