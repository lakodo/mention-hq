"""Populate a throwaway demo database with realistic data across every source.

This is what lets HQ be developed, tried and screenshotted without ever touching your real
`hq.db`: `task back:seed` builds `hq-demo.db` from scratch, and you run the app against that.
It never imports the app's global engine — it makes its own at the target path — so there is
no way for a stray run to write to your live database.

Content is generated from curated, domain-flavoured templates plus Faker for volume and names,
seeded deterministically so a rebuild is reproducible.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import BACKEND_DIR
from app.database import enable_sqlite_foreign_keys
from app.models import (
    CONFIRMED,
    PROPOSED,
    AppConfig,
    Base,
    Bucket,
    Item,
    Link,
    Person,
    PersonIdentity,
    SourceInstance,
    SyncLog,
    Task,
    TriageRule,
)

DEMO_DB = BACKEND_DIR / "hq-demo.db"

fake = Faker()

# One connected instance per kind, so the Admin screen has something to show.
INSTANCES = [
    ("github", "GitHub"),
    ("linear", "Linear"),
    ("slack", "Slack"),
    ("notion", "Notion"),
    ("notion_mcp", "Notion MCP"),
    ("dust", "Dust"),
    ("git", "Local Git"),
    ("todos", "Todo files"),
    ("markdown", "Markdown docs"),
]

PEOPLE = [
    ("Ada Lovelace", "ada", "U01ADA"),
    ("Grace Hopper", "ghopper", "U02GRC"),
    ("Linus Rivera", "linusr", "U03LIN"),
    ("Mona Okoye", "mokoye", "U04MON"),
    ("Bruno Vega", "bvega", "U05BRU"),
    ("Priya Nair", "pnair", "U06PRI"),
    ("Tom Fischer", "tfischer", "U07TOM"),
    ("Sofia Marino", "smarino", "U08SOF"),
]

BUCKETS = [
    ("Platform", ["api", "sync", "engine"]),
    ("Payments", ["stripe", "invoice", "refund", "billing"]),
    ("Data pipeline", ["dataset", "etl", "pipeline", "ingest"]),
    ("Auth", ["oauth", "token", "session", "sso"]),
    ("Developer experience", ["ci", "tooling", "docs", "lint"]),
]

REPO = "acme/platform"


def _avatar(login: str) -> str:
    """A stable, real-looking face per person — pravatar keys off the seed, so it never changes."""
    return f"https://i.pravatar.cc/200?u={login}@acme.dev"


class Builder:
    """Accumulates rows and wires their relationships, then hands them to a session."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)
        self.rows: list[object] = []
        self.people_by_login: dict[str, tuple[str, str]] = {}  # login -> (name, slack)
        self._n = 0

    def add(self, row: object) -> object:
        self.rows.append(row)
        return row

    def uid(self) -> int:
        self._n += 1
        return self._n

    def ago(self, hours: float) -> datetime:
        return self.now - timedelta(hours=hours)

    # --- people -----------------------------------------------------------------------
    def people(self) -> None:
        for name, login, slack in PEOPLE:
            self.people_by_login[login] = (name, slack)
            person = self.add(Person(id=f"person:{login}", display_name=name, email=f"{login}@acme.dev"))
            for kind, value in (("github", login), ("slack", slack), ("email", f"{login}@acme.dev")):
                self.add(
                    PersonIdentity(
                        id=f"pid:{login}:{kind}",
                        person_id=person.id,
                        kind=kind,
                        value=value,
                        label=name,
                        avatar_url=_avatar(login) if kind == "github" else None,
                    )
                )

    def refs(self, *logins: str, role: str = "author") -> list[dict]:
        out = []
        for login in logins:
            name, slack = self.people_by_login[login]
            kind, value = ("slack", slack) if role == "mentioned" else ("github", login)
            out.append({"kind": kind, "value": value, "name": name, "role": role, "avatar": _avatar(login)})
        return out

    # --- buckets ----------------------------------------------------------------------
    def buckets(self) -> None:
        for i, (name, keywords) in enumerate(BUCKETS):
            self.add(Bucket(name=name, keywords=keywords, position=i, created_at=self.ago(24 * 40)))

    # --- items & tasks ----------------------------------------------------------------
    def item(
        self,
        source: str,
        external_id: str,
        label: str,
        *,
        context: str | None = None,
        url: str | None = None,
        hours: float = 12.0,
        extra: dict | None = None,
        triaged: bool = True,
        triage_reason: str | None = None,
    ) -> Item:
        occurred = self.ago(hours)
        return self.add(
            Item(
                id=f"{source}:{external_id}",
                source=source,
                instance_id=None,
                label=label,
                url=url,
                context=context,
                occurred_at=occurred,
                triaged=triaged,
                triage_reason=triage_reason,
                triaged_at=occurred if triaged else None,
                first_seen_at=occurred,
                extra=extra or {},
            )
        )

    def task(
        self,
        title: str,
        bucket: str,
        *,
        tags: list[str],
        priority: int,
        status: str = "open",
        description: str | None = None,
        next_action: str | None = None,
        hours: float = 8.0,
    ) -> Task:
        return self.add(
            Task(
                id=f"task:{self.uid():04d}",
                title=title,
                description=description,
                bucket=bucket,
                bucket_override=True,
                status=status,
                priority=priority,
                tags=tags,
                unread=random.random() < 0.4,
                origin="manual",
                title_override=True,
                next_action=next_action,
                updated_at=self.ago(hours),
            )
        )

    def link(self, task: Task, item: Item, *, state: str = CONFIRMED, **kw) -> None:
        self.add(
            Link(
                task_id=task.id,
                item_id=item.id,
                state=state,
                decided_at=self.ago(6) if state == CONFIRMED else None,
                **kw,
            )
        )

    # --- source instances, rules, log -------------------------------------------------
    def instances(self) -> None:
        for i, (kind, name) in enumerate(INSTANCES):
            self.add(SourceInstance(id=f"{kind}-demo", kind=kind, name=name, position=i))

    def rules(self) -> None:
        self.add(
            TriageRule(
                id="rule:1",
                name="Dependabot noise",
                sources=["pr"],
                condition="starts_with",
                value="chore(deps):",
            )
        )
        self.add(
            TriageRule(
                id="rule:2",
                name="Deploy notifications",
                sources=["slack"],
                condition="contains",
                value="deployed to production",
            )
        )

    def sync_log(self) -> None:
        # Newest sync is seconds old, so the app opens on a freshly-synced state — and catch-up's
        # open-refresh throttle skips a re-sync, which would otherwise rebuild proposals the demo
        # data can't reproduce.
        for hours in (0.005, 24, 48):
            started = self.ago(hours)
            self.add(
                SyncLog(
                    started_at=started,
                    finished_at=started + timedelta(seconds=8),
                    sources=[
                        {"source": k, "items_fetched": random.randint(0, 12), "error": None}
                        for k, _ in INSTANCES
                    ],
                    items_fetched=random.randint(20, 60),
                    items_added=random.randint(2, 15),
                    items_updated=random.randint(0, 8),
                    proposals=random.randint(1, 10),
                    tasks_updated=random.randint(0, 6),
                    duration_seconds=round(random.uniform(3, 12), 1),
                )
            )

    def config(self) -> None:
        self.add(AppConfig(namespace="app", key="auto_sync", value="true"))


