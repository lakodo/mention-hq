---
icon: lucide/plug
---

# Sources

A **source** is an adapter that emits [items](concepts.md) and nothing else — it never creates
a task. Each declares its own configuration, so the [Admin](screens/admin.md) panel can render a
setup form for a source it has never seen. Two rules hold for every source:

- **Graceful degradation** — a source with missing or wrong credentials returns nothing and
  reports itself *unconfigured*; it never fails the sync.
- **Read by default** — HQ only writes to a source on a deliberate action you take from the
  board, never as part of a sync.

Connect and configure sources under **Admin → Connected sources** (you can connect the same kind
more than once — a work GitHub and a personal one).

## At a glance

| Source | Brings | Auth | Notes |
| --- | --- | --- | --- |
| **GitHub** | Open PRs you authored, recently-merged PRs, assigned issues | Personal access token (`repo` scope) | Auto-detects everything from the `gh` CLI; review status; joins a PR to its local branch |
| **Linear** | Issues assigned to you (backlog → started) | Personal API key (read-only) | User id auto-resolved from the key |
| **Slack** | Threads you wrote in or were mentioned in | User token (`xoxp-`, `search:read`) | One item per thread; rich markup & emoji |
| **Notion** | Pages you created, own, or are mentioned in | OAuth **or** a pasted token | Token refreshes itself |
| **Notion MCP** | Notion pages over the hosted MCP server | Dynamic client registration + PKCE | No admin-provisioned app needed |
| **Local Git** | Branches in local repos | None (reads the machine) | git-spice stacks; deleted-branch detection |
| **Todo list** | Unchecked todo lines in local files | None | `- [ ]`, `TODO:`, `☐` |
| **Markdown docs** | Local docs & specs | None | Title from the first heading |
| **Dust** | — | — | **Not implemented yet** — a deliberate stub |

## GitHub

Fetches, for the org you name: **open PRs you authored**, **PRs you merged in the last 14 days**,
and **open issues assigned to you**. A merged PR is *refresh-only* — it updates a PR you've
already filed (so it shows a **Merged** pill) without flooding [catch-up](screens/catch-up.md)
with every recent merge.

- **Config:** a personal access token (secret, needs the `repo` scope), your **username**, and
  the **organisation**.
- **Detect:** if the [`gh`](https://cli.github.com/) CLI is installed and logged in, press
  **Detect** and there's nothing to type — HQ reads the token, username and your org list from it.
- **Review status:** each open PR carries `draft` / `changes requested` / `approved` /
  `review required`, plus whether a reviewer is still pending — shown as a pill on the item.
- **Code-aware:** a PR carries the **head branch** it was pushed from, so the
  [task's Code lane](screens/tasks.md#the-code-lane) can join it to your local branch.
- **People:** author, assignees and reviewers, each with their GitHub avatar.

## Linear

Fetches **issues assigned to you** that are in backlog, triage, unstarted or started. Read-only —
HQ never writes to Linear.

- **Config:** a personal **API key** (secret; a read-only key is enough). Your Linear **user id**
  is optional — leave it blank and **Test connection** looks it up from the key.
- **Cross-linking:** an item is keyed by its issue identifier (e.g. `ENG-123`) *and* the issue's
  branch name, so a local branch named after the ticket matches it.

## Slack

Fetches threads from the last 14 days that **you wrote in** or **were mentioned in** — one item
per thread, not per message.

- **Config:** a **user token** (`xoxp-`, with `search:read`) — a bot token can't search. Your
  user id is optional (detected from the token). Optionally paste space-separated **custom-emoji
  image URLs** so `:your-emoji:` renders as a picture.
- **Setup:** created from an app **manifest** you paste into Slack; installation may need admin
  approval.
- **Rich rendering:** mentions, channels, links and standard emoji (`:fire:` → 🔥) are resolved;
  message text is pulled even from bot/app posts and shared-link unfurls.
- **Writing:** the manifest also requests `chat:write` and `reactions:write` so a future board
  action can reply or react *as you* — but **no write ever fires during a sync**.

Slack never names a subject, so it only ever *references* other items (a ticket ref in a
thread) — it never wins a task's title.

## Notion

Fetches recently-edited pages where **you** are the creator, owner, a commenter, or are mentioned.
Read-only.

- **Two ways to connect:** a **Connect** button runs the OAuth consent flow (the access token
  then refreshes itself), or paste a **personal token** where your workspace allows it.
- The **redirect URI** to register is shown on the source card, detected from your own host — so
  it works behind a proxy or custom domain, not just localhost.

## Notion MCP

A second Notion source, over the hosted **MCP server** (`mcp.notion.com`). It exists for
workspaces where an admin blocks tokens and OAuth apps: HQ **registers itself on the fly**
(dynamic client registration + PKCE), needing no admin-provisioned credential.

- **Config:** your **name / email** (so full-text search can flag pages that mention you, even
  written plainly in a table with no @-handle) and optional **search terms** for other subjects.
- There is no "list everything" mode — with neither a name nor a term, it fetches nothing.

## Local Git

Reads the **branches** of the local repositories you point it at — no credentials, it reads the
machine.

- **Config:** comma-separated **absolute repo paths** (with a filesystem **browse** picker), an
  optional **branch prefix** (branches with it are always included, however old), and a
  **max-age** in days (default 30) for the rest.
- **git-spice stacks:** stacks are read directly from git-spice's own ref (no `gs` CLI needed)
  and drawn as a tree in the [Code lane](screens/tasks.md#the-code-lane).
- **Deleted-branch detection:** every branch that still exists is reported, so a branch you filed
  that's since been deleted is shown struck through rather than lingering as if it were live.

## Todo list & Markdown docs

Two local-file sources, each configured with comma-separated **glob patterns**:

- **Todo list** — every unchecked todo line (`- [ ]`, `* [ ]`, `TODO:`, `☐`, `•`). A todo's id
  hashes its *text*, so inserting a line above doesn't re-create every item.
- **Markdown docs** — one item per file, titled from its first heading (else the filename). Only
  the first part of a doc is scanned for ticket references, so a doc citing the whole backlog
  doesn't merge unrelated subjects.

## Dust

**Not implemented yet.** The adapter is a deliberate stub: with no API to build against, it shows
no config form and reports itself unconfigured rather than asking for credentials nothing would
use.

## How an item finds its task

Sources emit items; the **engine** proposes which task each belongs to, and grouping is global —
the engine sees every task, so a Slack thread can join a task first built from a PR. Two engines
run, and the strongest claim wins:

- **Key engine** — matches the ticket references and identifiers an item and a task share. If
  both *name* the same ticket it proposes at **100%**; if the item merely *references* a key the
  task owns, **90%**. An explicit ticket reference is a deliberate act, so it's trusted.
- **Title similarity** — a fuzzy match of normalised titles (conventional-commit prefixes and
  branch-owner prefixes stripped), capped below a key match so a lookalike title can never beat a
  real reference.

Not every source uses both: **Slack** and **Dust** are key-only (chat text fuzzy-matched against
titles produces confident nonsense), and **todos** are title-only. Every proposal carries its
engine, confidence and reason, shown in [catch-up](screens/catch-up.md) so it's arguable rather
than magic. See [Concepts](concepts.md) for how your confirm/reject decisions are kept.
