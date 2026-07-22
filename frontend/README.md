# Mention HQ — frontend

React 19 + Vite + Mantine (stock theme) + TanStack Query.

A client and nothing more: no data, no logic the backend doesn't already own. It needs the
backend running at `http://localhost:13000` — see the root `README.md`.

## Running

Node and yarn come from devbox, not your global PATH. From inside `devbox shell`:

```bash
task front:deps    # yarn install
task front:dev     # http://localhost:13001
task front:test
task front:lint && task front:typecheck
```

Point it at a different API with `VITE_API_URL=http://localhost:8011 task front:dev`.

## Views

|              |                                                                       |
| ------------ | --------------------------------------------------------------------- |
| **Board**    | Tasks in bucket columns. Click a column to focus it.                  |
| **Timeline** | Every item, newest first.                                             |
| **Catch-up** | Items you haven't ruled on. Confirm or reject the engine's proposals. |
| **Log**      | Sync history, one line per run.                                       |
| **Admin**    | App name, buckets, source credentials, AI.                            |

## What to know before editing

The vocabulary is **Bucket > Task > Item**, and the code uses those words exactly — see
`CLAUDE.md`. The word "mention" belongs to no one.

Buckets are user-created and `GET /buckets` returns `[]` on a fresh install, so the board
must handle having no columns. Column order comes from each bucket's `position`.

Item ids contain `:` and `~` (`branch:repo:owner~feature`), so `encodeURIComponent` them
before putting them in a URL.

Admin renders each source's form from the `fields` array the API returns, rather than a
form per source. That is what lets a new backend source appear here with a working form.
Secret fields come back masked (`••••••••1234`) and never carry the real value.