def _stack_task(b: Builder) -> None:
    """A git-spice stack: three stacked branches, each with its PR, on one task — the case the
    Code lane is built to show."""
    task = b.task(
        "Datasets screen: filtering, quick add/remove",
        "Data pipeline",
        tags=["frontend", "datasets"],
        priority=78,
        status="in_progress",
        description="The stacked work behind the new datasets screen, from the API up to the UI.",
        next_action="Land #201 (the API) first — the two PRs on top of it are blocked on its review.",
    )
    chain = ["dev/datasets-api", "dev/datasets-list", "dev/datasets-screen"]
    prs = [
        ("201", "feat(api): datasets list, filtering and remove endpoint", "approved"),
        ("204", "feat(web): datasets list with filtering", "changes_requested"),
        ("206", "feat(web): datasets screen and quick add/remove", "review_required"),
    ]
    for depth, (branch, (num, title, status)) in enumerate(zip(chain, prs, strict=True)):
        pr = b.item(
            "pr",
            f"{REPO.replace('/', '~')}~{num}",
            title,
            context=f"#{num}",
            url=f"https://github.com/{REPO}/pull/{num}",
            hours=3 + depth,
            extra={
                "repo": REPO,
                "pr_status": status,
                "pr_review_requested": status != "approved",
                "head_branch": branch,
                "people": b.refs("bvega", "ada"),
            },
        )
        b.link(task, pr)
        bitem = b.item(
            "branch",
            f"platform~{branch.replace('/', '~')}",
            f"[platform] {branch}",
            context="platform",
            hours=2 + depth,
            extra={"repo_name": "platform", "branch": branch, "stack": chain[: depth + 1]},
        )
        b.link(task, bitem)


