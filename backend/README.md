# Personal HQ — backend

FastAPI + SQLAlchemy (async, SQLite). Owns the database, talks to the sources, and serves
the API the frontend consumes.

See the root `README.md` for what to run and `CLAUDE.md` for conventions.

## Running

```bash
task back:setup    # install dependencies, create and migrate the database
task back:dev      # http://localhost:13000  — interactive API docs at /docs
task back:test
```

It binds to 127.0.0.1 by design: the API is unauthenticated and can reach keychain-backed
tokens, so it must not be exposed beyond the loopback interface.

The backend runs standalone — `/docs` is enough to drive every flow without the frontend.
The frontend, on the other hand, is useless without this.

## Layout

| Path | What lives there |
|---|---|
| `app/models.py` | `Task`, `Item`, `Link`, `Bucket`, `AppConfig`, `SyncLog` |
| `app/engine/` | proposes which task an incoming item attaches to |
| `app/sources/` | one adapter per source; each declares its own config fields |
| `app/services/sync.py` | fetch → route through the engine → persist |
| `app/services/catchup.py` | the untriaged inbox; writes confirm/reject decisions |
| `app/services/ai.py` | bucket suggestions via the Claude API |
| `app/security/secrets.py` | OS keychain, with an encrypted-file fallback |
| `app/routers/` | `tasks`, `buckets`, `catchup`, `sync`, `admin` |

## Configuration

There is no `.env` to fill in. Non-secret settings live in the `app_config` table and
secrets in the OS keychain; both are written through `/admin/sources/{id}/config`.
`GET /admin/sources` reports what is configured and reachable.

## Database

SQLite, at `backend/hq.db`. Schema changes go through Alembic:

```bash
task back:db-migrate -- "add a column"   # autogenerate, then review the file
task back:db-check                       # fail if models drifted from migrations
task back:db-reset                       # delete and rebuild
```
