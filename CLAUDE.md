# Personal HQ

Local web app aggregating your activity across GitHub, Linear, Slack, Dust and local files
(git branches, todos, markdown docs) into topic buckets, so you can regain context on a subject fast.

## Working rules

These come first because they apply to every change in this repo.

### Don't paraphrase code

The default is **no comment and no docstring**. Add one only when it carries information the code
cannot: the *Why* — a non-obvious constraint, a gotcha, a rationale. A comment restating what the
next line plainly does is noise, and it rots.

```python
# Bad — restates the code
# Loop over the mentions and merge them
for mention in mentions: ...

# Good — explains a constraint the code can't show
# Slack search returns the same thread once per matching message; dedupe on thread_ts.
```

A comment must never narrate change history ("changed to fix…", "now does X instead of Y",
"as discussed"). That belongs in the commit message.

### Commits

- Follow the **Commitizen / Conventional Commits** convention: `type(scope): subject`.
  Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`, `build`, `style`.
  Scopes used here: `backend`, `frontend`, `sync`, `sources`, `db`, `tooling`.
- Subject in the imperative mood, lowercase, no trailing period: `feat(sources): add linear source`.
- **Never** append a `Co-Authored-By:` trailer.
- Write the *Why* in plain language — lead with the problem or impact in one clear sentence,
  keep jargon to what actually adds value.

### Pull requests

Always open PRs in **draft** (`gh pr create --draft`); the user marks them ready themselves.

### Before committing

Hooks run lint + tests on staged files only. Run the same checks yourself first, scoped to the
files you touched — never repo-wide auto-fix, which pollutes the tree with unrelated rewrites.

## Architecture

**A task is a subject; a mention is one appearance of it in one source.** One task, many mentions.
This is the single most important idea in the codebase, and the main way it departs from
`todos/personal-hq-specs.md` (stale — the design in `tierces/` supersedes it).

A PR, a Slack thread and a local todo that all concern the same refund bug are three
`mentions` rows linked to one `tasks` row. Sources never create tasks directly: they emit
`RawMention`s carrying identity/reference keys, and `services/grouping.py` merges them via
union-find into tasks. That keeps grouping logic in one testable place instead of smeared
across eight source adapters.

**A mention can belong to several tasks.** A thread that argues about two subjects is about
both, so `task_mentions` is many-to-many. Sync recomputes automatic links every run, then
replays the user's `link_overrides` on top — that separation is what lets sync be
destructive about its own guesses without ever destroying a human's.

```
backend/app/
  models.py            Task, Mention, SyncLog
  sources/             one adapter per source; each returns list[RawMention]
  services/grouping.py mentions -> tasks (union-find over identity/reference keys)
  services/sync.py     orchestrates sources, persists, preserves manual overrides
  routers/             tasks, buckets, sync, admin
frontend/src/
  views/               Board, Timeline, Log, Admin, ItemDetail
  hooks/               TanStack Query wrappers
```

## Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2 async + aiosqlite, Alembic, `uv` for deps.
- **Frontend**: React 19, TypeScript, Vite, Mantine 8 (stock theme), TanStack Query v5, `yarn` for deps.
- **Tests**: pytest + pytest-asyncio + respx (backend), vitest + testing-library + msw (frontend).

## Commands

Everything runs through [go-task](https://taskfile.dev) — `task --list` shows them all.
Prefer these over raw `uv`/`yarn` invocations so the steps stay in one place.

```bash
task setup            # install backend + frontend, create and migrate the DB
task dev              # run API (:8000) and UI (:5173) together
task check            # what CI runs: lint, typecheck, migration drift, tests

task back:dev         # API only
task back:test -- -k grouping
task back:db-migrate -- "add tags to tasks"   # autogenerate a migration
task back:db-check    # fail if models drifted from migrations
task back:db-reset    # nuke and rebuild the local DB
task back:sync        # sync from the CLI, no UI

task front:dev
task front:test
task front:lint
```

## Conventions

- **Migrations are required.** Schema changes go through Alembic (`uv run alembic revision --autogenerate -m "..."`);
  never edit the DB by hand and never rely on `create_all` outside tests.
- Sources must degrade gracefully: missing credentials means the source reports itself
  unconfigured in `/admin/sources`, it does not fail the whole sync.
- No writes back to sources. HQ reads; it never creates a Linear issue or posts to Slack.
- Secrets live in `.env` (gitignored). `.env.example` documents every key.
