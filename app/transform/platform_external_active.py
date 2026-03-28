"""Índices sobre plataformas externas activas (alinear con platformExternalCode en ventas POS)."""

from __future__ import annotations

from typing import Any

from app.schemas.nubceo_responses import PlatformExternalActiveRecord


def platform_external_active_index(records: list[PlatformExternalActiveRecord]) -> dict[str, Any]:
    by_code: dict[str, dict[str, Any]] = {}
    for r in records:
        code = r.platformExternalCode
        info = r.PlatformExternal
        by_code[code] = {
            "id": r.id,
            "companyId": r.companyId,
            "platformName": info.name,
            "platformType": info.type,
            "setupCompleted": r.setupCompleted,
        }
    setup_ok = sum(1 for r in records if r.setupCompleted is True)
    return {
        "by_platform_code": by_code,
        "count": len(records),
        "setup_completed_count": setup_ok,
    }
