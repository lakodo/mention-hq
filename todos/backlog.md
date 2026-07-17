# Personal HQ — working backlog

Living backlog for the `feat/hq-foundation` branch. Everything below the "Shipped"
section is still to do, most-wanted first-ish. Each item carries enough context to pick
up cold.

---

## Shipped this cycle (on `feat/hq-foundation`, pushed)

- **People directory + tab.** `Person` + `PersonIdentity(kind, value)` tables; `/api/people`
  (list/create/get/patch/merge/identities/delete); People tab (add/edit/merge/delete, add &
  remove handles). Source-agnostic: a `PeopleDirectory` the sync hands to sources so Slack
  resolves user ids to names once and caches them (never re-asks). Merge folds duplicate people.
- **Slack rendering.** Mentions/links/channels/`<!here>`/emoji shortcodes rendered; app/bot
  messages read from Block Kit `blocks`/`attachments` (no more "(no text)"); **one item per
  thread** (grouped by the thread root parsed from the reply permalink); labels are now
  `#channel - message[:50]` (or `DM with @x - …`).
- **Catch-up.** Clearable header search (✕) + empty-state "Clear search"; bucket dropdown in
  the New-task modal no longer clipped; new task appears in the attach list without a refresh;
  **item titles link out** to Linear/Slack/PR; **New task keeps the item in the inbox** (so you
  can attach it elsewhere first — confirm/skip is what files it); **items with a proposal float
  to the top**.
- **Board / Buckets.** Create a bucket from the board (New-bucket column + empty-state button);
  Uncategorized column leads.
- **Tasks.** Resizable left sidebar (drag divider, width persisted); archive & delete a task
  (delete frees items back to Catch-up; archive keeps them filed), per-row menu + bulk select.
- **Timeline.** Shows *all* items (own `/api/items` feed), clickable task badges, "To triage"
  badge; column-filter header (source multiselect, text, task-state, newest/oldest sort).
- **Settings.** Auto-sync now persisted in `app_config` (survives reload), like the app name.
- **AI brain.** `claude -p` CLI is now a detected engine (subscription-priced) alongside a
  Claude/OpenAI API key — fixes "Suggest bucket" failing with no key. Runs `claude -p … --output-format json`,
  parses the result against the schema. Credential order still prefers a stored key.
- **Log** opens scrolled to the newest run.
- **Housekeeping.** A `commit-msg` hook rejects assistant-attribution trailers. Scrubbed real
  colleague names / employer identifiers out of fixtures & tests (→ Ada Lovelace, Grace Hopper,
  Katherine Johnson, `acme/webapp`). Modal dropdowns portal so options stop clipping.

---

## ⚠️ Privacy debt (do this)

- **Real names remain in git HISTORY.** HEAD is scrubbed, but earlier commits on the pushed
  public branch (`lakodo/mention-hq`) still contain the real colleague names. To truly remove
  them: rewrite history (same search/replace via `git filter-repo` or an interactive rebase)
  and **force-push**. Destructive (rewrites SHAs) — needs a go-ahead. Names/strings to replace
  are the same set already applied to HEAD.

---

## Backlog (features)

- **Delete & archive a bucket, with a "cascade to its tasks?" prompt.** (Next up; not started —
  the tree is clean.) Plan: add `Bucket.archived_at` (nullable) + migration.
  `DELETE /buckets/{name}?cascade_tasks=bool` — if true delete the bucket's tasks, else rehome
  to Uncategorized (current behaviour). `POST /buckets/{name}/archive {cascade_tasks}` — set
  `archived_at`; if cascade archive its tasks (`task.archived_at`), else rehome. Add restore.
  `list_buckets` excludes archived (board hides them); board column header gets a ⋮ menu
  (Archive / Delete) opening a confirm with a checkbox "Also [archive/delete] its N tasks" shown
  only when the bucket has tasks.

- **Change a task's bucket from the board.** A control on the task card (drag-and-drop is
  fiddly to build/test — prefer a button/menu on the card that opens a bucket picker →
  `PATCH /tasks/{id} {bucket}`).

- **PR items: show status.** Surface draft / ready-for-review / changes-requested / merged /
  closed on PR items (a status pill). GitHub source already fetches PRs — extend it to carry
  the review/merge state into `RawItem.status`/extra, and render a pill on the item rows
  (Catch-up, Timeline, Task detail).

- **Next-action proposal on the task screen (brain).** A button on a task that asks the brain
  to predict the next action, using the *full* content of the task's items — not just labels:
  - Slack: fetch the whole thread (messages + author names + times).
  - GitHub PR: state, review comments, CI status/errors.
  - Linear: description + comments with dates.
  Feed all of that to the brain engine and return a short "next action" (may be implied in a
  comment, or nothing clear — that's the brain's job). Needs richer per-source content
  fetching (a "detail"/"expand" fetch beyond the summary `RawItem`), then a brain call.

- **Task attach/create from a Timeline row.** Same actions as Catch-up (attach to task(s) /
  new task), from a timeline row. Reuse `useConfirmLinks` / `useCreateTaskFromItem`. Probably a
  per-row menu or inline controls; keep the row compact.

- **Candidate items inside the task view.** While working a task, show *proposed* links
  (candidate items the engine guessed for this task) so you catch new elements without going
  through full triage. Compact by default — a small notification/count that expands the list;
  each candidate has confirm/reject. Needs the task detail to fetch proposed links for the task
  (currently the task only shows confirmed items).

- **Review a proposed task before confirming (from Catch-up).** From a proposal in Catch-up,
  open the target task to review it before confirming — ideally a task **preview modal** (nicer
  than opening in a new tab / `_blank`).

- **Triage rules (from Catch-up).** "Add a triage rule" button + modal on Catch-up. Classic
  conditions to start: source (multiselect or `*`), starts-with, contains. A matching incoming
  item is auto-skipped (triaged) by the rule. Needs a `TriageRule` model + a rule engine applied
  on sync/ingest, and the item's skip reason recorded (see below).

- **Skipped items view + reasons.** See skipped (triaged-without-a-task) items and *why* each
  was skipped — manually vs by which rule. Record a skip reason on the item (new field, e.g.
  `triage_reason`). Default the view to the last week; make the window customizable in the
  frontend.

- **Slack thread items: richer meta.** For items that come from a thread, show how many
  messages are in the thread and who is speaking (participants). Needs `conversations.replies`
  (manifest already grants the history/read scopes) to get reply count + participant names;
  resolve names via the People directory.

- **AI brain: explicit provider selection + OpenAI.** Currently auto-detects (stored Claude key
  → env → `ant` login → `claude` CLI). Finish the "3 interchangeable engines" from the original
  spec: let the user *choose* the provider in Admin, and add the OpenAI-key provider
  (`_suggest_via_openai`) with structured output. The `claude -p` path is already in
  `app/services/ai.py` as `_suggest_via_cli`.

---

## Notes / conventions

- Backend `backend/`, frontend `frontend/`. Run inside `devbox`. `task check` = lint + types +
  migration drift + tests. Migrations via `task back:db-migrate -- "…"` (never edit the DB).
- Ports: backend :13000, frontend :13001. `task up` runs both + the Caddy proxy at your bare
  domain (see `ops/Caddyfile.example`, `task proxy:set`).
- Never commit real people's names or the employer's identifiers into fixtures.
- Commit style: Conventional Commits; no `Co-Authored-By` trailer (hook-enforced).
