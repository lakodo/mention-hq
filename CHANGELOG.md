# Changelog

All notable changes to Mention HQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-21 — "GitHubris"

### Added

- **Local Git branches, with git-spice stacks.** The Local Git source reads
  [git-spice](https://github.com/abhinav/git-spice) stack state straight from the repo's refs
  and draws each stacked branch as a trail — the whole downstack chain, with the branch you're
  on highlighted. Repo paths can be filled by browsing the filesystem instead of typed, with
  git repositories marked.
- **The task screen splits into two lanes.** Slack and the rest of your activity on the left, a
  **Code** lane on the right for PRs and branches — where a PR and the local branch it was
  pushed from collapse into a single card. The detail also uses the width it has.
- **Install HQ as an app.** A web manifest and service worker make HQ a PWA: install it and it
  opens in its own standalone window, outside the browser. It works from `task dev` behind the
  Caddy HTTPS proxy — the way HQ actually runs — not just a production build.
- **A welcome screen behind the logo.** Clicking the app title lands on a home: a greeting, a
  catch-up call-to-action with the count when the inbox has items, and your five highest-priority
  tasks, each a shortcut to its detail.
- **A deleted branch reads as gone.** A branch you filed on a task and later delete locally is
  struck through and pilled **deleted** rather than lingering as if it were still live — attached
  branches included, since sync keeps them. A recreated branch clears the flag.

### Fixed

- An item you've attached no longer returns to catch-up when it gathers new activity. A branch
  you filed picking up commits — or any filed item that moves — stays put; only items you
  haven't filed still resurface on new activity.

## [1.0.1] - 2026-07-20

### Added

- Jump to the current screen's search box with **⌘K** (⌃K off macOS) — the header search on the
  board, catch-up and timeline; the task-list search on Tasks.

### Fixed

- A merged PR no longer vanishes from a task. Sync never deletes an item you've attached to a
  task — a source dropping it (a merged PR leaving GitHub's `is:open` search, a closed thread)
  can't remove your decision. Merged PRs are also fetched to refresh a PR you've already filed,
  shown with a **Merged** pill, without flooding catch-up with every recent merge.

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

[1.1.0]: https://github.com/lakodo/mention-hq/releases/tag/v1.1.0
[1.0.1]: https://github.com/lakodo/mention-hq/releases/tag/v1.0.1
[1.0.0]: https://github.com/lakodo/mention-hq/releases/tag/v1.0.0
