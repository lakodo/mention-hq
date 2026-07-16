"""Dust conversations.

Stub. The design shows Dust mentions ("Conversation: latency root-cause exploration"),
but we have no API spec for it yet, so this reports itself unconfigured and returns
nothing rather than guessing at an endpoint shape. Fill in `fetch`/`check` once the
Dust API is pinned down; the rest of the pipeline already handles the "dust" source.
"""

from __future__ import annotations

from typing import ClassVar

from app.sources.base import ConfigField, RawMention, Source, SourceNotConfigured


class DustSource(Source):
    id = "dust"
    name = "Dust"
    description = "Conversations in Dust (not implemented yet)"
    # No fields until the API is known — an empty form is more honest than one asking
    # for credentials nothing will use.
    fields: ClassVar[list[ConfigField]] = []

    def is_configured(self) -> bool:
        return False

    def detail(self) -> str:
        return "Not implemented — awaiting Dust API details"

    async def check(self) -> None:
        raise SourceNotConfigured("Dust integration is not implemented yet")

    async def fetch(self) -> list[RawMention]:
        return []
