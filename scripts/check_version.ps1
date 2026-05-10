param(
    [string]$Tag = $env:GITHUB_REF_NAME
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VersionFile = Join-Path $RepoRoot "core\version.py"

if (-not (Test-Path $VersionFile)) {
    throw "Version file not found: $VersionFile"
}

$VersionText = Get-Content -Raw $VersionFile
$Match = [regex]::Match($VersionText, 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $Match.Success) {
    throw "Could not read APP_VERSION from $VersionFile"
}

$AppVersion = $Match.Groups[1].Value.Trim()
if ([string]::IsNullOrWhiteSpace($Tag)) {
    throw "Release tag is required. Pass -Tag v$AppVersion or set GITHUB_REF_NAME."
}

if ($Tag -notmatch '^v(.+)$') {
    throw "Invalid release tag '$Tag'. Expected format: v$AppVersion"
}

$TagVersion = $Matches[1]
if ($TagVersion -ne $AppVersion) {
    throw "Version mismatch: APP_VERSION=$AppVersion but tag=$Tag. Expected tag v$AppVersion."
}

Write-Host "Version check passed: APP_VERSION=$AppVersion tag=$Tag"
