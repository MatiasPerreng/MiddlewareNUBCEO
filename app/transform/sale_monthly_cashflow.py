"""Derivados simples para SALE/SUMMARY, MONTHLY-SUMMARY y CASH-FLOW-ADJACENT-MONTH."""

from __future__ import annotations

from app.schemas.nubceo_responses import (
    CashFlowAdjacentMonthSummaryData,
    MonthlySummaryData,
    SaleSummaryData,
)


def sale_summary_derived(d: SaleSummaryData) -> dict[str, float | int]:
    last, cur = d.last, d.current
    return {
        "delta_qty": int(cur.qty) - int(last.qty),
        "delta_gross": float(cur.grossAmount) - float(last.grossAmount),
        "delta_net": float(cur.netAmount) - float(last.netAmount),
    }


def monthly_summary_derived(d: MonthlySummaryData) -> dict[str, float]:
    c = d.collections
    three = d.lastThreeMonthsSummary
    return {
        "collections_next_month_amount": float(c.nextMonth.amount),
        "sum_last_three_income": sum(float(x.income) for x in three),
        "sum_last_three_taxes": sum(float(x.taxes) for x in three),
        "sum_last_three_deductions": sum(float(x.deductions) for x in three),
    }


def cash_flow_adjacent_derived(d: CashFlowAdjacentMonthSummaryData) -> dict[str, float]:
    prev, nxt = float(d.prev), float(d.next)
    return {"prev": prev, "next": nxt, "next_minus_prev": nxt - prev}
