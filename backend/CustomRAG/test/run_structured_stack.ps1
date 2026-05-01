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
    # Run the main end-to-end structured stack test module only.
    & $pythonExe -m unittest backend.CustomRAG.test.test_structured_stack -v
}
finally {
    Pop-Location
}
