# Mention HQ - Project Specs

## Overview

A local web app that aggregates your personal activity across Linear, Slack, GitHub, and local files, then groups items into topic buckets so you can quickly get context and resume work on any subject.

- **Backend**: Python + FastAPI
- **Frontend**: React 19 + Mantine 8 + TanStack Query
- **Database**: SQLite (via SQLAlchemy, async with `aiosqlite`)
- **Runtime**: Fully local, no cloud deployment

---

## Project Structure

```
personal-hq/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── config.py                # Settings (API tokens, bucket config path)
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── models.py                # SQLAlchemy ORM models
│   ├── schemas.py               # Pydantic schemas (request/response)
│   ├── routers/
│   │   ├── items.py             # GET /items, GET /items/{id}, PATCH /items/{id}
│   │   ├── buckets.py           # GET /buckets
│   │   └── sync.py              # POST /sync (trigger full or partial sync)
│   ├── sources/
│   │   ├── base.py              # Abstract base class for sources
│   │   ├── github.py            # GitHub PRs + issues
│   │   ├── linear.py            # Linear issues + comments
│   │   ├── slack.py             # Slack threads and mentions
│   │   ├── git.py               # Local git branches
│   │   └── todos.py             # Local markdown/text todo files
│   └── services/
│       ├── sync_service.py      # Orchestrates all sources, writes to DB
│       └── bucket_service.py    # Assigns items to buckets via keyword matching
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx             # React entrypoint
│       ├── App.tsx              # Root component with MantineProvider
│       ├── api/
│       │   └── client.ts        # Axios or fetch wrapper, base URL = localhost:8000
│       ├── hooks/
│       │   ├── useItems.ts      # TanStack Query: fetch items
│       │   ├── useBuckets.ts    # TanStack Query: fetch buckets
│       │   └── useSync.ts       # TanStack mutation: trigger sync
│       ├── components/
│       │   ├── BucketGrid.tsx   # Main layout: grid of BucketColumn
│       │   ├── BucketColumn.tsx # One topic bucket with its items
│       │   ├── ItemCard.tsx     # Single item card (title, source icon, link, date)
│       │   ├── SourceBadge.tsx  # Icon + label for GitHub / Linear / Slack / etc.
│       │   ├── SyncButton.tsx   # Triggers sync, shows loading state
│       │   └── FocusMode.tsx    # Clicking a bucket collapses all others
│       └── types/
│           └── index.ts         # Shared TypeScript types
├── buckets.json                 # Bucket → keyword mapping (user-editable)
├── .env                         # API tokens (never committed)
├── .env.example                 # Template for .env
├── requirements.txt
└── README.md
```

---

## Data Model

### SQLite Tables (via SQLAlchemy async)

#### `items`

| Column       | Type     | Description                                          |
|--------------|----------|------------------------------------------------------|
| `id`         | TEXT PK  | Composite: `{source}:{external_id}` e.g. `gh:pr:123`|
| `source`     | TEXT     | `github_pr`, `github_issue`, `linear`, `slack`, `git_branch`, `todo` |
| `title`      | TEXT     | Display title                                        |
| `url`        | TEXT     | Deep link to the item (null for local items)         |
| `bucket`     | TEXT     | Assigned bucket name (FK to buckets config)          |
| `status`     | TEXT     | Source-specific status: `open`, `in_progress`, `done`, `merged` |
| `updated_at` | DATETIME | Last updated timestamp from the source               |
| `synced_at`  | DATETIME | When we last fetched this item                       |
| `snoozed_until` | DATETIME | If set, hide from UI until this date              |
| `metadata`   | JSON     | Raw source data (author, labels, branch name, etc.)  |

#### `sync_log`

| Column       | Type     | Description              |
|--------------|----------|--------------------------|
| `id`         | INTEGER PK |                        |
| `started_at` | DATETIME |                          |
| `finished_at`| DATETIME |                          |
| `source`     | TEXT     | Which source was synced  |
| `items_added`| INTEGER  |                          |
| `items_updated`| INTEGER|                          |
| `error`      | TEXT     | Null if successful       |

---

## Backend API

Base URL: `http://localhost:8000`

### `GET /items`

Returns all non-snoozed items, optionally filtered.

**Query params:**
- `bucket` (str, optional): filter by bucket name
- `source` (str, optional): filter by source
- `status` (str, optional): filter by status
- `include_snoozed` (bool, default false)

**Response:**
```json
[
  {
    "id": "gh:pr:1234",
    "source": "github_pr",
    "title": "feat(payments): add Stripe webhook handler",
    "url": "https://github.com/alan-eu/alan-apps/pull/1234",
    "bucket": "Payments",
    "status": "open",
    "updated_at": "2026-07-15T14:30:00Z",
    "snoozed_until": null,
    "metadata": {
      "labels": ["payments", "backend"],
      "repo": "alan-eu/alan-apps"
    }
  }
]
```

### `PATCH /items/{item_id}`

Update mutable fields on an item (manual bucket override, snooze).

**Body:**
```json
{
  "bucket": "Payments",
  "snoozed_until": "2026-07-20T09:00:00Z"
}
```

