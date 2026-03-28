"""Unifica try_parse_data + derivados (POST /tools y GET /dev/parse-sample)."""

from __future__ import annotations

from typing import Any

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


def parse_nubceo_with_derived(body: dict[str, Any]) -> dict[str, Any]:
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
