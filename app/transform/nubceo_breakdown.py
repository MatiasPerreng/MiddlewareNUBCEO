"""
Transformaciones sobre respuestas Nubceo ya parseadas (ej. desglose fiscal/comisiones).
Cuando tengamos reglas SAP ↔ typeCode, se amplía aquí o en mappers dedicados.
"""

from __future__ import annotations

from collections import defaultdict

from app.schemas.nubceo_responses import BreakdownLine


def breakdown_lines_to_totals(lines: list[BreakdownLine]) -> dict[str, float]:
    """Suma por entity (deduction / tax) y total general."""
    by_entity: dict[str, float] = defaultdict(float)
    for line in lines:
        by_entity[line.entity] += line.amount
    total = sum(by_entity.values(), 0.0)
    return {**dict(by_entity), "total": total}
