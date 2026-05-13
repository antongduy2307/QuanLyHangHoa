param(
    [string]$Tag = $env:GITHUB_REF_NAME,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        throw "Python not found."
    }
    $Python = $Command.Source
}

& (Join-Path $PSScriptRoot "check_version.ps1") -Tag $Tag

if (-not $SkipTests) {
    Push-Location $RepoRoot
    try {
        & $Python -m unittest discover -s tests -p "test*.py" -t .
        & $Python -m compileall core modules tests shell
    } finally {
        Pop-Location
    }
}

& (Join-Path $PSScriptRoot "build_exe.ps1")

$VersionText = Get-Content -Raw (Join-Path $RepoRoot "core\version.py")
$Match = [regex]::Match($VersionText, 'APP_VERSION\s*=\s*"([^"]+)"')
$Version = $Match.Groups[1].Value.Trim()
& (Join-Path $PSScriptRoot "build_installer.ps1") -Version $Version
