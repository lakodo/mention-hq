# Changelog

All notable changes to Personal HQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-18 — "Notion Sickness"

The first release. HQ aggregates your activity across GitHub, Linear, Slack, Notion, Dust and
local files (git branches, todos, markdown docs) and groups it into tasks on a board, so you
can regain context on a subject fast. It reads by default and writes to a source only on a
deliberate action you take — never as a side effect of a sync.

### Sources

- **GitHub** (PRs and assigned issues, with review/merge status as a pill), **Linear** (issues
  assigned to you, including backlog), **Slack** (one item per thread, rich markup and emoji
  rendering), **Notion**, **Notion MCP**, **Dust**, **git branches**, **todo files** and
  **markdown docs**. Each adapter declares its own config, so the Admin panel can set it up.
- **Notion over OAuth** for workspaces where an admin blocks static tokens: a Connect button
  runs the consent handshake, the redirect URI is detected from your own host (so it works
  behind a proxy or custom domain, not just localhost), and the access token refreshes itself.
  A pasted personal token still works where that's allowed.
- **Notion MCP** — a second Notion source over the hosted MCP server (mcp.notion.com). It
  registers HQ as an OAuth client on the fly (dynamic client registration + PKCE), needing no
  admin-provisioned token or app at all. It finds pages that **mention you** — full-text
  search catches your name even written plainly in a table with no @-handle — plus pages
  matching topic search terms.
- **Slack custom emoji**: map your org's non-standard emoji to image URLs in the source
  config so `:custom-emoji:` renders as the picture.

### Capture & catch-up

- **Catch-up inbox** of everything you haven't ruled on: item→task matching (a keyword/title
  engine and the AI brain), a drainable **Match all** with a live progress bar and Stop,
  **triage rules** that auto-skip noise, and a skipped-items tab you can un-skip from.
  Confirming a proposed match stages it in the attach box so you can add more before filing.
- **Brain dump**: a distraction-free page (and an always-present header button) to type a
  thought straight into an item, optionally filed onto tasks as you submit it; notes stay
  editable in place.
- **Manual links**: a brain dump can carry a URL and title, becoming a clickable item whose
  typed text is its description — which feeds the AI next-action.
- **Delete an item** outright from the timeline, for clearing out what a since-removed source
  left behind.

### Tasks & board

- **Tasks** with priority (0 to 100, sortable by date or priority), a sidebar grouped by
  bucket, tags or flat, a description, a candidates panel of proposed items, and an AI
  **next action** (a card with its own refresh).
- **Precomputed context**: creating or confirming a task kicks off a background pass that
  writes its next action and, for a new or still-uncategorised task, adopts the brain's
  recommended bucket when it's confident. A one-click backfill runs it for existing tasks.
- **Buckets**: create, archive and delete (with a cascade-to-tasks prompt), change a task's
  bucket from its card, and get a bucket suggestion right next to an uncategorised task.
- **Timeline**: a full feed of every item, with attach / create-from-row and column filters.

### People

- **People directory and tab**: one person per human with handles across sources; add, edit,
  merge and delete; sources resolve ids through a shared, cached directory. Every author,
  assignee and mention an item names is ingested here automatically.
- **Avatars**: items carry the people they concern, shown as a people strip that resolves
  through the directory — so one human across Slack and GitHub collapses to a single avatar.
  Sources carry images where they're free (GitHub, Linear), and you can **choose a person's
  avatar** from their platform images or a pasted URL.

### Platform & ops

- **AI brain**: the local `claude` CLI is a detected engine alongside a Claude/OpenAI API key;
  next-action and matching treat item content as your own trusted context.
- **Secrets** live in the OS keychain, never the database or a log line.
- **Backups**: a dated database copy on every migration and from the Admin screen.
- **Local HTTPS**: serve the whole app under your own local domain with Caddy's built-in CA
  (`tls internal`), which also makes strict OAuth redirect URIs work.
- **Auto-sync** runs hourly in the background; a manual Sync button is always there.

[1.0.0]: https://github.com/lakodo/mention-hq/releases/tag/v1.0.0
