"""Cliente HTTP para SAP Business One Service Layer (sesión B1SESSION + ROUTEID)."""

from __future__ import annotations

import httpx

from app.config import settings
from app.httpx_debug import httpx_event_hooks


class SapClient:
    def __init__(self) -> None:
        base = settings.sap_base_url.rstrip("/")
        self._base = base
        self._client = httpx.Client(
            base_url=base,
            timeout=120.0,
            event_hooks=httpx_event_hooks("sap"),
        )
        self._logged_in = False

    def close(self) -> None:
        if self._logged_in:
            try:
                self._client.post("/Logout")
            except httpx.HTTPError:
                pass
        self._client.close()

    def __enter__(self) -> SapClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def login(self) -> dict:
        r = self._client.post(
            "/Login",
            json={
                "CompanyDB": settings.sap_company_db,
                "UserName": settings.sap_user,
                "Password": settings.sap_password,
            },
        )
        r.raise_for_status()
        self._logged_in = True
        return r.json()

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        if not self._logged_in:
            self.login()
        url = path if path.startswith("/") else f"/{path}"
        return self._client.request(method, url, **kwargs)

    def get_json(self, path: str, **kwargs: object) -> dict | list:
        r = self.request("GET", path, **kwargs)
        r.raise_for_status()
        return r.json()

    def get_invoices(
        self,
        *,
        top: int = 100,
        skip: int = 0,
        odata_filter: str | None = None,
        orderby: str | None = None,
        expand: str | None = None,
    ) -> dict:
        """Consulta facturas de deudores (Invoices). Ajustá $filter a tu necesidad."""
        params: dict[str, str | int] = {"$top": top, "$skip": skip}
        if odata_filter:
            params["$filter"] = odata_filter
        if orderby:
            params["$orderby"] = orderby
        if expand:
            params["$expand"] = expand
        r = self.request("GET", "/Invoices", params=params)
        r.raise_for_status()
        return r.json()

    def get_invoice(self, doc_entry: int) -> dict:
        return self.get_json(f"/Invoices({doc_entry})")  # type: ignore[return-value]
