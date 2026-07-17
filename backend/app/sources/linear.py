"""Linear issues, via the GraphQL API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source
from app.sources.keys import all_reference_keys

API_URL = "https://api.linear.app/graphql"

MY_ISSUES_QUERY = """
query MyIssues($userId: ID!) {
  issues(
    filter: {
      assignee: { id: { eq: $userId } }
      state: { type: { in: ["started", "unstarted", "triage", "backlog"] } }
    }
    first: 50
    orderBy: updatedAt
  ) {
    nodes {
      id
      identifier
      title
      description
      url
      updatedAt
      branchName
      state { name type }
      labels { nodes { name } }
      project { name }
    }
  }
}
"""

VIEWER_QUERY = "query { viewer { id } }"

STATE_TO_STATUS = {
    "started": "in_progress",
    "unstarted": "open",
    "triage": "open",
    "backlog": "open",
    "completed": "done",
}


class LinearSource(Source):
    id = "linear"
    name = "Linear"
    description = "Issues assigned to you that are in backlog, triage, unstarted or started"
    setup = (
        "Linear → Settings → Security & access → Personal API keys → New key. "
        "A read-only key is enough; HQ never writes to Linear."
    )
    setup_url = "https://linear.app/settings/account/security"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="api_key",
            label="API key",
            kind="secret",
            placeholder="lin_api_…",
            help="Settings → Security & access → Personal API keys → New key.",
            help_url="https://linear.app/settings/account/security",
        ),
        ConfigField(
            key="user_id",
            label="Your Linear user ID",
            placeholder="UUID",
            help="Leave blank and use Test connection to look it up automatically",
            required=False,
        ),
    ]

    def detail(self) -> str:
        return (
            "Assigned issues · backlog, triage, unstarted, started"
            if self.is_configured()
            else "Not configured"
        )

    def is_configured(self) -> bool:
        return bool(self.get("api_key"))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.get("api_key"), "Content-Type": "application/json"}

    async def _post(self, client: httpx.AsyncClient, query: str, variables: dict | None = None) -> dict:
        response = await client.post(
            API_URL, headers=self._headers(), json={"query": query, "variables": variables or {}}
        )
        response.raise_for_status()
        payload = response.json()
        # GraphQL reports failures in a 200 body, so raise_for_status alone isn't enough.
        if payload.get("errors"):
            raise RuntimeError(payload["errors"][0].get("message", "Linear GraphQL error"))
        return payload["data"]

    async def check(self) -> None:
        await super().check()
        async with httpx.AsyncClient(timeout=10) as client:
            await self._post(client, VIEWER_QUERY)

    async def _user_id(self, client: httpx.AsyncClient) -> str:
        configured = self.get("user_id")
        if configured:
            return configured
        # The token already identifies the user, so asking them to paste a UUID they'd have
        # to dig out of the API is needless friction.
        data = await self._post(client, VIEWER_QUERY)
        return data["viewer"]["id"]

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            user_id = await self._user_id(client)
            data = await self._post(client, MY_ISSUES_QUERY, {"userId": user_id})
        return [_to_item(node) for node in data["issues"]["nodes"]]


def _to_item(node: dict) -> RawItem:
    identifier = node["identifier"]
    labels = [label["name"] for label in node.get("labels", {}).get("nodes", [])]
    state = node.get("state") or {}
    project = (node.get("project") or {}).get("name")

    identity = {identifier}
    if node.get("branchName"):
        identity.add(node["branchName"].upper())

    return RawItem(
        source="linear",
        external_id=node["id"],
        label=node["title"],
        occurred_at=datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00")),
        url=node.get("url"),
        context=identifier,
        title=node["title"],
        status=STATE_TO_STATUS.get(state.get("type", ""), "open"),
        tags=labels,
        identity_keys=identity,
        reference_keys=all_reference_keys(node.get("description")) - identity,
        extra={
            "state_name": state.get("name"),
            "labels": labels,
            "project_name": project,
            "branch_name": node.get("branchName"),
        },
    )
