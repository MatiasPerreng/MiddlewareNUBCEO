"""Totales y vistas derivadas del bloque expenses-summary."""

from __future__ import annotations

from app.schemas.nubceo_responses import ExpensesSummaryData, NamedAmountRow


def sum_rows(rows: list[NamedAmountRow]) -> float:
    return sum(r.amount for r in rows)


def expenses_summary_derived(data: ExpensesSummaryData) -> dict[str, float]:
    """Suma por bloque y total global."""
    s_tax = sum_rows(data.tax)
    s_ded = sum_rows(data.deduction)
    s_sum = sum_rows(data.summary)
    return {
        "summary_block_total": s_sum,
        "tax_total": s_tax,
        "deduction_total": s_ded,
        "cross_check_tax_plus_deduction": s_tax + s_ded,
    }
