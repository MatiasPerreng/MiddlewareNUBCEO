"""Cliente para Nubceo Connect API (JWT Bearer)."""

from __future__ import annotations

import httpx

from app.config import settings


class NubceoClient:
    def __init__(self) -> None:
        self._base = settings.nubceo_base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=120.0)
        self._token: str | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NubceoClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def authenticate(self) -> str:
        r = self._client.post(
            "/authenticate",
            json={"API_KEY": settings.nubceo_api_key, "API_SECRET": settings.nubceo_api_secret},
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def insert_sales(self, tenant_id: str, body: list | dict) -> dict:
        r = self._client.post(
            f"/v1/tenants/{tenant_id}/reconciler/sales",
            json=body,
            headers=self._headers(),
        )
        return self._parse(r)

    def get_sales(self, tenant_id: str, params: dict | None = None) -> dict:
        r = self._client.get(
            f"/v1/tenants/{tenant_id}/reconciler/sales",
            params=params or {},
            headers=self._headers(),
        )
        return self._parse(r)

    def update_sale(self, tenant_id: str, company_id: str, sale_id: str, body: list | dict) -> dict:
        from urllib.parse import quote

        sid = quote(sale_id, safe="")
        r = self._client.put(
            f"/v1/tenants/{tenant_id}/{company_id}/reconciler/sales/{sid}",
            json=body,
            headers=self._headers(),
        )
        return self._parse(r)

    def delete_sales(self, tenant_id: str, company_id: str, sale_ids: list[str]) -> dict:
        r = self._client.post(
            f"/v1/tenants/{tenant_id}/{company_id}/reconciler/sales/delete",
            json=sale_ids,
            headers=self._headers(),
        )
        return self._parse(r)

    def get_companies(self, tenant_id: str, params: dict | None = None) -> dict:
        # El PDF indica /v1/tenants/tenants/:id/companies — verificá en Swagger si hay typo.
        r = self._client.get(
            f"/v1/tenants/tenants/{tenant_id}/companies",
            params=params or {},
            headers=self._headers(),
        )
        if r.status_code == 404:
            r = self._client.get(
                f"/v1/tenants/{tenant_id}/companies",
                params=params or {},
                headers=self._headers(),
            )
        return self._parse(r)

    def get_ledger_headers(self, tenant_id: str, params: dict | None = None) -> dict:
        r = self._client.get(
            f"/v1/tenants/{tenant_id}/accounting/ledger-header",
            params=params or {},
            headers=self._headers(),
        )
        return self._parse(r)

    @staticmethod
    def _parse(r: httpx.Response) -> dict:
        r.raise_for_status()
        if not r.content:
            return {}
        return r.json()
