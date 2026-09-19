param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Build command failed: $LASTEXITCODE" } }
npm ci
Check-Exit
npm run build
Check-Exit
cargo test --manifest-path src-tauri/Cargo.toml --no-default-features --locked
Check-Exit
if ($SkipInstaller) { npm run package -- --no-bundle } else { npm run package -- --bundles nsis }
Check-Exit
Write-Host 'Desktop: src-tauri/target/release/pipedl.exe'
Write-Host 'Installer: src-tauri/target/release/bundle/nsis/'
