# Release

Keep versions in package.json, src-tauri/Cargo.toml and src-tauri/tauri.conf.json aligned. Refresh lockfiles and test before tagging v<version>.

The workflow builds the Windows Rust/Tauri executable and NSIS installer. Neither CLI nor Python runtime is distributed. WebView2 is bootstrapped by the Tauri installer. NSIS replaces Inno Setup: back up data before uninstalling the old app, whose old uninstaller deletes runtime data.

The new installer must preserve databases/logs on uninstall. Upgrade only with an idle queue and the app fully exited.

Settings opens GitHub Releases. Automatic installer execution is disabled until a signed update channel is configured. Signing secrets belong in CI, never in source. Do not invent keys or bypass signature verification.

Local Windows build: scripts/build_windows.ps1. Use -SkipInstaller for just the executable. CI uploads artifacts; a version tag publishes them. Local tests do not publish anything.
