# Personal HQ

A local dashboard that pulls your activity out of GitHub, Linear, Slack, Dust and your own
machine (git branches, todo files, markdown docs) and groups it by subject, so you can pick
a topic back up without hunting through five tabs.

Everything runs on your machine. Nothing is deployed, and no data leaves except the calls
to the APIs you connect.

## What has to be running

Two processes, both local:

| | | |
|---|---|---|
| **Backend** | http://localhost:8000 | FastAPI. Talks to the sources, owns the database. API docs at `/docs`. |
| **Frontend** | http://localhost:5173 | Vite dev server. Useless without the backend — it is a client. |

`task dev` starts both. The frontend calls the backend directly from your browser, so both
must be up; if the UI loads but shows no data, the backend isn't running.

## Getting started

Prerequisites: [devbox](https://www.jetify.com/devbox) (everything else — python, uv, node,
yarn, go-task — is pinned in `devbox.json` and installed by it). Optionally
[direnv](https://direnv.net), so entering the directory activates the toolchain for you.

```bash
devbox shell        # or: direnv allow
task setup          # installs backend + frontend, creates and migrates the database
task dev            # backend on :8000, frontend on :5173
```

Then open http://localhost:5173, go to **Admin**, and connect a source. Nothing is
configured out of the box and nothing is assumed about how you work.

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
for a task (it needs `ant auth login`, or an API key in Admin).

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
the sync. HQ only ever reads — it will not create an issue or post a message.

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
