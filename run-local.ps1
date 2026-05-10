param(
  [switch]$BackendOnly,
  [switch]$FrontendOnly,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($BackendOnly -and $FrontendOnly) {
  throw "Use either -BackendOnly or -FrontendOnly, not both."
}

$repoRoot = Split-Path -Parent $PSCommandPath
$frontendRoot = Join-Path $repoRoot "frontend\Website\civil-ai-web"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$packageJsonPath = Join-Path $frontendRoot "package.json"

function Test-PortInUse {
  param(
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $listener.Start()
    return $false
  } catch {
    return $true
  } finally {
    if ($null -ne $listener) {
      $listener.Stop()
    }
  }
}

function Start-LocalWindow {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [Parameter(Mandatory = $true)]
    [int]$Port
  )

  if (Test-PortInUse -Port $Port) {
    Write-Warning "$Name did not start because port $Port is already in use."
    return $null
  }

  $launcher = @(
    "-NoExit"
    "-Command"
    "Set-Location '$WorkingDirectory'; Write-Host 'Starting $Name...' -ForegroundColor Cyan; $Command"
  )

  if ($DryRun) {
    Write-Host "[dry-run] powershell $($launcher -join ' ')" -ForegroundColor Yellow
    return $null
  }

  Start-Process -FilePath "powershell" -WorkingDirectory $WorkingDirectory -ArgumentList $launcher
}

if (-not (Test-Path $pythonPath)) {
  throw "Backend virtual environment was not found at $pythonPath"
}

if (-not (Test-Path $packageJsonPath)) {
  throw "Frontend package.json was not found at $packageJsonPath"
}

$shouldStartBackend = -not $FrontendOnly
$shouldStartFrontend = -not $BackendOnly

if ($shouldStartBackend) {
  $backendCommand = "& '$pythonPath' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"
  Start-LocalWindow -Name "CivilAI backend" -WorkingDirectory $repoRoot -Command $backendCommand -Port 8000 | Out-Null
}

if ($shouldStartFrontend) {
  $frontendCommand = "npm run dev"
  Start-LocalWindow -Name "CivilAI frontend" -WorkingDirectory $frontendRoot -Command $frontendCommand -Port 3000 | Out-Null
}

Write-Host ""
Write-Host "CivilAI local launch script finished." -ForegroundColor Green
Write-Host "Backend URL : http://127.0.0.1:8000/health"
Write-Host "Frontend URL: http://localhost:3000"
Write-Host ""
Write-Host "Options:"
Write-Host "  .\run-local.ps1"
Write-Host "  .\run-local.ps1 -BackendOnly"
Write-Host "  .\run-local.ps1 -FrontendOnly"
Write-Host "  .\run-local.ps1 -DryRun"