### `GET /buckets`

Returns all bucket names with their item counts.

**Response:**
```json
[
  { "name": "Payments", "count": 12 },
  { "name": "Auth", "count": 4 },
  { "name": "Uncategorized", "count": 3 }
]
```

### `POST /sync`

Triggers a full sync across all sources (or a specific source).

**Body (optional):**
```json
{ "source": "github" }
```

**Response:** streams progress as newline-delimited JSON (NDJSON), or returns a summary on completion:
```json
{
  "sources_synced": ["github", "linear", "slack", "git", "todos"],
  "items_added": 5,
  "items_updated": 12,
  "duration_seconds": 4.2,
  "errors": []
}
```

### `GET /sync/status`

Returns the last sync log entry per source.

---

## Configuration

### `.env`

```env
GITHUB_TOKEN=ghp_...
GITHUB_USERNAME=joris-guerry
GITHUB_ORG=alan-eu

LINEAR_API_KEY=lin_api_...
LINEAR_USER_ID=...         # Your Linear user ID (UUID)

SLACK_USER_TOKEN=xoxp-...  # User token, not bot token
SLACK_USER_ID=U...

GIT_REPOS_PATHS=/Users/joris/code/alan-apps,/Users/joris/code/myproject
TODO_FILES_GLOB=/Users/joris/**/*.todo,/Users/joris/notes/**/*.md

BUCKETS_CONFIG_PATH=./buckets.json
SYNC_ON_STARTUP=true
```

### `buckets.json`

```json
{
  "buckets": {
    "Payments": ["payments", "billing", "stripe", "invoice"],
    "Auth": ["auth", "login", "sso", "oauth", "session"],
    "Infra": ["infra", "deploy", "k8s", "terraform", "ci"],
    "AI": ["ai", "llm", "ml", "dust", "claude"],
    "Onboarding": ["onboarding", "signup", "kyc"]
  },
  "default_bucket": "Uncategorized"
}
```

Bucket assignment: match keywords (case-insensitive) against item `title` + `metadata.labels`. First match wins.

---

## Source Implementations

### GitHub (`sources/github.py`)

Use the GitHub REST API (`https://api.github.com`).

Fetch:
1. **Pull Requests** where `author = GITHUB_USERNAME` and `state = open`, across all repos in `GITHUB_ORG`
   - Endpoint: `GET /search/issues?q=is:pr+author:{username}+org:{org}+is:open`
2. **Issues** assigned to `GITHUB_USERNAME` and `state = open`
   - Endpoint: `GET /search/issues?q=is:issue+assignee:{username}+org:{org}+is:open`

Map to item:
- `source`: `github_pr` or `github_issue`
- `id`: `gh:pr:{number}` or `gh:issue:{number}`
- `title`: PR/issue title
- `url`: `html_url`
- `status`: `open` / `merged` / `closed`
- `updated_at`: `updated_at`
- `metadata`: `{ labels, repo, draft, reviewers }`

Use `httpx` (async) with `Authorization: Bearer {GITHUB_TOKEN}` header.

### Linear (`sources/linear.py`)

Use Linear's GraphQL API (`https://api.linear.app/graphql`).

Fetch issues where `assignee.id = LINEAR_USER_ID` and `state.type` in `["started", "unstarted", "triage"]`.

GraphQL query:
```graphql
query MyIssues($userId: ID!) {
  issues(filter: {
    assignee: { id: { eq: $userId } }
    state: { type: { in: ["started", "unstarted", "triage"] } }
  }, first: 50) {
    nodes {
      id
      title
      url
      state { name type }
      labels { nodes { name } }
      updatedAt
      project { name }
      branchName
    }
  }
}
```

Map to item:
- `source`: `linear`
- `id`: `linear:{issue.id}`
- `title`: issue title
- `url`: issue URL
- `status`: map state type (`started` → `in_progress`, `unstarted` → `open`)
- `metadata`: `{ state_name, labels, project_name, branch_name }`

Use `httpx` with `Authorization: {LINEAR_API_KEY}` header.

### Slack (`sources/slack.py`)

Use Slack Web API. Requires a **user token** (`xoxp-`), not a bot token.

Fetch recent threads where the user is active:
1. `search.messages` with `query = "from:me"`, last 14 days
2. `conversations.history` on active DMs/channels (optional, can be added later)

Map to item:
- `source`: `slack`
- `id`: `slack:{channel}:{ts}`
- `title`: First 100 chars of message text
- `url`: Build permalink via `chat.getPermalink`
- `status`: `open` (always)
- `metadata`: `{ channel_name, thread_ts, reply_count }`

> Note: `search.messages` requires a user token scopes: `search:read`

### Git Branches (`sources/git.py`)

For each path in `GIT_REPOS_PATHS`, run shell commands via `asyncio.create_subprocess_exec`:

```bash
git -C {repo_path} branch --format='%(refname:short) %(committerdate:iso)' --sort=-committerdate
```

Filter branches that start with your username prefix (e.g. `joris/`) OR were committed in the last 30 days.

