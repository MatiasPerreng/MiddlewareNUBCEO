from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    debug: bool = False
    """Si es true, habilita /dev/parse-sample para iterar JSON desde disco."""

    dev_sample_path: str = "dev_samples/sample.json"
    """Ruta al JSON de prueba (relativa al cwd donde corre uvicorn)."""

    sap_base_url: str = "https://localhost:50000/b1s/v1"
    sap_company_db: str = ""
    sap_user: str = ""
    sap_password: str = ""

    nubceo_base_url: str = "https://connectapi.nubceo.com"
    nubceo_api_key: str = ""
    nubceo_api_secret: str = ""
    nubceo_tenant_id: str = ""
    nubceo_default_company_id: str | None = None


settings = Settings()
