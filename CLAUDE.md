# Personal HQ

A local web app that aggregates your activity across GitHub, Linear, Slack, Dust and local
files (git branches, todo files, markdown docs) and groups it into topics, so you can regain
context on a subject fast.

# Vocabulary

Three words, used consistently in code, API, UI and commits. Never mix them.

- **Item** — one thing from one source: a PR, a Slack thread, a todo line, a branch.
- **Task** — a subject you handle. Items attach to it. An item can attach to several tasks.
- **Bucket** — a topic column on the board. Groups tasks. Created by the user.

Reads as **Bucket > Task > Item**.

# Folders

```
hq/
|-- backend/          # FastAPI + SQLAlchemy (async, SQLite). See backend/README.md.
|   |-- app/
|   |   |-- engine/   # proposes which task an incoming item attaches to
|   |   |-- models.py # Task, Item, Link, Bucket, AppConfig, SyncLog
|   |   |-- routers/  # tasks, buckets, catchup, sync, admin
|   |   |-- security/ # secret storage (OS keychain)
|   |   |-- services/ # sync, catchup, buckets, app_config, ai
|   |   |-- sources/  # one adapter per source; each declares its own config fields
|   |-- alembic/      # migrations
|   |-- tests/
|-- frontend/         # React 19 + Vite + Mantine (stock theme) + TanStack Query
|-- tierces/          # design handoff bundle from Claude Design (read-only reference)
|-- todos/            # the original spec (superseded by tierces/)
```

# Architecture

**Sources never create tasks.** A source adapter emits `RawItem`s and nothing else. Each
declares its own `fields`, which is what lets the Admin panel render a setup form for a
source it has never heard of.

**The engine proposes; the user decides.** Every incoming item goes through
`app/engine/`, which returns `Proposal`s (task + confidence + reason). Engines are chosen
per source in `engine/registry.py`, because sources differ in what they can honestly claim:
a tracker issue names a subject, a chat message only ever points at one. A source with no
entry proposes nothing.

**A `Link` carries the decision.** `proposed` is an engine's guess and is rebuilt on every
sync. `confirmed` and `rejected` are the user's, and sync never touches them. Rejections
persist so an engine cannot re-propose something already dismissed.

**Grouping is global.** The engine sees every task, not just those from the item's source,
so a partial sync still reads other sources' stored items back out of the DB first.

# Linting & Formatting

Backend: ruff (`task back:lint`, `task back:format`). Line length 110, target py311,
rules E/F/I/UP/B/SIM/C4/RUF — config in `backend/pyproject.toml`.
Frontend: eslint + prettier (`task front:lint`).

Scope both to the files you touched. A repo-wide `--fix` rewrites files you didn't touch
and leaves unrelated changes in the tree, which then block the commit.

# Tests

Backend: pytest + pytest-asyncio + respx (`task back:test`). Frontend: vitest +
testing-library + msw (`task front:test`).

Service-level tests don't exercise routing or serialisation — anything that touches an
endpoint needs a test that goes over HTTP.

# Commands

Everything runs through [go-task](https://taskfile.dev); `task --list` shows them all.
Tools come from devbox, so run `devbox shell` (or let direnv do it) first.

```bash
task setup            # install backend + frontend, create and migrate the DB
task dev              # API (:8000) and UI (:5173)
task check            # what CI runs: lint, typecheck, migration drift, tests

task back:test -- -k engine
task back:db-migrate -- "add links table"   # autogenerate a migration
task back:db-check    # fail if models drifted from migrations
task back:sync        # sync from the CLI, no UI
```

# Working with a running app

**When the user already has the app running, read `logs/`; don't start your own.**
`task back:dev` and `task front:dev` tee to `logs/backend.log` and `logs/frontend.log`
(gitignored). That is the shared surface: they get their terminal, you get the file.
Starting a second server means racing them for the port and reading output from a process
that isn't the one in front of them.

Only start servers yourself when nobody else is running the app.

- **`backend/hq.db` is the user's data, not a scratchpad.** Never drive a manual test
  against the default database: syncing a source writes tasks, items and config into it,
  and a demo folder full of invented branches then looks like the user's real work. Point
  `DB_PATH` at a throwaway file and run on another port:
  `DB_PATH=/tmp/hq-probe.db uv run uvicorn app.main:app --port 8011`.
  Same for the app name and source config — both live in that database.

# Specific Guidelines

- Python >3.11 typing: `list[]`, `dict[]`, `X | None`. Don't import from `typing` for these.
- **Comments and docstrings: the default is none.** Add one only when it brings information
  the code cannot: a non-obvious constraint, a gotcha, a rationale. The Why, not the How.
  Then keep it to the length that information needs — a four-line essay on a one-line
  property is noise even when every sentence is true. This one is on the author: no check
  can catch it (length lets essays through; "docstring longer than its function" flags the
  short functions whose subtle constraints most deserve one). Review for it.
- **A comment describes the code as it is now.** Never the history behind it, never the
  project's own trajectory. `# changed to fix…`, `# as discussed`, `# previously a list`
  are all wrong: a future reader has none of that context and shouldn't need it. That
  belongs in the commit message. `bin/check-comments.py` enforces this one, and runs as a
  pre-commit hook.
- Migrations are required. Schema changes go through Alembic
  (`task back:db-migrate -- "…"`); never edit the DB by hand, never rely on `create_all`
  outside tests. Migrations must not import application code — they outlive it.
- Sources degrade gracefully: missing credentials means the source reports itself
  unconfigured in `/admin/sources`, it does not fail the sync.
- HQ reads; it does not author content in a source. No creating Linear issues, no posting
  Slack messages. The one sanctioned write is marking a thread handled — a Slack reaction
  from the board — which is an annotation on your own view, not content others receive. The
  Slack manifest provisions `reactions:write`/`reactions:read` for it; keep that the only
  exception, and keep it opt-in.
- Secrets live in the OS keychain via `app/security/secrets.py` — never in the database, in
  `.env`, or in a log line. The API returns masked hints only.
- Ids travel in URL paths, so they are restricted to URL-safe characters at construction
  (`sources/base.py:url_safe`).
- No default buckets, and no vendor names in bucket keywords. HQ cannot know what someone
  works on, and a wrong guess fills the board with a taxonomy that isn't theirs.

# Commits

- Commitizen / Conventional Commits: `type(scope): subject`.
  Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`, `build`, `style`.
  Scopes: `backend`, `frontend`, `engine`, `sources`, `db`, `tooling`.
- Subject in the imperative, lowercase, no trailing period.
- **Never** append a `Co-Authored-By:` trailer.
- Write the Why in plain language — lead with the problem or impact in one clear sentence.
- PRs open in **draft** (`gh pr create --draft`).
