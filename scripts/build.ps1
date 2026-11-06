param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 richiesto.' }
$buildPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $buildPython -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze fallita.' }
& $buildPython scripts/collect_licenses.py
& $buildPython -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw 'Test falliti: build interrotta.' }
& $buildPython scripts/build.py
if ($LASTEXITCODE -ne 0) { throw 'Build fallita.' }
