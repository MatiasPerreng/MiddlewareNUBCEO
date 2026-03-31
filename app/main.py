"""
API intermedia: orquesta SAP Service Layer y Nubceo Connect.
Las rutas son ejemplos; adaptá paths y mapeos al contrato de tu WEB.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.requests import Request

from app.clients.nubceo import NubceoClient
from app.clients.sap import SapClient
from app.config import settings
from app.mappers.sales import sap_invoice_to_nubceo_sale
from app.parse_pipeline import parse_nubceo_with_derived

_log_in = logging.getLogger("middleware.incoming")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.debug:
        logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
        _log_in.info(
            "DEBUG=true: [in] = peticiones a este servidor (localhost). "
            "[nubceo]/[sap] = salientes del middleware."
        )
        _log_in.info(
            "El navegador hacia nubceo.com NO pasa por uvicorn; usá F12 Red o mitmproxy para eso."
        )
    yield


app = FastAPI(title="SAP B1 - Nubceo Middleware", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def log_incoming_requests(request: Request, call_next):
    response = await call_next(request)
    if settings.debug:
        _log_in.info("[in] %s %s -> %s", request.method, request.url.path, response.status_code)
    return response


class PushFromSapBody(BaseModel):
    customer_branch_reference: str = Field(..., description="Sucursal cabecera Nubceo (header branch)")
    tax_code: str | None = None
    odata_filter: str | None = Field(None, description="Ej: DocDate ge '2025-03-01'")
    doc_date_from: str | None = Field(None, description="Atajo: fecha desde (YYYY-MM-DD) para DocDate")
    doc_date_to: str | None = Field(None, description="Atajo: fecha hasta (YYYY-MM-DD) para DocDate")
    card_code: str | None = Field(None, description="Atajo: filtro exacto de cliente SAP (CardCode)")
    top: int = 50
    include_credit_notes: bool = True
    sap_page_size: int = Field(100, ge=1, le=500)
    max_records: int | None = Field(None, ge=1, description="Límite global de docs SAP a procesar")
    nubceo_batch_size: int = Field(500, ge=1, le=500)
    platform_external_code: str | None = None


class NubceoUpdateSaleBody(BaseModel):
    company_id: str | None = Field(None, description="CompanyId de Nubceo. Si falta, usa NUBCEO_DEFAULT_COMPANY_ID")
    sale_id: str
    sale: dict[str, Any]


class NubceoDeleteSalesBody(BaseModel):
    company_id: str | None = Field(None, description="CompanyId de Nubceo. Si falta, usa NUBCEO_DEFAULT_COMPANY_ID")
    sale_ids: list[str] = Field(..., min_length=1, max_length=500)


class LedgerStatusBody(BaseModel):
    status: str = Field(..., description="confirmed o not_confirmed")
    ids: list[str] = Field(..., min_length=1)


class SyncFromSapBody(PushFromSapBody):
    async_mode: bool = True
    wait_for_completion: bool = False
    poll_seconds: float = Field(2.0, ge=0.5, le=10.0)
    timeout_seconds: int = Field(120, ge=5, le=1800)
    dry_run: bool = False
    continue_on_batch_error: bool = True
    retry_attempts: int = Field(2, ge=0, le=5)
    retry_delay_seconds: float = Field(1.5, ge=0.0, le=30.0)


def _extract_value_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("value") or raw.get("Value") or []
    if not isinstance(values, list):
        raise HTTPException(502, "Respuesta SAP inesperada (sin 'value').")
    return [x for x in values if isinstance(x, dict)]


def _fetch_sap_documents(
    sap: SapClient,
    *,
    include_credit_notes: bool,
    odata_filter: str | None,
    page_size: int,
    max_records: int | None,
) -> list[tuple[dict[str, Any], str]]:
    rows: list[tuple[dict[str, Any], str]] = []
    skip = 0
    while True:
        inv_page = _extract_value_list(
            sap.get_invoices(top=page_size, skip=skip, odata_filter=odata_filter, orderby="DocDate asc,DocEntry asc")
        )
        rows.extend((inv, "invoice") for inv in inv_page)
        if max_records and len(rows) >= max_records:
            return rows[:max_records]
        if len(inv_page) < page_size:
            break
        skip += page_size

    if not include_credit_notes:
        return rows

    skip = 0
    while True:
        cn_page = _extract_value_list(
            sap.get_credit_notes(top=page_size, skip=skip, odata_filter=odata_filter, orderby="DocDate asc,DocEntry asc")
        )
        rows.extend((cn, "creditNote") for cn in cn_page)
        if max_records and len(rows) >= max_records:
            return rows[:max_records]
        if len(cn_page) < page_size:
            break
        skip += page_size
    return rows


def _compose_odata_filter(body: PushFromSapBody) -> str | None:
    def _escape_odata(value: str) -> str:
        # OData string literal escaping: single quote becomes doubled quote.
        return value.replace("'", "''")

    def _validate_date(value: str, field_name: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(400, f"{field_name} inválida: '{value}'. Formato esperado YYYY-MM-DD") from exc
        return value

    parts: list[str] = []
    if body.odata_filter:
        parts.append(f"({body.odata_filter})")
    if body.doc_date_from:
        safe_from = _validate_date(body.doc_date_from, "doc_date_from")
        parts.append(f"(DocDate ge '{safe_from}')")
    if body.doc_date_to:
        safe_to = _validate_date(body.doc_date_to, "doc_date_to")
        parts.append(f"(DocDate le '{safe_to}')")
    if body.card_code:
        safe_card_code = _escape_odata(body.card_code)
        parts.append(f"(CardCode eq '{safe_card_code}')")
    if not parts:
        return None
    return " and ".join(parts)


def _build_nubceo_sales(rows: list[tuple[dict[str, Any], str]], body: PushFromSapBody) -> list[dict[str, Any]]:
    sales: list[dict[str, Any]] = []
    for i, (doc, doc_type) in enumerate(rows):
        sales.append(
            sap_invoice_to_nubceo_sale(
                doc,
                sale_index=i,
                customer_branch_reference=body.customer_branch_reference,
                tax_code=body.tax_code,
                platform_external_code=body.platform_external_code,
                document_type=doc_type,
            )
        )
    return sales


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _extract_request_id(resp: dict[str, Any]) -> str | None:
    for key in ("id", "requestId", "request_id"):
        value = resp.get(key)
        if isinstance(value, str) and value:
            return value
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("id", "requestId", "request_id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _sale_validation_errors(sale: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ("customerBranchReference", "date", "currencyCode", "type", "id", "taxAmount", "netAmount", "grossAmount")
    for field in required:
        if field not in sale or sale[field] in (None, ""):
            errors.append(f"missing:{field}")

    gross = sale.get("grossAmount")
    net = sale.get("netAmount")
    tax = sale.get("taxAmount")
    if isinstance(gross, (int, float)) and isinstance(net, (int, float)) and isinstance(tax, (int, float)):
        if round(float(net) + float(tax), 2) != round(float(gross), 2):
            errors.append("invalid_amount_equation: grossAmount != netAmount + taxAmount")

    related = sale.get("relatedPayments")
    if not isinstance(related, list) or not related:
        errors.append("missing:relatedPayments")
    else:
        for pidx, payment in enumerate(related):
            if not isinstance(payment, dict):
                errors.append(f"invalid:relatedPayments[{pidx}]")
                continue
            for pf in ("presentedDate", "grossAmount", "id"):
                if pf not in payment or payment[pf] in (None, ""):
                    errors.append(f"missing:relatedPayments[{pidx}].{pf}")
    return errors


def _validate_sales_payload(sales: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, sale in enumerate(sales):
        errs = _sale_validation_errors(sale)
        if errs:
            out.append({"index": idx, "saleId": sale.get("id"), "errors": errs})
    return out


def _sales_summary(sales: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    gross_total = 0.0
    net_total = 0.0
    tax_total = 0.0
    payments = 0
    for sale in sales:
        typ = str(sale.get("type") or "unknown")
        by_type[typ] = by_type.get(typ, 0) + 1
        gross_total += float(sale.get("grossAmount") or 0.0)
        net_total += float(sale.get("netAmount") or 0.0)
        tax_total += float(sale.get("taxAmount") or 0.0)
        rel = sale.get("relatedPayments")
        if isinstance(rel, list):
            payments += len(rel)
    return {
        "count": len(sales),
        "by_type": by_type,
        "totals": {"grossAmount": round(gross_total, 2), "netAmount": round(net_total, 2), "taxAmount": round(tax_total, 2)},
        "related_payments_count": payments,
    }


def _http_error_to_detail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError):
        response_text = ""
        try:
            response_text = exc.response.text
        except Exception:
            response_text = "<no-response-text>"
        return {"type": "HTTPStatusError", "status_code": exc.response.status_code, "message": str(exc), "response": response_text}
    if isinstance(exc, httpx.HTTPError):
        return {"type": "HTTPError", "message": str(exc)}
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _extract_inserted_sales_count(detail: dict[str, Any]) -> int:
    data = detail.get("data")
    if not isinstance(data, dict):
        return 0
    response = data.get("response")
    if not isinstance(response, dict):
        return 0
    summary = response.get("summary")
    if not isinstance(summary, dict):
        return 0
    total_inserted = summary.get("totalPosSalesInserted")
    if isinstance(total_inserted, int):
        return total_inserted
    if isinstance(total_inserted, float):
        return int(total_inserted)
    return 0


def _summarize_wait_results(wait_result: dict[str, Any]) -> dict[str, Any]:
    raw_results = wait_result.get("results")
    if not isinstance(raw_results, dict):
        return {"finalized_requests": 0, "status_counts": {}, "confirmed_inserted_sales": 0}

    status_counts: dict[str, int] = {}
    confirmed_inserted_sales = 0
    for detail in raw_results.values():
        status = ""
        if isinstance(detail, dict):
            data = detail.get("data")
            if isinstance(data, dict):
                status = str(data.get("status") or "")
                confirmed_inserted_sales += _extract_inserted_sales_count(detail)
        status = status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "finalized_requests": len(raw_results),
        "status_counts": status_counts,
        "confirmed_inserted_sales": confirmed_inserted_sales,
    }


def _send_batch_with_retry(
    *,
    send_fn: Any,
    batch: list[dict[str, Any]],
    retry_attempts: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(retry_attempts + 1):
        try:
            return send_fn(batch)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retry_attempts:
                break
            time.sleep(retry_delay_seconds)
    if last_exc is None:
        raise HTTPException(500, "Error inesperado al enviar batch")
    raise last_exc


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
        max_records = body.top if body.max_records is None else min(body.top, body.max_records)
        merged_filter = _compose_odata_filter(body)
        rows = _fetch_sap_documents(
            sap,
            include_credit_notes=body.include_credit_notes,
            odata_filter=merged_filter,
            page_size=body.sap_page_size,
            max_records=max_records,
        )
        sales = _build_nubceo_sales(rows, body)

        if not sales:
            return {"pushed": 0, "batches": 0, "nubceo_responses": [], "message": "Sin facturas para el filtro."}

        responses: list[dict[str, Any]] = []
        for batch in _chunks(sales, body.nubceo_batch_size):
            responses.append(nub.insert_sales(settings.nubceo_tenant_id, batch))
        return {
            "pushed": len(sales),
            "summary": _sales_summary(sales),
            "batches": len(responses),
            "nubceo_responses": responses,
        }


@app.post("/bridge/sales/push-from-sap-async")
def push_sales_from_sap_async(body: PushFromSapBody) -> dict[str, Any]:
    """
    Igual que push-from-sap pero inicia carga asíncrona en Nubceo.
    """
    with SapClient() as sap, NubceoClient() as nub:
        sap.login()
        nub.authenticate()
        max_records = body.top if body.max_records is None else min(body.top, body.max_records)
        merged_filter = _compose_odata_filter(body)
        rows = _fetch_sap_documents(
            sap,
            include_credit_notes=body.include_credit_notes,
            odata_filter=merged_filter,
            page_size=body.sap_page_size,
            max_records=max_records,
        )
        sales = _build_nubceo_sales(rows, body)

        if not sales:
            return {"accepted_sales": 0, "batches": 0, "request_ids": [], "nubceo_responses": [], "message": "Sin facturas para el filtro."}

        responses: list[dict[str, Any]] = []
        request_ids: list[str] = []
        for batch in _chunks(sales, body.nubceo_batch_size):
            out = nub.insert_sales_async(settings.nubceo_tenant_id, batch)
            responses.append(out)
            req_id = _extract_request_id(out)
            if req_id:
                request_ids.append(req_id)
        return {
            "accepted_sales": len(sales),
            "summary": _sales_summary(sales),
            "batches": len(responses),
            "request_ids": request_ids,
            "nubceo_responses": responses,
        }


@app.get("/bridge/sales/push-from-sap-async/wait")
def wait_async_processes(
    request_ids: str = Query(..., description="IDs separados por coma devueltos por push-from-sap-async"),
    poll_seconds: float = Query(2.0, ge=0.5, le=10.0),
    timeout_seconds: int = Query(120, ge=5, le=1800),
) -> dict[str, Any]:
    """Hace polling de procesos async Nubceo hasta estado final o timeout."""
    ids = [x.strip() for x in request_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(400, "Debe enviar al menos un request_id.")

    final_statuses = {"finished", "error", "warning", "deleted"}
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    with NubceoClient() as nub:
        nub.authenticate()
        while time.time() < deadline:
            latest = {}
            all_final = True
            for rid in ids:
                detail = nub.get_request_result(settings.nubceo_tenant_id, rid)
                latest[rid] = detail
                status = (((detail.get("data") or {}) if isinstance(detail, dict) else {}).get("status")) or ""
                if status not in final_statuses:
                    all_final = False
            if all_final:
                return {"done": True, "results": latest}
            time.sleep(poll_seconds)
    return {"done": False, "timeout_seconds": timeout_seconds, "results": latest}


@app.post("/bridge/sales/run-sync")
def run_sync_from_sap(body: SyncFromSapBody) -> dict[str, Any]:
    """
    Flujo integral SAP -> Nubceo:
    - extrae docs SAP (facturas + opcional NC)
    - mapea y valida payload
    - envía en lotes sync o async
    - opcionalmente espera finalización de procesos async
    """
    with SapClient() as sap:
        sap.login()
        max_records = body.top if body.max_records is None else min(body.top, body.max_records)
        merged_filter = _compose_odata_filter(body)
        rows = _fetch_sap_documents(
            sap,
            include_credit_notes=body.include_credit_notes,
            odata_filter=merged_filter,
            page_size=body.sap_page_size,
            max_records=max_records,
        )
    sales = _build_nubceo_sales(rows, body)
    validation_errors = _validate_sales_payload(sales)
    if body.dry_run:
        return {
            "dry_run": True,
            "documents_found": len(rows),
            "sales_built": len(sales),
            "summary": _sales_summary(sales),
            "validation_errors": validation_errors,
            "sample": sales[:2],
        }

    if validation_errors:
        raise HTTPException(400, {"message": "Hay errores de validación en payload Nubceo", "errors": validation_errors[:50]})

    if not sales:
        return {"pushed": 0, "batches": 0, "message": "Sin documentos SAP para sincronizar."}

    batch_results: list[dict[str, Any]] = []
    request_ids: list[str] = []
    with NubceoClient() as nub:
        nub.authenticate()
        for bidx, batch in enumerate(_chunks(sales, body.nubceo_batch_size)):
            try:
                if body.async_mode:
                    resp = _send_batch_with_retry(
                        send_fn=lambda data: nub.insert_sales_async(settings.nubceo_tenant_id, data),
                        batch=batch,
                        retry_attempts=body.retry_attempts,
                        retry_delay_seconds=body.retry_delay_seconds,
                    )
                    req_id = _extract_request_id(resp)
                    if req_id:
                        request_ids.append(req_id)
                    batch_results.append({"batch": bidx, "size": len(batch), "ok": True, "request_id": req_id, "response": resp})
                else:
                    resp = _send_batch_with_retry(
                        send_fn=lambda data: nub.insert_sales(settings.nubceo_tenant_id, data),
                        batch=batch,
                        retry_attempts=body.retry_attempts,
                        retry_delay_seconds=body.retry_delay_seconds,
                    )
                    batch_results.append({"batch": bidx, "size": len(batch), "ok": True, "response": resp})
            except Exception as exc:  # noqa: BLE001
                batch_results.append({"batch": bidx, "size": len(batch), "ok": False, "error": _http_error_to_detail(exc)})
                if not body.continue_on_batch_error:
                    break

    result: dict[str, Any] = {
        "accepted_sales": sum(item["size"] for item in batch_results if item.get("ok")),
        "summary": _sales_summary(sales),
        "batches": len(batch_results),
        "failed_batches": sum(1 for item in batch_results if not item.get("ok")),
        "request_ids": request_ids,
        "batch_results": batch_results,
    }

    if body.async_mode and body.wait_for_completion and request_ids:
        ids = ",".join(request_ids)
        wait_result = wait_async_processes(
            request_ids=ids,
            poll_seconds=body.poll_seconds,
            timeout_seconds=body.timeout_seconds,
        )
        result["wait_result"] = wait_result
        result["wait_summary"] = _summarize_wait_results(wait_result)
    return result


@app.post("/bridge/sales/preview-from-sap")
def preview_from_sap(body: PushFromSapBody) -> dict[str, Any]:
    """Extrae y mapea desde SAP pero no envía a Nubceo (prevalidación)."""
    with SapClient() as sap:
        sap.login()
        max_records = body.top if body.max_records is None else min(body.top, body.max_records)
        merged_filter = _compose_odata_filter(body)
        rows = _fetch_sap_documents(
            sap,
            include_credit_notes=body.include_credit_notes,
            odata_filter=merged_filter,
            page_size=body.sap_page_size,
            max_records=max_records,
        )
    sales = _build_nubceo_sales(rows, body)
    validation_errors = _validate_sales_payload(sales)
    return {
        "documents_found": len(rows),
        "sales_built": len(sales),
        "summary": _sales_summary(sales),
        "validation_errors": validation_errors,
        "sample": sales[:5],
    }


@app.get("/bridge/check-connections")
def check_connections() -> dict[str, Any]:
    """
    Smoke test de conectividad/autenticación contra SAP y Nubceo.
    """
    out: dict[str, Any] = {"sap": {"ok": False}, "nubceo": {"ok": False}}
    sap_error: str | None = None
    nub_error: str | None = None

    try:
        with SapClient() as sap:
            login = sap.login()
            out["sap"] = {"ok": True, "session": login.get("SessionId")}
    except Exception as exc:  # noqa: BLE001
        sap_error = str(exc)

    try:
        with NubceoClient() as nub:
            nub.authenticate()
            companies = nub.get_companies(settings.nubceo_tenant_id, params={"pageSize": 1})
            count = 0
            data = companies.get("data") if isinstance(companies, dict) else None
            if isinstance(data, list):
                count = len(data)
            out["nubceo"] = {"ok": True, "companies_probe_count": count}
    except Exception as exc:  # noqa: BLE001
        nub_error = str(exc)

    if sap_error:
        out["sap"]["error"] = sap_error
    if nub_error:
        out["nubceo"]["error"] = nub_error
    out["ok"] = bool(out["sap"]["ok"] and out["nubceo"]["ok"])
    return out


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


@app.post("/proxy/nubceo/sales/update")
def proxy_nubceo_update_sale(body: NubceoUpdateSaleBody) -> dict[str, Any]:
    """Actualiza una venta en Nubceo usando sale_id + company_id."""
    company_id = body.company_id or settings.nubceo_default_company_id
    if not company_id:
        raise HTTPException(400, "Falta company_id (body.company_id o NUBCEO_DEFAULT_COMPANY_ID).")
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.update_sale(settings.nubceo_tenant_id, company_id, body.sale_id, body.sale)


@app.post("/proxy/nubceo/sales/delete")
def proxy_nubceo_delete_sales(body: NubceoDeleteSalesBody) -> dict[str, Any]:
    """Elimina ventas en Nubceo (máx. 500 ids por request)."""
    company_id = body.company_id or settings.nubceo_default_company_id
    if not company_id:
        raise HTTPException(400, "Falta company_id (body.company_id o NUBCEO_DEFAULT_COMPANY_ID).")
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.delete_sales(settings.nubceo_tenant_id, company_id, body.sale_ids)


@app.post("/proxy/nubceo/sales/delete-async")
def proxy_nubceo_delete_sales_async(body: NubceoDeleteSalesBody) -> dict[str, Any]:
    """Inicia borrado asíncrono de ventas en Nubceo."""
    company_id = body.company_id or settings.nubceo_default_company_id
    if not company_id:
        raise HTTPException(400, "Falta company_id (body.company_id o NUBCEO_DEFAULT_COMPANY_ID).")
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.delete_sales_async(settings.nubceo_tenant_id, company_id, body.sale_ids)


@app.get("/proxy/nubceo/request-results")
def proxy_nubceo_request_results(
    page: int | None = None,
    page_size: int | None = Query(None, alias="pageSize"),
) -> dict[str, Any]:
    """Lista procesos asíncronos de inserción/eliminación."""
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.get_request_results(settings.nubceo_tenant_id, params=params)


@app.get("/proxy/nubceo/request-results/{request_id}")
def proxy_nubceo_request_result(request_id: str) -> dict[str, Any]:
    """Detalle de un proceso asíncrono específico."""
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.get_request_result(settings.nubceo_tenant_id, request_id)


@app.get("/proxy/nubceo/companies")
def proxy_nubceo_companies(
    page: int | None = None,
    page_size: int | None = Query(None, alias="pageSize"),
) -> dict[str, Any]:
    """Lista compañías del tenant para resolver companyId/taxCode."""
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.get_companies(settings.nubceo_tenant_id, params=params)


@app.get("/proxy/nubceo/accounting/ledger-headers")
def proxy_nubceo_ledger_headers(
    page: int | None = None,
    page_size: int | None = Query(None, alias="pageSize"),
) -> dict[str, Any]:
    """Lista ledger headers contables de Nubceo."""
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.get_ledger_headers(settings.nubceo_tenant_id, params=params)


@app.patch("/proxy/nubceo/accounting/ledger-headers/status")
def proxy_nubceo_update_ledger_status(body: LedgerStatusBody) -> dict[str, Any]:
    """Actualiza estado de ledger header (confirmed / not_confirmed)."""
    if body.status not in {"confirmed", "not_confirmed"}:
        raise HTTPException(400, "status inválido. Debe ser confirmed o not_confirmed.")
    with NubceoClient() as nub:
        nub.authenticate()
        return nub.update_ledger_header_status(settings.nubceo_tenant_id, body.status, body.ids)


@app.get("/proxy/sap/invoices")
def proxy_sap_invoices(
    top: int = 20,
    odata_filter: str | None = None,
) -> dict[str, Any]:
    """Reexpone consulta mínima a Invoices en SAP."""
    with SapClient() as sap:
        sap.login()
        return sap.get_invoices(top=top, odata_filter=odata_filter)


@app.get("/proxy/sap/credit-notes")
def proxy_sap_credit_notes(
    top: int = 20,
    odata_filter: str | None = None,
) -> dict[str, Any]:
    """Reexpone consulta mínima a CreditNotes en SAP."""
    with SapClient() as sap:
        sap.login()
        return sap.get_credit_notes(top=top, odata_filter=odata_filter)
