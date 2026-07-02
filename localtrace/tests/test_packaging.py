import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALTRACE_ROOT = REPO_ROOT / "localtrace"


def run_packager(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "localtrace_packaging.package_release",
            *args,
        ],
        check=False,
        capture_output=True,
        cwd=LOCALTRACE_ROOT,
        text=True,
    )


def test_pyproject_exposes_core_and_winprobe_console_scripts() -> None:
    pyproject = tomllib.loads((LOCALTRACE_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["scripts"]["localtrace"] == (
        "localtrace_core.__main__:main"
    )
    assert pyproject["project"]["scripts"]["localtrace-winprobe"] == (
        "localtrace_winprobe.__main__:main"
    )


def test_packager_creates_release_zip_with_expected_layout(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    result = run_packager("--dist-dir", str(dist_dir), "--skip-exe-check")

    assert result.returncode == 0, result.stderr
    release_zip = dist_dir / "LocalTrace-windows.zip"
    assert release_zip.exists()

    with zipfile.ZipFile(release_zip) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("LocalTrace/manifest.json"))

    assert manifest["name"] == "LocalTrace"
    assert manifest["artifacts"]["core_exe"] == "localtrace.exe"
    assert manifest["artifacts"]["winprobe_exe"] == "localtrace-winprobe.exe"
    assert "LocalTrace/localtrace.exe" in names
    assert "LocalTrace/localtrace-winprobe.exe" in names
    assert "LocalTrace/web/index.html" in names
    assert "LocalTrace/scripts/install-localtrace.ps1" in names
    assert "LocalTrace/scripts/uninstall-localtrace.ps1" in names
    assert "LocalTrace/extension/localtrace-extension.zip" in names
    assert "LocalTrace/README.md" in names


@pytest.mark.parametrize(
    "forbidden_part",
    [
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "localtrace.db",
        "config.json",
        "tests/",
    ],
)
def test_packager_excludes_local_caches_data_and_tests(
    tmp_path: Path, forbidden_part: str
) -> None:
    dist_dir = tmp_path / "dist"
    result = run_packager("--dist-dir", str(dist_dir), "--skip-exe-check")

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(dist_dir / "LocalTrace-windows.zip") as archive:
        names = archive.namelist()

    assert not any(forbidden_part in name for name in names)


def test_extension_zip_contains_only_extension_runtime_files(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    result = run_packager("--dist-dir", str(dist_dir), "--skip-exe-check")

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(dist_dir / "LocalTrace-windows.zip") as release:
        extension_bytes = release.read("LocalTrace/extension/localtrace-extension.zip")

    extension_zip = tmp_path / "extension.zip"
    extension_zip.write_bytes(extension_bytes)
    with zipfile.ZipFile(extension_zip) as archive:
        names = set(archive.namelist())

    assert names == {
        "manifest.json",
        "event_builder.mjs",
        "offscreen.html",
        "offscreen.js",
        "popup.html",
        "popup.js",
        "service_worker.js",
    }


def test_install_script_uses_hkcu_run_and_user_local_appdata() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" in script
    assert "$env:LOCALAPPDATA" in script
    assert "LocalTrace" in script
    assert "localtrace.exe" in script
    assert "Start-Process -Verb RunAs" not in script
    assert "HKLM:" not in script


def test_uninstall_script_removes_hkcu_run_and_localtrace_install_dir() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "uninstall-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" in script
    assert "Remove-ItemProperty" in script
    assert "$env:LOCALAPPDATA" in script
    assert "Remove-Item" in script
    assert "Start-Process -Verb RunAs" not in script
    assert "HKLM:" not in script


def test_windows_build_script_invokes_pyinstaller_for_both_exes() -> None:
    script = (LOCALTRACE_ROOT / "packaging" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "PyInstaller" in script
    assert "--name localtrace" in script
    assert "--name localtrace-winprobe" in script
    assert "localtrace_launcher.py" in script
    assert "localtrace_winprobe_launcher.py" in script
    assert "Start-Process -Verb RunAs" not in script


def test_packaging_docs_are_in_mkdocs_nav() -> None:
    mkdocs = (LOCALTRACE_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    docs = (LOCALTRACE_ROOT / "docs" / "PACKAGING.md").read_text(encoding="utf-8")

    assert "Packaging: PACKAGING.md" in mkdocs
    assert "HKCU" in docs
    assert "localtrace.exe" in docs
    assert "localtrace-winprobe.exe" in docs
    assert "LocalTrace-windows.zip" in docs