Map to item:
- `source`: `git_branch`
- `id`: `git:{repo_name}:{branch_name}`
- `title`: `[repo_name] branch_name`
- `url`: null (local)
- `status`: `open`
- `metadata`: `{ repo_path, repo_name, last_commit_date }`

### Todo Files (`sources/todos.py`)

Use `glob.glob` with patterns from `TODO_FILES_GLOB`.

For each file, extract todo lines matching:
- `- [ ] ...` (GFM task list)
- `TODO: ...`
- Lines starting with `☐` or `•`

Map each todo line to one item:
- `source`: `todo`
- `id`: `todo:{file_hash}:{line_number}`
- `title`: The todo text (stripped)
- `url`: null
- `status`: `open`
- `metadata`: `{ file_path, line_number }`

---

## Frontend

### Stack

```json
{
  "react": "^19.0.0",
  "typescript": "^5.0.0",
  "@mantine/core": "^8.3.2",
  "@mantine/hooks": "^8.3.2",
  "@mantine/notifications": "^8.3.2",
  "@tabler/icons-react": "^3.34.0",
  "@tanstack/react-query": "^5.0.0",
  "axios": "^1.7.0",
  "vite": "^6.0.0"
}
```

### Key Components

#### `App.tsx`
- Wraps everything in `MantineProvider` and `QueryClientProvider`
- Top bar with app title + `SyncButton`
- Renders `BucketGrid`

#### `BucketGrid.tsx`
- Fetches all items via `useItems()`
- Groups items client-side by `bucket`
- Renders one `BucketColumn` per bucket
- "Focus mode" state: when a bucket is clicked/focused, others are collapsed

#### `BucketColumn.tsx`
- Props: `{ name: string, items: Item[], isFocused: boolean, onFocus: () => void }`
- Header shows bucket name + item count badge
- Clicking the header toggles focus mode
- Scrollable list of `ItemCard` components

#### `ItemCard.tsx`
- Props: `{ item: Item }`
- Shows: `SourceBadge` | title (truncated, links to `item.url`) | relative date
- On hover: show "Snooze" button (opens a date picker popover → calls `PATCH /items/{id}`)
- Color-code left border by `status` (open = blue, in_progress = yellow, merged = green)

#### `SourceBadge.tsx`
- Maps `source` to a Tabler icon + label:
  - `github_pr` → `IconGitPullRequest` + "PR"
  - `github_issue` → `IconBug` + "Issue"
  - `linear` → `IconCircleDot` + "Linear"
  - `slack` → `IconBrandSlack` + "Slack"
  - `git_branch` → `IconGitBranch` + "Branch"
  - `todo` → `IconCheckbox` + "Todo"

#### `SyncButton.tsx`
- Button with `IconRefresh`
- On click: calls `POST /sync` via `useSync()` mutation
- Shows loading spinner during sync
- On success: invalidates `useItems` and `useBuckets` queries, shows Mantine notification

### TanStack Query Setup

```tsx
// hooks/useItems.ts
export const useItems = (filters?: ItemFilters) =>
  useQuery({
    queryKey: ['items', filters],
    queryFn: () => api.get('/items', { params: filters }).then(r => r.data),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

// hooks/useSync.ts
export const useSync = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/sync').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['items'] });
      qc.invalidateQueries({ queryKey: ['buckets'] });
    },
  });
};
```

---

## Sync Service (`services/sync_service.py`)

```python
async def sync_all(db: AsyncSession) -> SyncResult:
    sources = [GitHubSource(), LinearSource(), SlackSource(), GitSource(), TodoSource()]
    results = await asyncio.gather(*[sync_source(s, db) for s in sources], return_exceptions=True)
    return aggregate_results(results)

async def sync_source(source: BaseSource, db: AsyncSession) -> SourceResult:
    items = await source.fetch()
    for item in items:
        existing = await db.get(Item, item.id)
        if existing:
            # Update fields but preserve manual bucket overrides
            if not existing.bucket_override:
                existing.bucket = assign_bucket(item)
            existing.title = item.title
            existing.status = item.status
            existing.updated_at = item.updated_at
            existing.synced_at = datetime.utcnow()
        else:
            item.bucket = assign_bucket(item)
            db.add(item)
    await db.commit()
```

---

## Startup Behavior

In `main.py`, on app startup (`@asynccontextmanager lifespan`):
1. Run `alembic upgrade head` (or `Base.metadata.create_all`) to ensure DB schema exists
2. If `SYNC_ON_STARTUP=true`, trigger `sync_all` in the background

---

## CORS

Enable CORS in FastAPI for `http://localhost:5173` (Vite default):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Python Dependencies (`requirements.txt`)

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.20.0
httpx>=0.27.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
```

---

## Running Locally

```bash
# Backend
cd backend
python -m uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # starts on localhost:5173
```

---

## What is explicitly NOT in scope (v1)

- Authentication (it's local-only)
- Drag-and-drop between buckets (use snooze + manual bucket patch instead)
- Notifications / scheduled background sync (add later with APScheduler)
- Mobile layout
- Dark mode (Mantine default light theme is fine)
- Any write actions back to sources (no creating Linear issues, no posting Slack messages)
