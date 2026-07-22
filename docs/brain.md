---
icon: lucide/brain
---

# The AI brain

The brain is **optional**. Every screen works without it — it only adds three conveniences, and
each is something you trigger, never a background surprise.

## What it does

- **Next action** — for a [task](screens/tasks.md), a one- or two-sentence concrete next step,
  precomputed when the task's items change so it's there when you open it. Backfill them all from
  [Admin → AI](screens/admin.md#ai).
- **Item → task matching** — on demand (**Match** on an item) or in bulk (**Match all** in
  [catch-up](screens/catch-up.md)), it suggests which existing tasks an item belongs to. It only
  proposes above a confidence floor — *no match* is a normal, common answer.
- **Bucket suggestion** — for an Uncategorized task, a bucket (existing or new) with its reasoning.
  It only *suggests*; enrichment will adopt a suggested bucket automatically only when that bucket
  already exists and it's confident — it never invents one for you.

## Which backend it uses

HQ picks the first credential it finds, in this order — so a machine you've already logged into
needs nothing stored:

1. an **API key** you saved in [Admin → AI](screens/admin.md#ai) (kept in the OS keychain);
2. the **environment** (`ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`);
3. a logged-in **`ant auth login`** profile;
4. the local **`claude` CLI** on your PATH (subscription pricing — HQ shells out to it);
5. **none** — the AI features are simply unavailable, and everything else keeps working.

The Admin → AI panel shows which of these is live and the model in use.

## What it's sent

Only your own connected-tool content — task titles, descriptions, buckets, tags, and each item's
source, label, context and extracted ticket references. **Never credentials.** Item content is
treated as context to reason over, not as instructions.
