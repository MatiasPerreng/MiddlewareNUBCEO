"""
API intermedia: orquesta SAP Service Layer y Nubceo Connect.
Las rutas son ejemplos; adaptá paths y mapeos al contrato de tu WEB.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.clients.nubceo import NubceoClient
from app.clients.sap import SapClient
from app.config import settings
from app.mappers.sales import sap_invoice_to_nubceo_sale
from app.schemas.nubceo_responses import (
    parse_cash_flow_adjacent_month_summary_envelope,
    parse_company_list_envelope,
    parse_expenses_detail_envelope,
    parse_expenses_summary_envelope,
    parse_monthly_summary_envelope,
    parse_platform_external_active_envelope,
    parse_report_list_envelope,
    parse_sale_summary_envelope,
    try_parse_data,
)
from app.transform.company_list import company_list_index
from app.transform.expenses_summary import expenses_summary_derived
from app.transform.nubceo_breakdown import breakdown_lines_to_totals
from app.transform.platform_external_active import platform_external_active_index
from app.transform.report_jobs import report_list_derived
from app.transform.sale_monthly_cashflow import (
    cash_flow_adjacent_derived,
    monthly_summary_derived,
    sale_summary_derived,
)

app = FastAPI(title="SAP B1 - Nubceo Middleware", version="0.1.0")


class PushFromSapBody(BaseModel):
    customer_branch_reference: str = Field(..., description="Sucursal cabecera Nubceo (header branch)")
    tax_code: str | None = None
    odata_filter: str | None = Field(None, description="Ej: DocDate ge '2025-03-01'")
    top: int = 50


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/parse-nubceo-json")
def tool_parse_nubceo_json(body: dict[str, Any]) -> dict[str, Any]:
    """
    Pegá el JSON crudo de Respuesta (Nubceo) y devuelve variante detectada + totales si aplica.
    Útil mientras vamos sumando ejemplos reales.
    """
    out = try_parse_data(body)
    v = out["variant"]
    if v == "expenses_detail":
        de = parse_expenses_detail_envelope(body)
        out["derived"] = {"totals_by_entity": breakdown_lines_to_totals(de.data)}
    elif v == "expenses_summary":
        sm = parse_expenses_summary_envelope(body)
        out["derived"] = {"section_totals": expenses_summary_derived(sm.data)}
    elif v == "company_list":
        cl = parse_company_list_envelope(body)
        out["derived"] = company_list_index(cl.data)
    elif v == "platform_external_active":
        pe = parse_platform_external_active_envelope(body)
        out["derived"] = platform_external_active_index(pe.data)
    elif v == "sale_summary":
        out["derived"] = sale_summary_derived(parse_sale_summary_envelope(body).data)
    elif v == "monthly_summary":
        out["derived"] = monthly_summary_derived(parse_monthly_summary_envelope(body).data)
    elif v == "cash_flow_adjacent_month_summary":
        out["derived"] = cash_flow_adjacent_derived(
            parse_cash_flow_adjacent_month_summary_envelope(body).data
        )
    elif v == "report_list":
        out["derived"] = report_list_derived(parse_report_list_envelope(body).data)
    return out


@app.post("/bridge/sales/push-from-sap")
def push_sales_from_sap(body: PushFromSapBody) -> dict[str, Any]:
    """
    Lee facturas SAP y las envía a Nubceo como ventas POS (formato Conciliaciones).
    """
    with SapClient() as sap, NubceoClient() as nub:
        sap.login()
        nub.authenticate()
        raw = sap.get_invoices(top=body.top, odata_filter=body.odata_filter)
        values = raw.get("value") or raw.get("Value") or []
        if not isinstance(values, list):
            raise HTTPException(502, "Respuesta SAP inesperada (sin 'value').")

        sales: list[dict[str, Any]] = []
        for i, inv in enumerate(values):
            if not isinstance(inv, dict):
                continue
            sales.append(
                sap_invoice_to_nubceo_sale(
                    inv,
                    sale_index=i,
                    customer_branch_reference=body.customer_branch_reference,
                    tax_code=body.tax_code,
                )
            )

        if not sales:
            return {"pushed": 0, "nubceo_response": None, "message": "Sin facturas para el filtro."}

        out = nub.insert_sales(settings.nubceo_tenant_id, sales)
        return {"pushed": len(sales), "nubceo_response": out}


@app.get("/proxy/nubceo/sales")
def proxy_nubceo_sales(
    page: int | None = None,
    page_size: int | None = Query(None, alias="pageSize"),
) -> dict[str, Any]:
    """Reexpone GET ventas Nubceo (útil para depurar)."""
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.get_sales(settings.nubceo_tenant_id, params)


@app.get("/proxy/sap/invoices")
def proxy_sap_invoices(
    top: int = 20,
    odata_filter: str | None = None,
) -> dict[str, Any]:
    """Reexpone consulta mínima a Invoices en SAP."""
    with SapClient() as sap:
        sap.login()
        return sap.get_invoices(top=top, odata_filter=odata_filter)
