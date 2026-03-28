"""
Traducción SAP B1 (OData Invoice) → payload Nubceo (posSale).

Ajustá según: numeración real de IDs, sucursales (customerBranchReference),
CUIT (taxCode), líneas de pago (relatedPayments) y tipos (invoice / creditNote).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo


def iso_date_from_sap(value: str | None, tz_name: str = "America/Argentina/Buenos_Aires") -> str:
    """Convierte fecha SAP 'YYYY-MM-DD' a ISO 8601 con zona (ajustá tz_name según tenant)."""
    tz = ZoneInfo(tz_name)
    if not value:
        return datetime.now(tz).isoformat(timespec="milliseconds")
    if "T" in value:
        return value
    d = date.fromisoformat(value[:10])
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=tz).isoformat(timespec="milliseconds")


def _num(inv: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in inv and inv[k] is not None:
            try:
                return float(inv[k])
            except (TypeError, ValueError):
                continue
    return default


def sap_invoice_to_nubceo_sale(
    inv: dict[str, Any],
    *,
    sale_index: int = 0,
    customer_branch_reference: str,
    tax_code: str | None = None,
    payment_id_suffix: str = "pay01",
    platform_external_code: str | None = None,
    document_type: str = "invoice",
) -> dict[str, Any]:
    """
    Mapeo ejemplo desde una fila de /Invoices.

    Campos típicos Service Layer: DocEntry, DocNum, DocDate, DocCurrency,
    DocTotal, VatSum, CardCode, NumAtCard, ...
    """
    doc_entry = inv.get("DocEntry")
    doc_num = inv.get("DocNum")
    ext_id = f"{doc_num}-{doc_entry}" if doc_num is not None and doc_entry is not None else str(doc_entry)

    gross = _num(inv, "DocTotal")
    tax = _num(inv, "VatSum", "TotalTax")
    net = gross - tax

    doc_date = inv.get("DocDate")
    date_iso = iso_date_from_sap(doc_date) if isinstance(doc_date, str) else iso_date_from_sap(None)

    currency = (inv.get("DocCurrency") or "ARS")[:3]

    pay: dict[str, Any] = {
        "presentedDate": date_iso,
        "grossAmount": gross,
        "id": f"{ext_id}-{payment_id_suffix}",
    }
    if platform_external_code:
        pay["platformExternalCode"] = platform_external_code

    sale: dict[str, Any] = {
        "saleIndexNumber": sale_index,
        "customerBranchReference": customer_branch_reference,
        "date": date_iso,
        "currencyCode": currency,
        "type": document_type,
        "id": ext_id,
        "taxAmount": tax,
        "netAmount": net,
        "grossAmount": gross,
        "relatedPayments": [pay],
    }
    if tax_code:
        sale["taxCode"] = tax_code

    return sale
