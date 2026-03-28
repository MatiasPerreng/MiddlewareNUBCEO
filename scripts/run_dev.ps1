# Recarga código al guardar .py. JSON: editá dev_samples/sample.json y abrí /dev/parse-sample
#
# Importante: al navegar nubceo.com en el navegador, esas peticiones NO pasan por este puerto.
# Solo verás [in] lo que pegues a http://127.0.0.1:8000/... y [nubceo]/[sap] cuando el middleware llame APIs.
# Para ver todo el tráfico del navegador: F12 > Red, o: mitmproxy -p 8080 y proxy del sistema en 127.0.0.1:8080
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:PYTHONPATH = "."
$env:DEBUG = "true"
if (-not (Test-Path .env)) { Copy-Item .env.example .env -ErrorAction SilentlyContinue }
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
