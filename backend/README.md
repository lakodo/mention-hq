# Personal HQ — backend

FastAPI + SQLAlchemy (async, SQLite) service that aggregates your activity across GitHub,
Linear, Slack, local git branches, todo files and markdown docs, and groups it into tasks.

See the repository root `README.md` for the whole picture, and `CLAUDE.md` for the
architecture and conventions.

```bash
task back:setup    # install + migrate
task back:dev      # serve on :8000  (docs at /docs)
task back:test
```

## Layout

| Path | What lives there |
|---|---|
| `app/models.py` | `Task`, `Mention`, `TaskMention`, `LinkOverride`, `Bucket`, `AppConfig`, `SyncLog` |
| `app/sources/` | One adapter per source. Each declares its own config fields. |
| `app/services/grouping.py` | Union-find that merges mentions into tasks |
| `app/services/sync.py` | Fetch → group → persist, preserving user overrides |
| `app/services/ai.py` | Bucket suggestions via the Claude API |
| `app/security/secrets.py` | OS keychain, with an encrypted-file fallback |
| `app/routers/` | `tasks`, `buckets`, `catchup`, `sync`, `admin` |

## Credentials

Nothing goes in `.env`. Tokens are entered in the Admin panel and stored in the OS keychain
(`app/security/secrets.py`); non-secret config goes in the `app_config` table. `GET /admin/sources`
reports which sources are configured and reachable.
