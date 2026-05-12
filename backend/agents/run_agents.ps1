param(
  [ValidateSet("all", "server-safe", "runtime-deep", "frontend", "security", "api-contract", "feature-flow", "frontend-features", "server-connections", "server-runtime", "risk-register", "policy-gate", "threat-model", "data-leak", "tenant-isolation", "llm-safety", "audit-log", "deployment-gate")]
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
$backendRoot = Split-Path -Parent $agentsRoot
$repoRoot = Split-Path -Parent $backendRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  $pythonExe = "python"
}

$argsList = @(
  "-m", "backend.agents.Features.Runner_management.runner_run",
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

Push-Location $repoRoot
try {
  & $pythonExe @argsList
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
