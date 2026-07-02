# LocalTrace

LocalTrace is a local-only Windows activity trace. It records foreground app
focus, non-browser background audio, and browser tab activity into a local
SQLite database, then renders the current day in a built-in web UI.

The active product path is `localtrace/`. Older WorkTrace desktop-client
artifacts have been removed from the main development path.

## What It Does

- Captures Windows foreground app focus through `localtrace-winprobe.exe`.
- Captures non-browser background audio through the Windows probe.
- Captures Chrome and Edge tab focus/audio through a Manifest V3 extension.
- Stores raw events in `%LOCALAPPDATA%\LocalTrace\localtrace.db`.
- Serves a local web UI at `http://127.0.0.1:8765/`.
- Computes Today, Timeline, Top apps/sites, Now, Health, Settings, and Privacy
  views from raw events in the browser.
- Keeps all runtime traffic on loopback. There is no login, cloud sync, LAN
  server, token flow, planner, report generator, or review workflow in
  LocalTrace v1.

## Runtime Pieces

```text
localtrace.exe
  Owns config, SQLite, HTTP JSON routes, and the web UI.

localtrace-winprobe.exe
  Posts Windows app focus and non-browser audio events to loopback HTTP.

LocalTrace Extension
  Posts browser tab focus and browser audio events to loopback HTTP.

Web UI
  Static HTML/CSS/JS served by localtrace.exe.
```

The default bind address is:

```text
http://127.0.0.1:8765/
```

## Install

GitHub Releases for LocalTrace use `localtrace-v*` tags and publish:

```text
LocalTrace-windows.zip
```

After extracting the zip, run from the extracted `LocalTrace/` directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-localtrace.ps1
```

The default install directory is:

```text
%LOCALAPPDATA%\LocalTrace\App
```

The data directory is:

```text
%LOCALAPPDATA%\LocalTrace
```

Open the local UI after starting `localtrace.exe`:

```text
http://127.0.0.1:8765/
```

For packaging details, see
[localtrace/docs/PACKAGING.md](localtrace/docs/PACKAGING.md).

## Browser Extension

The active extension source is:

```text
localtrace/extension/
```

For development, load that directory as an unpacked extension in Chrome or Edge.
For release installs, extract `extension/localtrace-extension.zip` from the
LocalTrace release zip and load the extracted directory.

## Development

Common local checks:

```bash
node --check localtrace/web/app.js
node --test localtrace/extension/*.test.mjs
localtrace/.venv/bin/python -m pytest localtrace/tests -q
localtrace/.venv/bin/python -m ruff check localtrace
localtrace/.venv/bin/python -m ruff format --check localtrace
npm --prefix localtrace run lint:md
localtrace/.venv/bin/mkdocs build --strict -f localtrace/mkdocs.yml
```

Development entry points:

- [DEVELOPING.md](DEVELOPING.md): day-to-day development commands.
- [WINDOWS_DEV.md](WINDOWS_DEV.md): Windows/WSL development and local install
  notes.
- [RELEASING.md](RELEASING.md): release tag and GitHub Actions flow.
- [localtrace/docs/](localtrace/docs): LocalTrace specification, architecture,
  packaging, and workflow docs.

## Repository Layout

Active LocalTrace files:

- `localtrace/apps/localtrace/`: core local HTTP app.
- `localtrace/apps/winprobe/`: Windows probe.
- `localtrace/extension/`: browser extension.
- `localtrace/web/`: built-in web UI.
- `localtrace/packaging/`: Windows packaging and install scripts.
- `localtrace/skill/`: local trace helper scripts.
- `localtrace/docs/`: product and engineering docs.

Legacy WorkTrace client/runtime code has been removed from the active main
branch. Use Git history if old implementation details are needed for reference.
