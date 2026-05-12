param(
  [ValidateSet("all", "security", "api-contract", "feature-flow", "frontend-features", "server-connections", "server-runtime")]
  [string]$Agent = "all",
  [string]$BackendUrl = "http://127.0.0.1:8000",
  [string]$FrontendUrl = "http://localhost:3000",
  [string]$ReportDir = "",
  [switch]$SkipFrontendBuild,
  [switch]$SkipDependencyAudit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$agentsRoot = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent $agentsRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  $pythonExe = "python"
}

$argsList = @(
  "-m", "civilai_agents.runner",
  "--repo-root", $repoRoot,
  "--agent", $Agent,
  "--backend-url", $BackendUrl,
  "--frontend-url", $FrontendUrl
)

if ($ReportDir.Trim().Length -gt 0) {
  $argsList += @("--report-dir", $ReportDir)
}

if ($SkipFrontendBuild) {
  $argsList += "--skip-frontend-build"
}

if ($SkipDependencyAudit) {
  $argsList += "--skip-dependency-audit"
}

Push-Location $agentsRoot
try {
  & $pythonExe @argsList
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
