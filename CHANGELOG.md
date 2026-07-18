# Changelog

All notable changes to Personal HQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it cuts releases.

## [Unreleased]

### Added

- Sources: GitHub PRs/issues, Linear issues (assigned — including backlog), Slack (one item
  per thread, rich markup/emoji rendering), Notion (pages you created, own, or a comment
  mentions you in), git branches, todos, markdown.
- Brain dump: a distraction-free page (and an always-present button in the header) to type
  a thought straight into an item, optionally filed onto tasks as you submit it; notes stay
  editable in place from the task or catch-up.
- People directory and tab: one person per human with handles across sources; add, edit,
  merge and delete; sources resolve ids through a shared, cached directory. Items now carry
  the people they concern (PR author/assignees/reviewers, Linear assignee/creator, Slack
  mentions, Notion creator/owner/mentions), shown as a people strip on the item and task.
- Delete an item outright from the timeline — for clearing out what a since-removed source
  left behind.
- Slack: map your org's custom (non-standard) emoji to image URLs in the source config, so
  `:custom-emoji:` renders as the picture instead of the code.
- Catch-up: brain-powered item→task matching, automatic matching with a drainable "Match
  all" (live progress bar + Stop), triage rules that auto-skip noise, and a skipped-items
  tab that can un-skip.
- Tasks: priority (0–100) with sort by date or priority; group the sidebar by bucket, tags
  or flat; description; a candidates panel of proposed items; a brain "next action"; and a
  task-preview popover from a catch-up proposal.
- Precomputed context: creating or confirming a task kicks off a background pass that writes
  its "next action" and, for a new or still-uncategorised task, adopts the brain's
  recommended bucket when it's confident — so the task is already framed when you open it. A
  one-click backfill runs it for existing tasks.
- Board: create, archive and delete buckets (with a cascade-to-tasks prompt) and change a
  task's bucket from its card.
- Timeline: a full feed of every item with attach/create-from-row and column filters.
- PR items show their review/merge status as a pill.
- AI brain: the local `claude` CLI is a detected engine alongside a Claude/OpenAI API key.
- Ops: dated database backups on migration and from the Admin screen.

### Changed

- Creating a task from an item, or attaching it, now files the item out of the inbox
  (attached means handled).
- An already-attached catch-up item shows its task pre-selected in the attach box instead
  of a separate CONFIRMED badge.

### Fixed

- Brain matches whose task id dropped the `task:` prefix are no longer discarded, so
  confident matches actually land.
- Linear issues assigned to you in a backlog state are fetched, not only active ones.
- Background brain matching no longer blocks a sync or locks the SQLite database.
- The board no longer crashes when a bucket is named "Uncategorized", and picking a bucket
  from a card no longer navigates to the task.
- Slack usergroup mentions like `<@S…|mo-crew>` render as their label instead of a raw id,
  and custom emoji resolve against a workspace-wide map so an item already in a task picks
  up an emoji added to the config afterwards.

[Unreleased]: https://github.com/lakodo/mention-hq/commits/feat/hq-foundation
