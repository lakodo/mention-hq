---
icon: lucide/plug
---

# Sources

Each source is an adapter that emits items and declares its own configuration, so the Admin
panel can set up a source it has never seen. A source with missing credentials reports itself
**unconfigured** — it never fails the sync. HQ reads by default; it writes to a source only on a
deliberate action you take from the board.

| Source | What it brings | Notes |
| --- | --- | --- |
| **GitHub** | PRs you authored and issues assigned to you | Review / merge status as a pill; a PR carries the head branch it was pushed from |
| **Linear** | Issues assigned to you, backlog included | Matches on the issue key and its branch name |
| **Slack** | One item per thread | Rich markup and emoji rendering; custom emoji map to images |
| **Notion** | Pages that mention you | Static token, or OAuth where an admin blocks tokens |
| **Notion MCP** | Pages over the hosted MCP server | Registers HQ on the fly (dynamic client registration + PKCE) — no admin-provisioned app |
| **Dust** | Assistant conversations | |
| **Local Git** | Branches in local repositories | git-spice stacks detected automatically; browse to pick repo paths |
| **Todo files** | Unchecked todo lines | From globs you configure |
| **Markdown docs** | Local markdown documents | Title from the first heading |

## Code sources join up

PRs and local branches share a **Code** lane on each task. A PR joins the local branch it was
pushed from, and a git-spice stack of PRs collapses into one card — the tree from the GitHub
stack comment. A branch you filed that's deleted from the repo is shown struck through, rather
than lingering as if it were live.

## Reading vs. writing

Everything is **read-only by default**. Slack is the one source provisioned with write scopes
(`chat:write`, `reactions:write`) so you can react to or reply to a thread from HQ — but only on
an explicit action, never as part of a sync.

## People

Every author, assignee and mention an item names is folded into a shared **people directory**,
so one colleague — a Slack id, a GitHub login and an email at once — collapses to a single
person, and a name learned from one source answers for all.
