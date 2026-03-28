"""Agregados sobre listado REPORT?sort (sin persistir fileUrl en derivados si no hace falta)."""

from __future__ import annotations

from collections import Counter

from app.schemas.nubceo_responses import ReportJobRecord


def report_list_derived(records: list[ReportJobRecord]) -> dict[str, int | dict[str, int]]:
    by_type = Counter((r.type or "unknown") for r in records)
    by_status = Counter((r.status or "unknown") for r in records)
    return {"count": len(records), "by_type": dict(by_type), "by_status": dict(by_status)}
