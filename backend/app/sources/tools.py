"""Reading configuration out of CLIs the user has already logged into."""

from __future__ import annotations

import asyncio
import shutil

import structlog

log = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 10


async def run_tool(command: str, *args: str) -> str:
    """Run a local CLI and return its stdout, or "" if it isn't there or fails.

    Never raises and never logs the output: these commands hand back credentials, and a
    log line is the easiest way to leak one.
    """
    if shutil.which(command) is None:
        return ""

    try:
        proc = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
    except (TimeoutError, OSError):
        log.warning("tool_failed", command=command)
        return ""

    if proc.returncode != 0:
        return ""
    return stdout.decode().strip()
