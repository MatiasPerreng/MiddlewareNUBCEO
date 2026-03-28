"""
Esquemas Pydantic alineados a respuestas reales de APIs Nubceo (api / connect).
Se van ampliando con cada JSON de muestra que pases.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class NubceoMeta(BaseModel):
    count: int
    total: int
    pages: int | None = None
    requestId: str | None = None


class NubceoEnvelope(BaseModel):
    """Sobre genérico: data puede ser objeto, lista o vacío según endpoint."""

    status: int
    meta: NubceoMeta
    data: Any


class ExpensesDetailLine(BaseModel):
    """expenses-detail: lista plana con entity / typeCode / typeName / amount."""

    entity: Literal["deduction", "tax"] | str
    typeCode: str
    typeName: str
    amount: float


# Alias retrocompatible con el nombre anterior
BreakdownLine = ExpensesDetailLine


class ExpensesDetailEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: list[ExpensesDetailLine]


BreakdownEnvelope = ExpensesDetailEnvelope


class NamedAmountRow(BaseModel):
    name: str
    amount: float


class ExpensesSummaryData(BaseModel):
    """expenses-summary: bloques summary / tax / deduction."""

    summary: list[NamedAmountRow]
    tax: list[NamedAmountRow]
    deduction: list[NamedAmountRow]


class ExpensesSummaryEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: ExpensesSummaryData


class CompanyAddress(BaseModel):
    """Dirección anidada en company (endpoint company?filter...)."""

    model_config = ConfigDict(extra="allow")

    id: int | str
    tenantId: int
    street: str | None = None
    number: str | None = None
    city: str | None = None
    postalCode: str | None = None
    state: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class CompanyRecord(BaseModel):
    """Ítem de listado de compañías (Nubceo)."""

    model_config = ConfigDict(extra="allow")

    id: str | int
    tenantId: int
    addressId: int | None = None
    countryCode: str | None = None
    category: str | None = None
    name: str
    taxCode: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    deletedAt: str | None = None
    Address: CompanyAddress
    enabled: bool | None = None


class CompanyListEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: list[CompanyRecord]


class BranchPlatformExternalItem(BaseModel):
    """Plataforma vinculada a una sucursal (branch?filter)."""

    model_config = ConfigDict(extra="allow")

    id: str | int
    platformExternalCode: str
    externalCode: str


class BranchCompanySnippet(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    taxCode: str | None = None


class BranchRecord(BaseModel):
    """Sucursal con PlatformExternals y Company embebido (branch?filter)."""

    model_config = ConfigDict(extra="allow")

    id: str | int
    tenantId: str | int
    companyId: str | int
    addressId: str | int | None = None
    branchRelatedId: str | int | None = None
    name: str | None = None
    headerBranchId: str | int | None = None
    TOTAL: str | int | float | None = None
    PlatformExternals: list[BranchPlatformExternalItem]
    Company: BranchCompanySnippet
    relatedBranches: list[Any] = Field(default_factory=list)
    relatedPlatformExternalCodes: list[str] = Field(default_factory=list)


class BranchListEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: list[BranchRecord]


class PlatformExternalInfo(BaseModel):
    """Objeto anidado en plataformas activas (SELF-PLATFORM-EXTERNAL-ACTIVE)."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    type: str | None = None


class PlatformExternalActiveRecord(BaseModel):
    """Ítem de /SELF-PLATFORM-EXTERNAL-ACTIVE (plataformas externas por compañía)."""

    model_config = ConfigDict(extra="allow")

    platformExternalCode: str
    id: int | str
    username: str | None = None
    codeAux: str | None = None
    codeAux2: str | None = None
    codeAux3: str | None = None
    codeAux4: str | None = None
    failureCount: int | None = None
    failureAuthCount: int | None = None
    retryFast: int | None = None
    companyId: int | str
    createdAt: str | None = None
    updatedAt: str | None = None
    deletedAt: str | None = None
    PlatformExternal: PlatformExternalInfo
    setupCompleted: bool | None = None


class PlatformExternalActiveListEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: list[PlatformExternalActiveRecord]


# --- Cashflow / ventas / reportes (api.nubceo.com v2) ---


class CashFlowAdjacentMonthSummaryData(BaseModel):
    """CASH-FLOW-ADJACENT-MONTH-SUMMARY (prev/next mes adyacente)."""

    prev: float | int
    next: float | int


class CashFlowAdjacentMonthSummaryEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: CashFlowAdjacentMonthSummaryData


class SaleSummaryBucket(BaseModel):
    qty: float | int
    grossAmount: float
    netAmount: float


class SaleSummaryData(BaseModel):
    """SALE/SUMMARY."""

    last: SaleSummaryBucket
    current: SaleSummaryBucket


class SaleSummaryEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: SaleSummaryData


