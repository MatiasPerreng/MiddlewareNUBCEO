"""Hooks httpx para loguear llamadas salientes cuando DEBUG=true (no loguea contraseñas de Login)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("middleware.outgoing")


def _request_hook_factory(label: str):
    def request_hook(request: httpx.Request) -> None:
        if not settings.debug:
            return
        url = str(request.url)
        if "/Login" in url or "/authenticate" in url.lower():
            log.info("%s → %s %s [credenciales omitidas en log]", label, request.method, url)
        else:
            log.info("%s → %s %s", label, request.method, url)

    return request_hook


def _response_hook_factory(label: str):
    def response_hook(response: httpx.Response) -> None:
        if not settings.debug:
            return
        log.info("%s ← %s %s", label, response.status_code, response.request.url)

    return response_hook


def httpx_event_hooks(label: str) -> dict[str, list[Any]]:
    if not settings.debug:
        return {}
    return {
        "request": [_request_hook_factory(label)],
        "response": [_response_hook_factory(label)],
    }
