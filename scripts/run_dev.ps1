# Recarga código Python al guardar (.py). JSON: editá dev_samples/sample.json y refrescá /dev/parse-sample
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:PYTHONPATH = "."
$env:DEBUG = "true"
if (-not (Test-Path .env)) { Copy-Item .env.example .env -ErrorAction SilentlyContinue }
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
