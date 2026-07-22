---
icon: lucide/home
---

# Personal HQ

**Personal HQ** aggregates your activity across GitHub, Linear, Slack, Notion, Dust and local
files — git branches, todo files, markdown docs — and groups it into the subjects you actually
work on, so you can regain context on a topic fast instead of tab-hopping across ten tools.

It runs **locally**, on your machine, against your own accounts. It reads by default and only
ever writes to a source on a deliberate action you take — never as a side effect of a sync.

<div class="grid cards" markdown>

- :lucide-layout-dashboard: **One board, every source**

    A PR, a Slack thread, a Linear issue and a local branch about the same subject sit together
    on one task — not scattered across ten tabs.

- :lucide-inbox: **A catch-up inbox**

    Everything you haven't ruled on in one place. The engine proposes where each item belongs;
    you confirm or skip. Triage rules auto-skip the noise.

- :lucide-git-branch: **Code-aware**

    PRs carry their review status; local branches show their git-spice stack; a PR joins the
    branch it was pushed from — the whole stack reads as one card.

- :lucide-brain: **Context on tap**

    Each task carries a precomputed next action and the people it concerns, resolved to one
    identity across sources.

</div>

## The model, in three words

Everything reads as **Bucket → Task → Item**:

- an **Item** is one thing from one source — a PR, a Slack thread, a todo line, a branch;
- a **Task** is a subject you handle, and items attach to it;
- a **Bucket** is a topic column on the board that groups tasks.

See [Concepts](concepts.md) for how the engine proposes attachments and how your decisions are
kept.

!!! tip "Try it without touching your data"

    `task back:seed` builds a throwaway demo database populated across every source, so you can
    explore — or build these docs' screenshots — without ever touching your real `hq.db`. See
    [Getting started](getting-started.md).