class CollectionsDateAmount(BaseModel):
    date: str
    amount: float | int


class CollectionsData(BaseModel):
    today: CollectionsDateAmount
    currentMonth: CollectionsDateAmount
    next: CollectionsDateAmount
    nextMonth: CollectionsDateAmount


class LastThreeMonthRow(BaseModel):
    month: str
    income: float | int
    taxes: float | int
    deductions: float | int


class MonthlySummaryData(BaseModel):
    """MONTHLY-SUMMARY."""

    collections: CollectionsData
    lastThreeMonthsSummary: list[LastThreeMonthRow]


class MonthlySummaryEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: MonthlySummaryData


class ReportJobRecord(BaseModel):
    """REPORT?sort — trabajos de export (xlsx) con filtros serializados."""

    model_config = ConfigDict(extra="allow")

    id: str
    userId: str | None = None
    tenantId: str | int | None = None
    type: str | None = None
    format: str | None = None
    filters: str | None = None
    status: str | None = None
    statusDetail: str | None = None
    fileUrl: str | None = None
    expiryDate: str | None = None
    fileNameTemplate: str | None = None
    origin: str | None = None
    requestId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ReportListEnvelope(BaseModel):
    status: int
    meta: NubceoMeta
    data: list[ReportJobRecord]


VARIANT_ENDPOINT_LABELS: dict[str, str] = {
    "expenses_summary": "expenses-summary",
    "expenses_detail": "expenses-detail",
    "branch_list": "branch?filter",
    "company_list": "company?filter",
    "platform_external_active": "SELF-PLATFORM-EXTERNAL-ACTIVE",
    "cash_flow_adjacent_month_summary": "CASH-FLOW-ADJACENT-MONTH-SUMMARY",
    "sale_summary": "SALE/SUMMARY",
    "monthly_summary": "MONTHLY-SUMMARY",
    "report_list": "REPORT?sort",
    "generic": "?",
}


def _looks_like_branch_row(d: dict[str, Any]) -> bool:
    """branch?filter: PlatformExternals + Company + relatedPlatformExternalCodes."""
    if not isinstance(d.get("PlatformExternals"), list):
        return False
    if not isinstance(d.get("Company"), dict):
        return False
    return "relatedPlatformExternalCodes" in d and "companyId" in d


def _looks_like_monthly_summary(data: dict[str, Any]) -> bool:
    return "collections" in data and "lastThreeMonthsSummary" in data


def _looks_like_sale_summary(data: dict[str, Any]) -> bool:
    last = data.get("last")
    cur = data.get("current")
    if not isinstance(last, dict) or not isinstance(cur, dict):
        return False
    return "grossAmount" in last and "grossAmount" in cur and "qty" in last


def _looks_like_cash_flow_adjacent_month(data: dict[str, Any]) -> bool:
    if "prev" not in data or "next" not in data:
        return False
    if _looks_like_monthly_summary(data) or _looks_like_sale_summary(data):
        return False
    return isinstance(data.get("prev"), (int, float)) and isinstance(data.get("next"), (int, float))


def _looks_like_report_job_row(d: dict[str, Any]) -> bool:
    return bool(
        "fileUrl" in d
        and isinstance(d.get("filters"), str)
        and d.get("format")
        and isinstance(d.get("User"), dict)
    )


def _looks_like_company_row(d: dict[str, Any]) -> bool:
    """Heurística: company list vs otras listas (p. ej. expenses-detail)."""
    if not isinstance(d.get("Address"), dict):
        return False
    if d.get("tenantId") is None or d.get("name") is None:
        return False
    if "entity" in d and "typeCode" in d and "typeName" in d:
        return False
    return "addressId" in d or "taxCode" in d or "category" in d


def _looks_like_platform_external_active_row(d: dict[str, Any]) -> bool:
    """Plataformas activas: platformExternalCode + companyId + PlatformExternal."""
    if not isinstance(d.get("PlatformExternal"), dict):
        return False
    return "platformExternalCode" in d and "companyId" in d


def parse_nubceo_json(raw: dict[str, Any]) -> NubceoEnvelope:
    """Valida el sobre común; no fuerza el tipo interno de data."""
    return NubceoEnvelope.model_validate(raw)


def parse_expenses_detail_envelope(raw: dict[str, Any]) -> ExpensesDetailEnvelope:
    """expenses-detail: data es list[entity, typeCode, typeName, amount]."""
    return ExpensesDetailEnvelope.model_validate(raw)


def parse_breakdown_envelope(raw: dict[str, Any]) -> ExpensesDetailEnvelope:
    """Alias de parse_expenses_detail_envelope."""
    return parse_expenses_detail_envelope(raw)


def parse_expenses_summary_envelope(raw: dict[str, Any]) -> ExpensesSummaryEnvelope:
    """expenses-summary: data.summary | data.tax | data.deduction."""
    return ExpensesSummaryEnvelope.model_validate(raw)


