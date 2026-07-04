# Release Process

PipeDL is intended to be installed on Windows from GitHub Releases.

## User Install Flow

1. Open the GitHub repository.
2. Select `Releases`.
3. Download `PipeDL-Setup-<version>.exe`.
4. Run the installer.
5. Start `PipeDL` from the Start Menu.

The installer provides:

- `PipeDL.exe`: desktop GUI, no terminal window
- `pipedl.exe`: CLI for users, scripts, and AI agents

The installer adds the install directory to the current user's `PATH`, so new terminals can run:

```powershell
pipedl status
pipedl run --name exp001 --shell powershell --cwd D:\project -- python train.py
```

The uninstaller removes the installed files, Start Menu shortcuts, the user PATH entry, and PipeDL runtime data under `%LOCALAPPDATA%\PipeDL`.

## Maintainer Release Flow

Push a version tag:

```bash
git tag v0.1.1
git push origin v0.1.1
```

GitHub Actions will build and upload:

- `PipeDL-Setup-<version>.exe`
- `PipeDL-portable-<version>.zip`

The desktop app uses the latest non-draft, non-prerelease GitHub Release for startup update checks. Keep the installer asset named `PipeDL-Setup-<version>.exe` so automatic updates can find it.

## Local Windows Build

Install Python 3.11 and Inno Setup, then run:

```powershell
.\scripts\build_windows.ps1 -Version 0.1.1
```

To build only the executable files without an installer:

```powershell
.\scripts\build_windows.ps1 -Version 0.1.1 -SkipInstaller
```
