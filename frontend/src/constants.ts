import type { LinkState, Source, SourceConnectionStatus, Status } from './types';

export const DEFAULT_APP_NAME = 'Mention HQ';

export const UNCATEGORIZED = 'Uncategorized';

/** Cadence at which relative-time labels are recomputed. */
export const CLOCK_TICK_MS = 30_000;

export interface SourceMeta {
  label: string;
  dot: string;
}

export const SOURCE_META: Record<Source, SourceMeta> = {
  pr: { label: 'PR', dot: '#343a40' },
  issue: { label: 'Issue', dot: '#495057' },
  linear: { label: 'Linear', dot: '#7048e8' },
  slack: { label: 'Slack', dot: '#d6336c' },
  branch: { label: 'Branch', dot: '#e8590c' },
  todo: { label: 'Todo', dot: '#0ca678' },
  markdown: { label: 'Doc', dot: '#1c7ed6' },
  dust: { label: 'Dust', dot: '#f08c00' },
  notion: { label: 'Notion', dot: '#212529' },
  notion_mcp: { label: 'Notion MCP', dot: '#495057' },
  note: { label: 'Note', dot: '#5c7cfa' },
};

const UNKNOWN_SOURCE: SourceMeta = { label: 'Source', dot: '#868e96' };

/** A source the backend added but this build has no metadata for still renders. */
export function sourceMeta(source: Source): SourceMeta {
  return SOURCE_META[source] ?? UNKNOWN_SOURCE;
}

/**
 * A source *kind* named the way it's set up in Admin — for the triage-rule source picker,
 * where the short card labels ("PR", "Doc") read as jargon. GitHub emits `pr` and `issue`
 * and Local Git emits `branch`, so those kinds are qualified with their adapter's name.
 */
export const SOURCE_KIND_LABEL: Record<string, string> = {
  pr: 'GitHub PR',
  issue: 'GitHub issue',
  linear: 'Linear',
  slack: 'Slack',
  branch: 'Local Git',
  todo: 'Todo list',
  markdown: 'Markdown docs',
  dust: 'Dust',
  notion: 'Notion',
  notion_mcp: 'Notion MCP',
};

export function sourceKindLabel(kind: string): string {
  return SOURCE_KIND_LABEL[kind] ?? sourceMeta(kind as Source).label;
}

export interface StatusMeta {
  label: string;
  color: string;
  bg: string;
}

export const STATUS_META: Record<Status, StatusMeta> = {
  open: { label: 'Open', color: '#1971c2', bg: '#e7f5ff' },
  in_progress: { label: 'In Progress', color: '#e8590c', bg: '#fff4e6' },
  merged: { label: 'Merged', color: '#2b8a3e', bg: '#ebfbee' },
  done: { label: 'Done', color: '#495057', bg: '#f1f3f5' },
};

const UNKNOWN_STATUS: StatusMeta = { label: 'Unknown', color: '#495057', bg: '#f1f3f5' };

export function statusMeta(status: Status): StatusMeta {
  return STATUS_META[status] ?? UNKNOWN_STATUS;
}

export const CONNECTION_META: Record<SourceConnectionStatus, { label: string; color: string }> = {
  connected: { label: 'Connected', color: 'teal' },
  error: { label: 'Error', color: 'red' },
  unconfigured: { label: 'Not configured', color: 'gray' },
};

export const LINK_STATE_META: Record<LinkState, { label: string; color: string }> = {
  proposed: { label: 'Proposed', color: 'blue' },
  confirmed: { label: 'Confirmed', color: 'teal' },
  rejected: { label: 'Rejected', color: 'red' },
};

export const SLACK_ACCENT = SOURCE_META.slack.dot;

export const TERMINAL_BG = '#0d1117';
export const TERMINAL_BORDER = '#21262d';
export const TERMINAL_TEXT = '#c9d1d9';
export const TERMINAL_MUTED = '#8b949e';
export const TERMINAL_DIM = '#6e7681';
export const TERMINAL_GREEN = '#3fb950';
export const TERMINAL_RED = '#f85149';
export const MONO_FONT = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
