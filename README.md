# Personal HQ

A local dashboard that pulls your activity out of GitHub, Linear, Slack, Dust and your own
machine (git branches, todo files, markdown docs) and groups it by subject, so you can pick
a topic back up without hunting through five tabs.

Everything runs on your machine. Nothing is deployed, and no data leaves except the calls
to the APIs you connect.

## What has to be running

In development, two processes:

| | | |
|---|---|---|
| **Backend** | http://localhost:8000 | FastAPI. Talks to the sources, owns the database. API docs at `/docs`. |
| **Frontend** | http://localhost:5173 | Vite dev server, for hot reload. Useless without the backend — it is a client. |

`task dev` starts both. The frontend calls the backend from your browser, so both must be
up; if the UI loads but shows no data, the backend isn't running.

**Or just one.** `task serve` builds the UI and serves the whole app from the API on
**http://localhost:8000** — one process, one origin, no CORS. That is the better way to
actually *use* HQ; the two-process setup exists for hot reload while developing it.

## Getting started

Prerequisites: [devbox](https://www.jetify.com/devbox) (everything else — python, uv, node,
yarn, go-task — is pinned in `devbox.json` and installed by it). Optionally
[direnv](https://direnv.net), so entering the directory activates the toolchain for you.

```bash
devbox shell        # or: direnv allow
task setup          # installs backend + frontend, creates and migrates the database
task dev            # backend on :8000, frontend on :5173
```

Work from inside `devbox shell` (or let direnv activate it). Node, yarn, uv and ruff come
from devbox and are not on your global PATH — outside it, `yarn dev` and `git commit` both
fail on missing tools rather than on anything being wrong. `task hooks` installs the git
hooks.

Then open http://localhost:5173, go to **Admin**, and connect a source. Nothing is
configured out of the box and nothing is assumed about how you work.

### Running one side at a time

`task dev` runs both, interleaving their logs. To watch one, use two terminals:

```bash
task back:dev     # terminal 1 — http://localhost:8000, API docs at /docs
task front:dev    # terminal 2 — http://localhost:5173, needs the backend up
```

### One process, one port

```bash
task serve        # builds the UI, then serves everything from :8000
```

The API serves `frontend/dist` when a build exists (`app.frontend` in `backend/app/main.py`),
so the SPA and the API share an origin and CORS stops being involved. Client-side routes
like `/task/abc` fall back to `index.html` for a browser navigation, while an API call for
a path that doesn't exist still gets a JSON 404 rather than a page.

There is no single-process equivalent *with* hot reload: that is a websocket Vite owns.

The frontend is only a client: it holds no data and talks to the backend from your browser.
If the UI loads but every panel is empty, the backend isn't running.

The backend needs no frontend at all. **http://localhost:8000/docs** is a full interactive
UI for every endpoint — connect a source, sync, read the board — which is the quickest way
to see what the app does, and the way to tell a frontend bug from a backend one.

### Frontend on its own

```bash
task front:deps       # yarn install
task front:dev        # dev server on :5173, hot reload
task front:test       # vitest, once
task front:test-watch # vitest, watching
task front:lint
task front:typecheck
task front:build      # type-check and production build
```

It expects the API at `http://localhost:8000`. Point it elsewhere with `VITE_API_URL`:

```bash
VITE_API_URL=http://localhost:8011 task front:dev
```

No credentials go in a file. You paste tokens into Admin and they are stored in your OS
keychain (Keychain on macOS, Credential Locker on Windows, Secret Service on Linux). The
API only ever hands back a masked hint like `••••••••1234`.

The local sources need no credentials at all, so the fastest way to see the app do
something is to point **Local Git** at a repo or **Todo list** at a markdown file, and hit
Sync.

## The idea

Three words, used everywhere:

- **Item** — one thing from one source: a PR, a Slack thread, a todo line, a branch.
- **Task** — a subject you handle. Items attach to it, and one item can attach to several.
- **Bucket** — a topic column on the board, grouping tasks.

Reads as **Bucket > Task > Item**.

When an item arrives it goes through an **engine**, which *proposes* which task it belongs
to and says why. It never decides. Proposals show up in **Catch-up**, where you confirm or
reject them; your answer is remembered, and a later sync will not undo it or re-propose
something you dismissed.

Buckets start empty on purpose — HQ can't know what you work on, and a wrong guess fills
the board with someone else's taxonomy. Create them in Admin, or ask Claude to suggest one
for a task (it needs an API key in Admin, or a local `ant auth login`).

## Sources

| Source | Needs | Provides |
|---|---|---|
| GitHub | token, username, org | your open PRs and assigned issues |
| Linear | API key | issues assigned to you |
| Slack | user token (`search:read`) | threads you wrote in or were mentioned in |
| Local Git | repo paths | branches you're working on |
| Todo list | file globs | unchecked todo lines |
| Markdown docs | file globs | local docs, attached to the subjects they mention |
| Dust | — | not implemented yet |

A source with no credentials reports itself unconfigured and is skipped; it never fails
the sync. A sync only ever reads. The one place HQ can write is Slack — its app can be
granted scopes to react to or reply to a thread from the board — and only on your action,
never automatically.

## Commands

`task --list` shows everything.

```bash
task dev              # both processes
task check            # what CI runs: lint, typecheck, migration drift, tests
task back:dev         # backend alone
task front:dev        # frontend alone (needs the backend up)
task back:sync        # sync from the CLI, without the UI
task back:db-reset    # delete the local database and rebuild it
task hooks            # install the pre-commit hooks
```

## Layout

```
backend/    FastAPI + SQLAlchemy (async) + SQLite. See backend/README.md.
frontend/   React + Vite + Mantine.
tierces/    Design handoff bundle. Reference, not code.
todos/      The original spec. Superseded by the design.
```

`CLAUDE.md` holds the conventions and the architecture in more depth.

## License

MIT — see [LICENSE](LICENSE). Use it freely, at your own risk.
