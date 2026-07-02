# Developing LocalTrace

This repository's active product is LocalTrace. Work primarily under
`localtrace/`.

## Setup

From the repository root:

```bash
cd localtrace
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

On Windows PowerShell, use the equivalent venv path:

```powershell
cd localtrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
```

## Main Directories

- `localtrace/apps/localtrace/`: local HTTP app, SQLite owner, config owner.
- `localtrace/apps/winprobe/`: Windows foreground app and audio probe.
- `localtrace/web/`: static web UI served by `localtrace.exe`.
- `localtrace/extension/`: Chrome/Edge Manifest V3 extension.
- `localtrace/packaging/`: Windows zip assembly and install scripts.
- `localtrace/tests/`: Python tests for app, storage, config, packaging, and
  scripts.
- `localtrace/docs/`: LocalTrace spec, architecture, workflow, and packaging
  docs.

## Local Checks

Run the checks relevant to your change:

```bash
node --check localtrace/web/app.js
node --test localtrace/extension/*.test.mjs
localtrace/.venv/bin/python -m pytest localtrace/tests -q
localtrace/.venv/bin/python -m ruff check localtrace
localtrace/.venv/bin/python -m ruff format --check localtrace
npm --prefix localtrace run lint:md
localtrace/.venv/bin/mkdocs build --strict -f localtrace/mkdocs.yml
```

Before committing, run the repo hooks when available:

```bash
PATH="$PWD/localtrace/.venv/bin:$PATH" pre-commit run --all-files
```

## Run Locally

During development, run the core app from Python:

```bash
cd localtrace
.venv/bin/python -m localtrace_core --bind 127.0.0.1:8765
```

Then open:

```text
http://127.0.0.1:8765/
```

On Windows, run the probe from a shell that can access the Windows desktop
session:

```powershell
cd localtrace
.\.venv\Scripts\python.exe -m localtrace_winprobe
```

Load the browser extension from:

```text
localtrace/extension/
```

After editing extension service-worker code, reload the unpacked extension in
Chrome or Edge.

## Packaging

Windows packaging is documented in
[localtrace/docs/PACKAGING.md](localtrace/docs/PACKAGING.md).

From Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\localtrace\packaging\build-windows.ps1
```

The output zip is:

```text
localtrace\dist\windows\LocalTrace-windows.zip
```

## Legacy Code

The old WorkTrace Flutter client, WinUI prototype, root browser extension,
client design docs, and old Windows installer workflow have been removed from
the active development path.

The old Rust runtime under `core/` and `collectors/` remains temporarily as
legacy reference. Do not add new LocalTrace features there.
