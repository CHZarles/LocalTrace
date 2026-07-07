# Releasing LocalTrace

LocalTrace releases are Windows zip releases built from the repository root.

## Release Tags

Use `localtrace-v*` tags:

```bash
git tag localtrace-v0.1.0
git push origin localtrace-v0.1.0
```

Use only `localtrace-v*` tags for LocalTrace releases.

## GitHub Actions

The release workflow is:

```text
.github/workflows/localtrace-release-windows.yml
```

It runs on:

- tag pushes matching `localtrace-v*`
- manual `workflow_dispatch`

The workflow builds:

```text
dist/windows/LocalTrace-windows.zip
```

and verifies the zip contains:

- `LocalTrace/localtrace.exe`
- `LocalTrace/localtrace-winprobe.exe`
- `LocalTrace/web/index.html`
- `LocalTrace/web/app.js`
- `LocalTrace/web/styles.css`
- `LocalTrace/extension/localtrace-extension.zip`
- `LocalTrace/scripts/install-localtrace.ps1`
- `LocalTrace/scripts/uninstall-localtrace.ps1`
- `LocalTrace/manifest.json`
- `LocalTrace/README.md`

## Manual Build

From Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1
```

For a zip assembly smoke test without building real executables:

```bash
python -m localtrace_packaging.package_release --skip-exe-check
```

Smoke mode creates placeholder `.exe` files and must not be shipped.

## Install Smoke

1. Extract `LocalTrace-windows.zip`.
2. Run `scripts\install-localtrace.ps1` from the extracted `LocalTrace/`
   directory.
3. Open `http://127.0.0.1:8765/`.
4. Confirm Health shows recent service and Windows probe timestamps.
5. Load the prepared extension directory in Chrome or Edge.
6. Confirm the extension health check reports OK.
