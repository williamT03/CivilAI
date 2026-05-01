$ErrorActionPreference = "Stop"

# Resolve the repo root from the current test directory so this script keeps
# working even when run from another shell location.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Project venv Python was not found at '$pythonExe'."
}

Push-Location $repoRoot
try {
    # Run the full CustomRAG test suite through the project virtualenv so local
    # Conda/Python installations do not interfere with imports or dependencies.
    & $pythonExe -m unittest discover -s backend\CustomRAG\test -v
}
finally {
    Pop-Location
}
