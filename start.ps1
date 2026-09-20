<#
    One-command start for the FC 27 price tool.

        .\start.ps1

    First run creates the virtualenv, installs dependencies, downloads the
    Chromium build Playwright needs, and copies .env.example to .env.
    Later runs skip straight to the server.

    Flags:
        -Recreate   throw the virtualenv away and build it again
        -NoBrowser  do not open the page in your browser
#>
[CmdletBinding()]
param(
    [switch]$Recreate,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$venv   = Join-Path $PSScriptRoot '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$stamp  = Join-Path $venv '.deps-installed'

function Write-Step([string]$text) {
    Write-Host ''
    Write-Host "==> $text" -ForegroundColor Cyan
}

# --- 1. Python ---------------------------------------------------------------
if ($Recreate -and (Test-Path $venv)) {
    Write-Step 'Removing the existing virtualenv'
    Remove-Item -Recurse -Force $venv
}

if (-not (Test-Path $python)) {
    Write-Step 'Creating the virtualenv'
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { & py -3 -m venv $venv } else { & python -m venv $venv }
    if (-not (Test-Path $python)) {
        throw "Virtualenv could not be created. Install Python 3.11+ from python.org and try again."
    }
}

$version = & $python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$version -lt [version]'3.11') {
    throw "Python 3.11+ required, found $version."
}

# --- 2. Dependencies ---------------------------------------------------------
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$needsInstall = $true
if (Test-Path $stamp) {
    $stampTime = (Get-Item $stamp).LastWriteTimeUtc
    $reqTime   = (Get-Item $requirements).LastWriteTimeUtc
    if ($stampTime -ge $reqTime) { $needsInstall = $false }
}

if ($needsInstall) {
    Write-Step 'Installing dependencies'
    & $python -m pip install --upgrade pip --quiet
    & $python -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }

    Write-Step 'Installing the Chromium build Playwright uses'
    & $python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'playwright install failed.' }

    New-Item -ItemType File -Path $stamp -Force | Out-Null
} else {
    Write-Host 'Dependencies already installed (delete .venv\.deps-installed to force).' -ForegroundColor DarkGray
}

# --- 3. Configuration --------------------------------------------------------
$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Step 'Creating .env from .env.example'
    Copy-Item (Join-Path $PSScriptRoot '.env.example') $envFile
    Write-Host ''
    Write-Host '  .env created. Open it and set ANTHROPIC_API_KEY before scanning cards,' -ForegroundColor Yellow
    Write-Host '  and point WATCH_DIR at the folder your screenshots land in.' -ForegroundColor Yellow
}

$hasKey = Select-String -Path $envFile -Pattern '^\s*ANTHROPIC_API_KEY\s*=\s*sk-' -Quiet
if (-not $hasKey) {
    Write-Host ''
    Write-Host '  ANTHROPIC_API_KEY is not set in .env -- card reading will be disabled' -ForegroundColor Yellow
    Write-Host '  until you add it. Everything else still runs.' -ForegroundColor Yellow
}

# --- 4. Run ------------------------------------------------------------------
$appHost = '127.0.0.1'
$port    = '8027'
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*HOST\s*=\s*(.+?)\s*$') { $appHost = $Matches[1] }
    if ($line -match '^\s*PORT\s*=\s*(\d+)\s*$') { $port = $Matches[1] }
}
$url = "http://$appHost`:$port"

Write-Step "Starting on $url"
if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($target)
        Start-Sleep -Seconds 3
        Start-Process $target
    } -ArgumentList $url | Out-Null
}

& $python -m uvicorn app.main:app --host $appHost --port $port
