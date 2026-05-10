param(
    [switch]$SkipClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SpecPath = Join-Path $RepoRoot "desktop_app.spec"
$BuildDir = Join-Path $RepoRoot "build"
$DistAppDir = Join-Path $RepoRoot "dist\QuanLyHangHoa"
$VenvPyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $SpecPath)) {
    throw "PyInstaller spec not found: $SpecPath"
}

if (-not $SkipClean) {
    if (Test-Path $BuildDir) {
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }
    if (Test-Path $DistAppDir) {
        Remove-Item -LiteralPath $DistAppDir -Recurse -Force
    }
}

if (Test-Path $VenvPyInstaller) {
    $PyInstaller = $VenvPyInstaller
} else {
    $Command = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        throw "PyInstaller not found. Install dependencies first: python -m pip install -r requirements.txt"
    }
    $PyInstaller = $Command.Source
}

Push-Location $RepoRoot
try {
    & $PyInstaller --noconfirm $SpecPath
} finally {
    Pop-Location
}

$ExePath = Join-Path $DistAppDir "QuanLyHangHoa.exe"
if (-not (Test-Path $ExePath)) {
    throw "Expected executable was not created: $ExePath"
}

Write-Host "PyInstaller output: $DistAppDir"
Write-Host "Executable: $ExePath"
