"""Índices sobre branch?filter (customerBranchReference / externalCode)."""

from __future__ import annotations

from typing import Any

from app.schemas.nubceo_responses import BranchRecord


def branch_list_derived(records: list[BranchRecord]) -> dict[str, Any]:
    by_name: dict[str, dict[str, Any]] = {}
    for r in records:
        key = str(r.name) if r.name is not None else str(r.id)
        by_name[key] = {
            "branchId": r.id,
            "companyId": r.companyId,
            "taxCode": r.Company.taxCode if r.Company else None,
            "platformCodes": [p.platformExternalCode for p in r.PlatformExternals],
            "externalCodesByPlatform": {
                p.platformExternalCode: p.externalCode for p in r.PlatformExternals
            },
        }
    return {"by_branch_name": by_name, "count": len(records)}
