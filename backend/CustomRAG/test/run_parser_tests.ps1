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
    # Run only the parser-focused test module. This is handy when iterating on
    # parse.py or its builder helpers.
    & $pythonExe -m unittest backend.CustomRAG.test.test_parser_components -v
}
finally {
    Pop-Location
}
