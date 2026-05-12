Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendRoot = Join-Path $repoRoot "frontend\Website\civil-ai-web"

if (-not (Test-Path $pythonExe)) {
  $pythonExe = "python"
}

Push-Location $repoRoot
try {
  & $pythonExe -m isort backend agents scripts
  & $pythonExe -m black backend agents scripts
}
finally {
  Pop-Location
}

Push-Location $frontendRoot
try {
  npm run format
}
finally {
  Pop-Location
}
