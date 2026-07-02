# Windows LocalTrace Development

LocalTrace is developed mostly from WSL or Linux-friendly tools, but the Windows
probe and browser extension must be tested in a real Windows user session.

## Installed Local Paths

Default install location:

```text
%LOCALAPPDATA%\LocalTrace\App
```

Default data location:

```text
%LOCALAPPDATA%\LocalTrace
```

Default database:

```text
%LOCALAPPDATA%\LocalTrace\localtrace.db
```

Default web UI:

```text
http://127.0.0.1:8765/
```

## Build A Windows Zip

From Windows PowerShell at the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1
```

The release zip is written to:

```text
dist\windows\LocalTrace-windows.zip
```

## Install Locally

Extract `LocalTrace-windows.zip`, open PowerShell in the extracted
`LocalTrace/` directory, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-localtrace.ps1
```

Start:

```powershell
%LOCALAPPDATA%\LocalTrace\App\localtrace.exe
```

Then open:

```text
http://127.0.0.1:8765/
```

## Fast Web UI Sync During Development

If you are only changing static web files and already have LocalTrace installed,
copy the web files into the installed app directory:

```bash
cp -f web/index.html \
  web/app.js \
  web/styles.css \
  web/README.md \
  /mnt/c/Users/$USER/AppData/Local/LocalTrace/App/web/
```

If your Windows user name differs from `$USER`, use the explicit path:

```text
/mnt/c/Users/<WindowsUser>/AppData/Local/LocalTrace/App/web/
```

Then hard-refresh `http://127.0.0.1:8765/`.

## Browser Extension

Development extension source:

```text
extension/
```

Release extension zip inside the Windows package:

```text
LocalTrace/extension/localtrace-extension.zip
```

For development, load `extension/` as an unpacked extension in Chrome or Edge.
After editing extension files, reload the extension from the browser's
extension management page. Service-worker changes may require a reload or
browser restart before old workers are replaced.

## Probe Smoke Test

Run `localtrace.exe`, then from Windows PowerShell run the probe:

```powershell
%LOCALAPPDATA%\LocalTrace\App\localtrace-winprobe.exe
```

Verify health:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health
```

The web UI Health section should show a recent `Windows probe` timestamp after
you switch foreground apps.