def _curated_tasks(b: Builder) -> None:
    t = b.task(
        "Refunds throw on partial captures",
        "Payments",
        tags=["bug", "stripe"],
        priority=90,
        status="in_progress",
        description="A partial capture followed by a refund double-counts the fee. Customer-facing.",
        next_action="Reproduce with the failing invoice in #payments-eng, then patch the fee math.",
    )
    b.link(
        t,
        b.item(
            "linear",
            "PAY-412",
            "Refund flow throws on partial captures",
            context="PAY-412",
            url="https://linear.app/acme/issue/PAY-412",
            hours=20,
            extra={
                "people": b.refs("mokoye", role="assignee"),
                **_linear_state("In Progress", "in_progress"),
            },
        ),
    )
    b.link(
        t,
        b.item(
            "slack",
            "C01~p17",
            "thread: refund fee looks doubled on partial captures :eyes:",
            context="#payments-eng, 9 replies",
            url="https://acme.slack.com/archives/C01/p17",
            hours=6,
            extra={"people": b.refs("mokoye", "bvega", role="mentioned"), "emoji": {}},
        ),
    )
    b.link(
        t,
        b.item(
            "pr",
            f"{REPO.replace('/', '~')}~198",
            "fix(payments): stop double-counting the fee on partial refunds",
            context="#198",
            url=f"https://github.com/{REPO}/pull/198",
            hours=4,
            extra={
                "repo": REPO,
                "pr_status": "review_required",
                "pr_review_requested": True,
                "head_branch": "dev/refund-fee",
                "people": b.refs("bvega"),
            },
        ),
    )
    b.link(
        t,
        b.item(
            "note",
            f"n{b.uid()}",
            "The bug only shows when capture < authorized. Ping finance before changing the rounding.",
            hours=5,
        ),
    )

    t = b.task(
        "Rotate refresh tokens on scope change",
        "Auth",
        tags=["security"],
        priority=72,
        description="When a user's scopes change, the old refresh token should be invalidated.",
        next_action="Confirm the migration backfills existing sessions before enabling the rotation.",
    )
    b.link(
        t,
        b.item(
            "pr",
            f"{REPO.replace('/', '~')}~188",
            "fix(auth): rotate refresh tokens on scope change",
            context="#188",
            url=f"https://github.com/{REPO}/pull/188",
            hours=30,
            extra={
                "repo": REPO,
                "pr_status": "approved",
                "head_branch": "dev/token-rotation",
                "people": b.refs("linusr"),
            },
        ),
    )
    b.link(
        t,
        b.item(
            "branch",
            "platform~dev~token-rotation",
            "[platform] dev/token-rotation",
            context="platform",
            hours=30,
            extra={"repo_name": "platform", "branch": "dev/token-rotation"},
        ),
    )
    b.link(
        t,
        b.item(
            "notion",
            "3491426e-8be7-80f1",
            "Auth hardening — Q3 plan",
            context="Engineering / Security",
            url="https://notion.so/3491426e",
            hours=48,
        ),
    )

    t = b.task(
        "Sync engine drops items on a partial failure",
        "Platform",
        tags=["bug", "sync"],
        priority=84,
        status="in_progress",
        description="When one source errors mid-sync, items from the healthy sources are cleared.",
        next_action="Add a test that fails one source and asserts the others survive, then guard the delete.",
    )
    b.link(
        t,
        b.item(
            "slack",
            "C02~p31",
            "thread: lost half my catch-up after a sync — Linear was down",
            context="#hq-dogfood, 5 replies",
            url="https://acme.slack.com/archives/C02/p31",
            hours=10,
            extra={"people": b.refs("ghopper", "tfischer", role="mentioned")},
        ),
    )
    b.link(
        t,
        b.item(
            "todo",
            "todos.md~14",
            "Guard _upsert_items against a source that returned nothing",
            context="todos.md",
            hours=14,
        ),
    )
    b.link(
        t,
        b.item(
            "markdown", "docs~sync.md", "Sync engine design notes", context="docs/sync.md", url=None, hours=60
        ),
    )
    b.link(
        t,
        b.item(
            "dust",
            "conv~7781",
            "Dust: why did my attached PR come back to catch-up?",
            context="Dust conversation",
            url="https://dust.tt/w/acme/conv/7781",
            hours=9,
        ),
    )

    t = b.task(
        "Ship the docs site to GitHub Pages",
        "Developer experience",
        tags=["docs", "ci"],
        priority=60,
        description="A modern docs site built from the seeded demo, published on every push to main.",
        next_action="Pick the generator (Material for MkDocs vs Zensical) and wire the Pages workflow.",
    )
    b.link(
        t,
        b.item(
            "notion_mcp",
            "27a1426e-8be7-8101",
            "Docs — outline and screenshots to capture",
            context="Vera - docs",
            url="https://notion.so/27a1426e",
            hours=7,
        ),
    )
    b.link(t, b.item("markdown", "readme", "README", context="README.md", hours=72))
    b.link(
        t,
        b.item(
            "todo", "todos.md~3", "Add a task:back:seed command and a demo DB", context="todos.md", hours=2
        ),
    )


