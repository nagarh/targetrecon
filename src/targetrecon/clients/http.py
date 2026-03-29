"""Shared async HTTP client utilities."""
from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0
USER_AGENT = "TargetRecon/0.1.2 (drug target intelligence; github.com/nagarh/targetrecon)"


def build_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
) -> Any:
    """GET JSON, returning None on any error."""
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def safe_post(
    client: httpx.AsyncClient,
    url: str,
    json_body: dict | None = None,
) -> Any:
    """POST JSON, returning None on any error."""
    try:
        resp = await client.post(url, json=json_body)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def safe_get_text(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
) -> str | None:
    """GET text, returning None on any error."""
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None
