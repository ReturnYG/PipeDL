param(
    [string]$Version = "0.1.1",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install --upgrade pip
python -m pip install --upgrade build pyinstaller
python -m pip install -e .

if (Test-Path dist) {
    Remove-Item dist -Recurse -Force
}
if (Test-Path build) {
    Remove-Item build -Recurse -Force
}

pyinstaller packaging/pyinstaller/pipedl-cli.spec --noconfirm --clean
pyinstaller packaging/pyinstaller/PipeDL.spec --noconfirm --clean

$GuiExe = Join-Path $Root "dist\PipeDL\PipeDL.exe"
$CliExe = Join-Path $Root "dist\pipedl.exe"
if (-not (Test-Path $GuiExe)) {
    throw "Missing GUI executable: $GuiExe"
}
if (-not (Test-Path $CliExe)) {
    throw "Missing CLI executable: $CliExe"
}

if (-not $SkipInstaller) {
    $env:PIPEDL_VERSION = $Version
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        throw "Inno Setup compiler is not installed. Install it from https://jrsoftware.org/isinfo.php or run with -SkipInstaller."
    }
    iscc packaging/windows/PipeDL.iss
}

Write-Host "Build complete."
Write-Host "GUI app: dist/PipeDL/PipeDL.exe"
Write-Host "CLI app: dist/pipedl.exe"
if (-not $SkipInstaller) {
    Write-Host "Installer: dist/installer/PipeDL-Setup-$Version.exe"
}