TITLE_POOL = [
    "Add rate limiting to the public API",
    "Investigate flaky auth integration tests",
    "Cache the people directory lookups",
    "Backfill next-action for old tasks",
    "Tidy the Admin source-config forms",
    "Speed up the timeline query",
    "Handle emoji shortcodes in item labels",
    "Warn when the frontend build is stale",
    "Support two GitHub accounts at once",
    "Reduce sync log noise for empty sources",
]


def _filler_tasks(b: Builder) -> None:
    for i, title in enumerate(TITLE_POOL):
        bucket = BUCKETS[i % len(BUCKETS)][0] if i % 4 else "Uncategorized"
        t = b.task(
            title,
            bucket,
            tags=random.sample(["backend", "frontend", "chore", "perf", "ux"], k=random.randint(1, 2)),
            priority=random.randint(20, 75),
            status=random.choice(["open", "open", "in_progress"]),
            description=fake.sentence(nb_words=12),
            hours=random.uniform(4, 120),
        )
        for _ in range(random.randint(1, 3)):
            source = random.choice(["pr", "issue", "linear", "slack", "todo"])
            n = b.uid()
            people = b.refs(random.choice(list(b.people_by_login)))
            b.link(
                t,
                b.item(
                    source,
                    f"{source}~{n}",
                    _label_for(source, n),
                    context=_context_for(source, n),
                    url=_url_for(source, n),
                    hours=random.uniform(2, 200),
                    extra={
                        "people": people,
                        **(
                            {"pr_status": random.choice(["approved", "review_required"])}
                            if source == "pr"
                            else {}
                        ),
                        **(_linear_state(*random.choice(LINEAR_STATES)) if source == "linear" else {}),
                    },
                ),
            )


def _catchup(b: Builder) -> None:
    """Untriaged items waiting in the inbox — some with a proposed match to a task."""
    tasks = [r for r in b.rows if isinstance(r, Task)]
    samples = [
        ("slack", "thread: can someone review the deploy checklist?", "#platform, 3 replies"),
        ("pr", "chore(deps): bump pydantic to 2.9", "#221"),
        ("linear", "Add a health endpoint to the API", "OPS-88"),
        ("notion_mcp", "[VERA 2.0] Dataset annotation", "Vera 2.0"),
        ("dust", "Draft: onboarding checklist for new engineers", "Dust conversation"),
        ("issue", "Timeline is slow with 5k items", "#233"),
    ]
    for i, (source, label, context) in enumerate(samples):
        n = b.uid()
        item = b.item(
            source,
            f"{source}~inbox~{n}",
            label,
            context=context,
            url=_url_for(source, n),
            hours=random.uniform(0.5, 30),
            triaged=False,
            extra={
                "people": b.refs(random.choice(list(b.people_by_login))),
                **(_linear_state("In Progress", "in_progress") if source == "linear" else {}),
            },
        )
        if i < 2:
            b.link(
                tasks[i],
                item,
                state=PROPOSED,
                engine="keyword",
                confidence=round(random.uniform(0.55, 0.9), 2),
                reason="Shares keywords with the task title",
            )

    # A couple already skipped, for the Skipped tab.
    b.item(
        "slack",
        "skip~1",
        "thread: lunch order for friday :taco:",
        context="#random",
        hours=40,
        triaged=True,
        triage_reason="Skipped",
    )
    b.item(
        "pr",
        "skip~2",
        "chore(deps): bump ruff to 0.7",
        context="#219",
        hours=50,
        triaged=True,
        triage_reason="Rule: Dependabot noise",
    )