def parse_company_list_envelope(raw: dict[str, Any]) -> CompanyListEnvelope:
    """company?filter...: data es list[CompanyRecord]."""
    return CompanyListEnvelope.model_validate(raw)


def parse_branch_list_envelope(raw: dict[str, Any]) -> BranchListEnvelope:
    """branch?filter: data es list[BranchRecord]."""
    return BranchListEnvelope.model_validate(raw)


def parse_platform_external_active_envelope(raw: dict[str, Any]) -> PlatformExternalActiveListEnvelope:
    """SELF-PLATFORM-EXTERNAL-ACTIVE: data es list[PlatformExternalActiveRecord]."""
    return PlatformExternalActiveListEnvelope.model_validate(raw)


def parse_cash_flow_adjacent_month_summary_envelope(raw: dict[str, Any]) -> CashFlowAdjacentMonthSummaryEnvelope:
    """CASH-FLOW-ADJACENT-MONTH-SUMMARY."""
    return CashFlowAdjacentMonthSummaryEnvelope.model_validate(raw)


def parse_sale_summary_envelope(raw: dict[str, Any]) -> SaleSummaryEnvelope:
    """SALE/SUMMARY."""
    return SaleSummaryEnvelope.model_validate(raw)


def parse_monthly_summary_envelope(raw: dict[str, Any]) -> MonthlySummaryEnvelope:
    """MONTHLY-SUMMARY."""
    return MonthlySummaryEnvelope.model_validate(raw)


def parse_report_list_envelope(raw: dict[str, Any]) -> ReportListEnvelope:
    """REPORT?sort."""
    return ReportListEnvelope.model_validate(raw)


def try_parse_data(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Intenta reconocer variantes conocidas. Si no matchea, devuelve el envelope genérico.
    Incluye endpoint_label cuando hay mapeo en VARIANT_ENDPOINT_LABELS.
    """
    env = parse_nubceo_json(raw)
    data = env.data
    variant = "generic"
    parsed: Any = data

    if isinstance(data, dict) and all(k in data for k in ("summary", "tax", "deduction")):
        try:
            inner = {
                "summary": data["summary"],
                "tax": data["tax"],
                "deduction": data["deduction"],
            }
            sm = ExpensesSummaryData.model_validate(inner)
            variant = "expenses_summary"
            parsed = sm.model_dump()
        except Exception:
            pass

    if variant == "generic" and isinstance(data, dict):
        if _looks_like_monthly_summary(data):
            try:
                ms = MonthlySummaryData.model_validate(data)
                variant = "monthly_summary"
                parsed = ms.model_dump()
            except Exception:
                pass
        elif _looks_like_sale_summary(data):
            try:
                ss = SaleSummaryData.model_validate(data)
                variant = "sale_summary"
                parsed = ss.model_dump()
            except Exception:
                pass
        elif _looks_like_cash_flow_adjacent_month(data):
            try:
                cf = CashFlowAdjacentMonthSummaryData.model_validate(data)
                variant = "cash_flow_adjacent_month_summary"
                parsed = cf.model_dump()
            except Exception:
                pass

    if variant == "generic" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and _looks_like_branch_row(first):
            try:
                parsed_models = TypeAdapter(list[BranchRecord]).validate_python(data)
                variant = "branch_list"
                parsed = [m.model_dump() for m in parsed_models]
            except Exception:
                pass

    if variant == "generic" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and _looks_like_company_row(first):
            try:
                parsed_models = TypeAdapter(list[CompanyRecord]).validate_python(data)
                variant = "company_list"
                parsed = [m.model_dump() for m in parsed_models]
            except Exception:
                pass

    if variant == "generic" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and _looks_like_platform_external_active_row(first):
            try:
                parsed_models = TypeAdapter(list[PlatformExternalActiveRecord]).validate_python(data)
                variant = "platform_external_active"
                parsed = [m.model_dump() for m in parsed_models]
            except Exception:
                pass

    if variant == "generic" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and _looks_like_report_job_row(first):
            try:
                parsed_models = TypeAdapter(list[ReportJobRecord]).validate_python(data)
                variant = "report_list"
                parsed = [m.model_dump() for m in parsed_models]
            except Exception:
                pass

    if variant == "generic" and isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and "entity" in first and "amount" in first:
            try:
                parsed_models = TypeAdapter(list[ExpensesDetailLine]).validate_python(data)
                variant = "expenses_detail"
                parsed = [m.model_dump() for m in parsed_models]
            except Exception:
                pass

    return {
        "variant": variant,
        "endpoint_label": VARIANT_ENDPOINT_LABELS.get(variant),
        "status": env.status,
        "meta": env.meta.model_dump(),
        "data": parsed,
    }
