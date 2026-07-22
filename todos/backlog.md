# Mention HQ — working backlog

Living backlog for the `feat/hq-foundation` branch. The "Shipped" list is a short pointer
to what already works; the "To do" list is what's left, most-wanted first-ish. Each to-do
carries enough context to pick up cold. A running, GitHub-style changelog lives in
`CHANGELOG.md`.

---

## Shipped (on `feat/hq-foundation`)

Sources & sync: GitHub PRs/issues (with review-status pill), Linear issues (assigned,
including **backlog**), Slack (thread grouping, rich rendering), git branches, todos,
markdown. People directory + tab. Triage rules (auto-skip on match).

Catch-up: item→task Match (brain), **auto-match** with a drainable **Match all** +
progress bar + Stop, skipped-items tab, New-task/Attach both file the item away, an
already-attached item shows its task pre-selected in the attach box.

Tasks & board: buckets (create/archive/delete with cascade prompt, change from the board),
resizable sidebar with **group by Flat/Bucket/Tags** and **sort by Date/Priority**, task
**priority (0–100)**, description, candidates panel, brain **next-action**, task preview
popover, archive/delete + bulk.

Timeline: full item feed, attach/create from a row, filters.

AI brain: `claude -p` CLI / API key auto-detected; match ids resolve even when the model
drops the `task:` prefix.

Ops: dated DB backups on migration and from Admin; commit-msg hook blocks assistant
trailers.

---

## ⚠️ Privacy debt (still open)

- **Real names remain in git HISTORY.** HEAD and fixtures are scrubbed, but earlier commits
  on the pushed public branch still contain real colleague names. Truly removing them means
  rewriting history (`git filter-repo` / interactive rebase) and **force-pushing** —
  destructive, needs a go-ahead.

---

## To do

- **People on items and tasks.** Each source exposes people differently — Linear commenters,
  Slack thread participants, GitHub reviewers/assignee/author. Extract them per source into
  a person reference on the item (id/handle/email as available), resolve through the People
  directory, show *who is referred* on each item, and show the merged set of people on the
  task page (union across the task's items).

- **Slack quoted/shared messages.** A Slack message that quotes another (a message "share")
  currently renders as the raw permalink URL. Parse the shared-message attachment and show
  friendly text (author + channel + snippet) instead of the URL.

- **GitHub PR dual review status.** A PR can be both *changes requested* and have a *pending
  review*. Only one badge shows today. Carry and render the combined review state.

- **Bucket identity is its name.** `Bucket.name` is the PK and `Task.bucket` is a plain
  string (no FK) — so no true rename and no referential integrity. Optional refactor: add a
  surrogate `Bucket.id` + `Task.bucket_id` FK, keep `name` as a mutable label. Deferred;
  the workaround is to create a new bucket.

- **AI brain: explicit provider selection + OpenAI.** Currently auto-detects (stored Claude
  key → env → `ant` login → `claude` CLI). Let the user *choose* the provider in Admin and
  add an OpenAI-key provider with structured output.

- **Richer per-source content for next-action.** Next-action runs on item labels/summaries.
  For sharper answers, fetch full content on demand — Slack thread messages, PR review
  comments + CI, Linear description + comments — and feed that to the brain.

---

## Notes / conventions

- Backend `backend/`, frontend `frontend/`. Run inside `devbox`. `task check` = lint + types
  + migration drift + tests. Migrations via `task back:db-migrate -- "…"` (never edit the DB).
- Ports: backend :13000, frontend :13001.
- Never commit real people's names or the employer's identifiers into fixtures.
- Commit style: Conventional Commits; no `Co-Authored-By` trailer (hook-enforced).
