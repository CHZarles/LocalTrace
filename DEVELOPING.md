# Developing LocalTrace

This repository's active product is LocalTrace. The repository root is the
project root.

## Setup

From the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

On Windows PowerShell, use the equivalent venv path:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
```

## Main Directories

- `apps/localtrace/`: local HTTP app, SQLite owner, config owner.
- `apps/winprobe/`: Windows foreground app and audio probe.
- `web/`: static web UI served by `localtrace.exe`.
- `extension/`: Chrome/Edge Manifest V3 extension.
- `packaging/`: Windows zip assembly and install scripts.
- `tests/`: Python tests for app, storage, config, packaging, and
  scripts.
- `docs/`: LocalTrace spec, architecture, workflow, and packaging docs.

## Local Checks

Run the checks relevant to your change:

```bash
node --check web/app.js
node --test extension/*.test.mjs
.venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
npm run lint:md
.venv/bin/mkdocs build --strict -f mkdocs.yml
```

Before committing, run the repo hooks when available:

```bash
PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files
```

## Run Locally

During development, run the core app from Python:

```bash
.venv/bin/python -m localtrace_core --bind 127.0.0.1:8765
```

Then open:

```text
http://127.0.0.1:8765/
```

On Windows, run the probe from a shell that can access the Windows desktop
session:

```powershell
.\.venv\Scripts\python.exe -m localtrace_winprobe
```

Load the browser extension from:

```text
extension/
```

After editing extension service-worker code, reload the unpacked extension in
Chrome or Edge.

## Packaging

Windows packaging is documented in
[docs/PACKAGING.md](docs/PACKAGING.md).

From Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\build-windows.ps1
```

The output zip is:

```text
dist\windows\LocalTrace-windows.zip
```

## Removed Prototype Code

Earlier prototype client/runtime code, client design docs, and installer
workflow have been removed from the active development path.

Use Git history if old implementation details are needed for reference.
