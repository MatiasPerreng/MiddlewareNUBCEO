"""Índices útiles sobre listado de compañías Nubceo (para mapear a SAP / companyId)."""

from __future__ import annotations

from app.schemas.nubceo_responses import CompanyRecord


def company_list_index(records: list[CompanyRecord]) -> dict[str, dict[str, str | int | None]]:
    """
    taxCode -> company id y nombre (si hay taxCode duplicado, gana el último).
    """
    by_tax: dict[str, dict[str, str | int | None]] = {}
    for r in records:
        if r.taxCode:
            by_tax[str(r.taxCode)] = {"companyId": r.id, "name": r.name}
    return {"by_tax_code": by_tax, "count": len(records)}