LINEAR_STATES = [
    ("Todo", "open"),
    ("In Progress", "in_progress"),
    ("In Review", "in_progress"),
    ("Backlog", "open"),
    ("Done", "done"),
]


def _linear_state(name: str, kind: str) -> dict[str, str]:
    """A Linear issue's own workflow state — the label the catch-up card shows, and the
    normalised kind (open/in_progress/done) it colours by."""
    return {"state_name": name, "state_kind": kind}


def _label_for(source: str, n: int) -> str:
    return {
        "pr": f"feat(api): {fake.bs()}",
        "issue": fake.sentence(nb_words=6).rstrip("."),
        "linear": fake.sentence(nb_words=5).rstrip("."),
        "slack": f"thread: {fake.sentence(nb_words=7).rstrip('.')}?",
        "todo": fake.sentence(nb_words=6).rstrip("."),
    }[source]


def _context_for(source: str, n: int) -> str:
    return {
        "pr": f"#{200 + n}",
        "issue": f"#{200 + n}",
        "linear": f"ENG-{100 + n}",
        "slack": f"#{fake.word()}, {random.randint(1, 12)} replies",
        "todo": "todos.md",
    }[source]


def _url_for(source: str, n: int) -> str | None:
    return {
        "pr": f"https://github.com/{REPO}/pull/{200 + n}",
        "issue": f"https://github.com/{REPO}/issues/{200 + n}",
        "linear": f"https://linear.app/acme/issue/ENG-{100 + n}",
        "slack": f"https://acme.slack.com/archives/C0/p{n}",
        "todo": None,
        "notion_mcp": f"https://notion.so/{n:012x}",
        "dust": f"https://dust.tt/w/acme/conv/{n}",
    }.get(source)


def build_rows() -> list[object]:
    Faker.seed(7)
    random.seed(7)
    b = Builder()
    b.people()
    b.buckets()
    b.instances()
    b.rules()
    b.sync_log()
    b.config()
    _stack_task(b)
    _curated_tasks(b)
    _filler_tasks(b)
    _catchup(b)
    return b.rows


async def seed(db: AsyncSession) -> dict[str, int]:
    """Insert the demo rows into an already-migrated session. Returns a per-table count."""
    rows = build_rows()
    # Items and tasks before the links that reference them.
    order = (Person, PersonIdentity, Bucket, SourceInstance, TriageRule, SyncLog, AppConfig, Task, Item, Link)
    for cls in order:
        db.add_all([r for r in rows if type(r) is cls])
        await db.flush()
    counts = {cls.__name__: sum(1 for r in rows if type(r) is cls) for cls in order}
    return counts


async def build_demo_db(path: Path) -> dict[str, int]:
    """Create a fresh SQLite file at `path` and fill it. Uses its own engine — never the app's."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        counts = await seed(db)
        await db.commit()
    await engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a seeded demo database.")
    parser.add_argument("--path", type=Path, default=DEMO_DB, help=f"Where to write it (default: {DEMO_DB})")
    args = parser.parse_args()
    counts = asyncio.run(build_demo_db(args.path))
    total = sum(counts.values())
    print(f"Seeded {args.path} — {total} rows:")
    for name, n in counts.items():
        if n:
            print(f"  {n:>4}  {name}")
    print(f"\nRun it:  DB_PATH={args.path} uv run uvicorn app.main:app --port 13010")


if __name__ == "__main__":
    main()
