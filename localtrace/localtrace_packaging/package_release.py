from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCALTRACE_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR_NAME = "LocalTrace"
RELEASE_ZIP_NAME = "LocalTrace-windows.zip"
EXTENSION_ZIP_NAME = "localtrace-extension.zip"
CORE_EXE = "localtrace.exe"
WINPROBE_EXE = "localtrace-winprobe.exe"

EXTENSION_RUNTIME_FILES = (
    "manifest.json",
    "event_builder.mjs",
    "offscreen.html",
    "offscreen.js",
    "popup.html",
    "popup.js",
    "service_worker.js",
)

WEB_RUNTIME_FILES = (
    "index.html",
    "app.js",
    "styles.css",
    "README.md",
)

SCRIPT_FILES = (
    "install-localtrace.ps1",
    "uninstall-localtrace.ps1",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build_release_zip(
            dist_dir=args.dist_dir,
            exe_dir=args.exe_dir,
            skip_exe_check=args.skip_exe_check,
        )
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"ok": True, "zip": str(result)}, sort_keys=True))
    return 0


def build_release_zip(
    *,
    dist_dir: Path,
    exe_dir: Path | None = None,
    skip_exe_check: bool = False,
) -> Path:
    dist_dir = dist_dir.resolve()
    exe_dir = (exe_dir or LOCALTRACE_ROOT / "dist" / "pyinstaller").resolve()
    release_dir = dist_dir / RELEASE_DIR_NAME
    release_zip = dist_dir / RELEASE_ZIP_NAME

    _reset_dir(release_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    _stage_executable(
        exe_dir / CORE_EXE,
        release_dir / CORE_EXE,
        skip_exe_check=skip_exe_check,
    )
    _stage_executable(
        exe_dir / WINPROBE_EXE,
        release_dir / WINPROBE_EXE,
        skip_exe_check=skip_exe_check,
    )
    _copy_named_files(LOCALTRACE_ROOT / "web", release_dir / "web", WEB_RUNTIME_FILES)
    _copy_named_files(
        LOCALTRACE_ROOT / "packaging" / "scripts",
        release_dir / "scripts",
        SCRIPT_FILES,
    )
    _write_extension_zip(release_dir / "extension" / EXTENSION_ZIP_NAME)
    _write_release_readme(release_dir / "README.md")
    _write_manifest(
        release_dir / "manifest.json",
        exe_build_skipped=skip_exe_check,
    )

    if release_zip.exists():
        release_zip.unlink()
    _write_zip_from_dir(release_dir, release_zip)
    return release_zip


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="localtrace-package-release")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=LOCALTRACE_ROOT / "dist" / "windows",
        help="Directory for the staged release folder and zip.",
    )
    parser.add_argument(
        "--exe-dir",
        type=Path,
        default=None,
        help="Directory containing localtrace.exe and localtrace-winprobe.exe.",
    )
    parser.add_argument(
        "--skip-exe-check",
        action="store_true",
        help="Create non-runnable placeholder exe files for non-Windows smoke tests.",
    )
    return parser.parse_args(argv)


def _stage_executable(
    source: Path,
    destination: Path,
    *,
    skip_exe_check: bool,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, destination)
        return
    if skip_exe_check:
        destination.write_text(
            "LocalTrace packaging smoke placeholder. "
            "Run packaging/build-windows.ps1 on Windows for a runnable executable.\n",
            encoding="utf-8",
        )
        return
    raise FileNotFoundError(f"Missing packaged executable: {source}")


def _copy_named_files(
    source_dir: Path, destination_dir: Path, names: tuple[str, ...]
) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = source_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"Missing release source file: {source}")
        shutil.copy2(source, destination_dir / name)


def _write_extension_zip(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    source_dir = LOCALTRACE_ROOT / "extension"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXTENSION_RUNTIME_FILES:
            source = source_dir / name
            if not source.is_file():
                raise FileNotFoundError(f"Missing extension runtime file: {source}")
            archive.write(source, name)


def _write_release_readme(destination: Path) -> None:
    destination.write_text(
        "\n".join(
            [
                "# LocalTrace Windows Release",
                "",
                "This folder contains the LocalTrace Windows release layout.",
                "",
                "## Contents",
                "",
                "- `localtrace.exe`: LocalTrace core process.",
                "- `localtrace-winprobe.exe`: Windows activity probe.",
                "- `web/`: Web Settings assets served by `localtrace.exe`.",
                "- `extension/localtrace-extension.zip`: browser extension package.",
                "- `scripts/install-localtrace.ps1`: current-user install script.",
                "- `scripts/uninstall-localtrace.ps1`: current-user uninstall script.",
                "",
                "Install from PowerShell:",
                "",
                "```powershell",
                "powershell -ExecutionPolicy Bypass -File "
                ".\\scripts\\install-localtrace.ps1",
                "```",
                "",
                "Uninstall from PowerShell:",
                "",
                "```powershell",
                "powershell -ExecutionPolicy Bypass -File "
                ".\\scripts\\uninstall-localtrace.ps1",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_manifest(destination: Path, *, exe_build_skipped: bool) -> None:
    payload: dict[str, Any] = {
        "name": "LocalTrace",
        "version": _project_version(),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "exe_build_skipped": exe_build_skipped,
        "artifacts": {
            "core_exe": CORE_EXE,
            "winprobe_exe": WINPROBE_EXE,
            "extension_zip": f"extension/{EXTENSION_ZIP_NAME}",
            "install_script": "scripts/install-localtrace.ps1",
            "uninstall_script": "scripts/uninstall-localtrace.ps1",
        },
        "runtime": {
            "api_host": "127.0.0.1",
            "autostart": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        },
    }
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_zip_from_dir(source_dir: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent).as_posix())


def _project_version() -> str:
    with (LOCALTRACE_ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    return str(project["project"]["version"])


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


if __name__ == "__main__":
    raise SystemExit(main())
