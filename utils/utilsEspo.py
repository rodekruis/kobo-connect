from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException
from utils.logger import logger


def espo_request(
    espo_client: Any,
    method: str,
    entity: str,
    params: dict[str, Any] | None = None,
    logs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Make a request to EspoCRM. Returns the response dict on success, or None on failure."""
    try:
        response = espo_client.request(method, entity, params)
        return response
    except HTTPException as e:
        detail = e.detail if "Unknown Error" not in e.detail else ""
        logger.error(f"Failed: EspoCRM returned {e.status_code} {detail}", extra=logs)
        return None


def required_headers_espocrm(
    targeturl: str = Header(), targetkey: str = Header()
) -> tuple[str, str]:
    return targeturl, targetkey
