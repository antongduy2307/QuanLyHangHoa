param(
    [string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VersionFile = Join-Path $RepoRoot "core\version.py"
$IssPath = Join-Path $RepoRoot "installer\QuanLyHangHoa.iss"
$DistAppDir = Join-Path $RepoRoot "dist\QuanLyHangHoa"
$OutputDir = Join-Path $RepoRoot "dist\installer"

if ([string]::IsNullOrWhiteSpace($Version)) {
    $VersionText = Get-Content -Raw $VersionFile
    $Match = [regex]::Match($VersionText, 'APP_VERSION\s*=\s*"([^"]+)"')
    if (-not $Match.Success) {
        throw "Could not read APP_VERSION from $VersionFile"
    }
    $Version = $Match.Groups[1].Value.Trim()
}

if (-not (Test-Path $IssPath)) {
    throw "Inno Setup script not found: $IssPath"
}
if (-not (Test-Path $DistAppDir)) {
    throw "PyInstaller output not found: $DistAppDir. Run scripts\build_exe.ps1 first."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$Candidates = @()
if (-not [string]::IsNullOrWhiteSpace($env:ISCC_PATH)) {
    $Candidates += $env:ISCC_PATH
}
$Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -ne $Command) {
    $Candidates += $Command.Source
}
$Command = Get-Command ISCC -ErrorAction SilentlyContinue
if ($null -ne $Command) {
    $Candidates += $Command.Source
}
$Candidates += @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)

$IsccPath = $Candidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path $_) } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($IsccPath)) {
    throw "Inno Setup compiler not found. Install Inno Setup 6, add ISCC.exe to PATH, or set ISCC_PATH."
}

Push-Location (Join-Path $RepoRoot "installer")
try {
    & $IsccPath "/DMyAppVersion=$Version" $IssPath
} finally {
    Pop-Location
}

$InstallerPath = Join-Path $OutputDir "QuanLyHangHoa-Setup-v$Version.exe"
if (-not (Test-Path $InstallerPath)) {
    throw "Expected installer was not created: $InstallerPath"
}

Write-Host "Installer output: $InstallerPath"
