---
icon: lucide/file-text
---

# Task reports

HQ can export every task as a self-contained Markdown **report** on disk, plus a `task-map.md`
index — so a task's whole context is one file to read, or to hand to another tool. It's a read-only
export: HQ never posts anything back to a source.

Generate them from **Admin → Task reports → Generate task reports** (or `POST /api/tasks/reports`).

## What gets written

Under `~/.hq/` (override with the `HQ_DIR` environment variable):

```
~/.hq/
├── task-map.md                 # every task, most urgent first; archived clearly marked
└── tasks/
    └── {id}/report.md          # one report per task
```

- **`task-map.md`** — a table ordered by priority (highest first): task, status, bucket, an
  **Archived** column, item count, and a link to each report.
- **`tasks/{id}/report.md`** — the task's title, status, bucket, priority, tags and archived flag;
  its description and AI next action; the people involved; then every item with its **full
  content**, not just a link.

## Content, not just links

Reports pull the real content wherever HQ can reach it:

| Source | In the report |
|---|---|
| **GitHub** | The PR/issue body and its comments (review + discussion), fetched live |
| **Linear** | The issue description and comments, fetched live |
| **Slack** | The full message content (kept from the search HQ already runs — no extra scope) + a permalink to the thread |
| **Markdown / todos / notes** | The local file body / the note's text |

Live fetches are best-effort: if one fails, that item falls back to its stored fields (title, link,
status) rather than sinking the whole report.

!!! note "Slack threads"

    Slack shows the **matched message's** content. The complete thread transcript (every reply)
    needs Slack *history* scopes HQ doesn't request, so the report links out to the thread for the
    rest.

## Pointing a tool at it

Because the map is priority-ordered and marks archived tasks, it's a natural work-list: read
`task-map.md`, skip the archived rows, open each report for the full context. Regenerate any time to
refresh — the endpoint rewrites every report and the map.
