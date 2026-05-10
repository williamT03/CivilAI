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
    # Run only the backend integration test module. This exercises the mounted
    # FastAPI backend with the structured DB/Chroma stack and a stubbed LLM call.
    & $pythonExe -m unittest backend.CustomRAG.test.test_backend_integration -v
}
finally {
    Pop-Location
}
