# Packaging

Status: P6 MVP.

LocalTrace packaging creates a Windows release layout for manual local
installation. The release remains local-only: `localtrace.exe` binds to
`127.0.0.1`, the Windows probe posts to loopback HTTP JSON, and install scripts
use current-user autostart under HKCU.

## Release Contents

The release zip is named:

```text
LocalTrace-windows.zip
```

Inside the zip, `LocalTrace/` contains:

- `localtrace.exe`
- `localtrace-winprobe.exe`
- `web/`
- `extension/localtrace-extension.zip`
- `scripts/install-localtrace.ps1`
- `scripts/uninstall-localtrace.ps1`
- `manifest.json`
- `README.md`

Packaging excludes local development environments, caches, tests, local config,
SQLite databases, and secrets.

## Build On Windows

Executable packaging uses PyInstaller from the packaging environment. PyInstaller
is not a LocalTrace runtime dependency and is not added to project dependencies.

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1
```

This builds:

- `dist\pyinstaller\localtrace.exe`
- `dist\pyinstaller\localtrace-winprobe.exe`
- `dist\windows\LocalTrace-windows.zip`

For a zip assembly smoke test without building runnable executables:

```bash
python -m localtrace_packaging.package_release --skip-exe-check
```

The smoke mode creates placeholder `.exe` files and must not be shipped.

## GitHub Release

LocalTrace uses a dedicated Windows release workflow:

```text
.github/workflows/localtrace-release-windows.yml
```

LocalTrace release tags use this prefix:

```text
localtrace-v*
```

For example:

```bash
git tag localtrace-v0.1.0
git push origin localtrace-v0.1.0
```

On a `localtrace-v*` tag push, GitHub Actions runs the Windows packaging script
and attaches this file to the GitHub Release:

```text
LocalTrace-windows.zip
```

The workflow can also be started manually from GitHub Actions. Manual runs upload
`LocalTrace-windows.zip` as an Actions artifact without requiring a tag.

The release workflow runs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1 -Python python
```

The workflow verifies the generated zip contains the documented release layout
before uploading it.

## Install

Extract `LocalTrace-windows.zip`, open PowerShell in the extracted
`LocalTrace/` directory, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-localtrace.ps1
```

The default install directory is:

```text
%LOCALAPPDATA%\LocalTrace\App
```

The install script registers current-user autostart at:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

The value points to `localtrace.exe`. The script does not use HKLM and does not
request elevation.

## Uninstall

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-localtrace.ps1
```

The uninstall script removes the HKCU Run value and removes the staged app files
under `%LOCALAPPDATA%\LocalTrace\App`. It does not delete captured data such as
`%LOCALAPPDATA%\LocalTrace\localtrace.db`.

## Manual Smoke

After install:

1. Start `%LOCALAPPDATA%\LocalTrace\App\localtrace.exe`.
2. Open `http://127.0.0.1:8765/`.
3. Confirm the Web Settings health view loads.
4. Start `%LOCALAPPDATA%\LocalTrace\App\localtrace-winprobe.exe` on Windows.
5. Confirm `GET /health` reports LocalTrace and recent source diagnostics.
6. The installer extracts the browser extension and copies the unpacked
   extension directory to the clipboard.
7. In Chrome or Edge extension developer tooling, use Load unpacked and select
   the prepared extension directory.
8. Confirm the extension health check reports OK.

## Non-Goals

- No Windows Service.
- No admin-required installer.
- No signed installer.
- No auto-update system.
- No auth, token, login, LAN, or cloud behavior.
- No Native Messaging.
