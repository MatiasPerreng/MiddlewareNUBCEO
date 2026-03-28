"""
API intermedia: orquesta SAP Service Layer y Nubceo Connect.
Las rutas son ejemplos; adaptá paths y mapeos al contrato de tu WEB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.clients.nubceo import NubceoClient
from app.clients.sap import SapClient
from app.config import settings
from app.mappers.sales import sap_invoice_to_nubceo_sale
from app.parse_pipeline import parse_nubceo_with_derived

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
    return parse_nubceo_with_derived(body)


@app.get("/dev/parse-sample")
def dev_parse_sample() -> dict[str, Any]:
    """
    Solo con DEBUG=true. Lee `dev_samples/sample.json` (o DEV_SAMPLE_PATH) en cada request:
    editás el archivo, guardás, refrescás el navegador y ves el parseo sin re-postear.
    """
    if not settings.debug:
        raise HTTPException(404, "Activa DEBUG=true en .env para usar /dev/parse-sample")
    path = Path(settings.dev_sample_path)
    if not path.is_file():
        raise HTTPException(
            404,
            f"No existe el archivo: {path.resolve()}. Creá dev_samples/sample.json o ajustá DEV_SAMPLE_PATH.",
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON inválido en {path}: {e}") from e
    if not isinstance(body, dict):
        raise HTTPException(400, "El JSON raíz debe ser un objeto { ... }")
    return parse_nubceo_with_derived(body)


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
