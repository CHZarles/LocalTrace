import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

LOCALTRACE_ROOT = Path(__file__).resolve().parents[1]


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


def test_pyproject_keeps_packaging_helpers_out_of_runtime_scripts() -> None:
    pyproject = tomllib.loads((LOCALTRACE_ROOT / "pyproject.toml").read_text())

    assert "localtrace" not in pyproject["project"]["scripts"]
    assert "localtrace-package-release" not in pyproject["project"]["scripts"]
    assert pyproject["project"]["scripts"]["localtrace-winprobe"] == (
        "localtrace_winprobe.__main__:main"
    )


def test_pyproject_declares_windows_uiautomation_dependency() -> None:
    pyproject = tomllib.loads((LOCALTRACE_ROOT / "pyproject.toml").read_text())

    assert (
        'uiautomation>=2.0,<3.0; platform_system == "Windows"'
        in pyproject["project"]["dependencies"]
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
    assert "LocalTrace/scripts/check-localtrace.ps1" in names
    assert "LocalTrace/scripts/uninstall-localtrace.ps1" in names
    assert "LocalTrace/extension/localtrace-extension.zip" in names
    assert "LocalTrace/README.md" in names


def test_packager_output_is_reproducible(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = run_packager("--dist-dir", str(first_dir), "--skip-exe-check")
    second = run_packager("--dist-dir", str(second_dir), "--skip-exe-check")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (first_dir / "LocalTrace-windows.zip").read_bytes() == (
        second_dir / "LocalTrace-windows.zip"
    ).read_bytes()

    with zipfile.ZipFile(first_dir / "LocalTrace-windows.zip") as archive:
        manifest = json.loads(archive.read("LocalTrace/manifest.json"))
    assert "built_at" not in manifest


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


def test_release_and_extension_versions_follow_pyproject(tmp_path: Path) -> None:
    pyproject = tomllib.loads((LOCALTRACE_ROOT / "pyproject.toml").read_text())
    project_version = pyproject["project"]["version"]
    dist_dir = tmp_path / "dist"
    result = run_packager("--dist-dir", str(dist_dir), "--skip-exe-check")

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(dist_dir / "LocalTrace-windows.zip") as release:
        release_manifest = json.loads(release.read("LocalTrace/manifest.json"))
        extension_bytes = release.read("LocalTrace/extension/localtrace-extension.zip")

    extension_zip = tmp_path / "extension.zip"
    extension_zip.write_bytes(extension_bytes)
    with zipfile.ZipFile(extension_zip) as archive:
        extension_manifest = json.loads(archive.read("manifest.json"))

    assert release_manifest["version"] == project_version
    assert extension_manifest["version"] == project_version


def test_install_script_uses_hkcu_run_and_user_local_appdata() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" in script
    assert "$env:LOCALAPPDATA" in script
    assert "LocalTrace" in script
    assert "localtrace.exe" in script
    assert "LocalTraceWinprobe" in script
    assert "localtrace-winprobe.exe" in script
    assert "Start-Process -Verb RunAs" not in script
    assert "HKLM:" not in script


def test_uninstall_script_removes_hkcu_run_and_localtrace_install_dir() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "uninstall-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" in script
    assert "Remove-ItemProperty" in script
    assert "LocalTraceWinprobe" in script
    assert "$env:LOCALAPPDATA" in script
    assert "Remove-Item" in script
    assert "Start-Process -Verb RunAs" not in script
    assert "HKLM:" not in script


def test_windows_build_script_invokes_pyinstaller_for_both_exes() -> None:
    script = (LOCALTRACE_ROOT / "packaging" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "PyInstaller" in script
    assert ".ProviderPath" in script
    assert "--name localtrace" in script
    assert "--name localtrace-winprobe" in script
    assert '"--add-data=${webDir}:web"' in script
    assert '"--add-data",' not in script
    assert "$webDir;web" not in script
    assert "localtrace_launcher.py" in script
    assert "localtrace_winprobe_launcher.py" in script
    assert "Start-Process -Verb RunAs" not in script


def test_windows_build_script_bundles_uiautomation_for_winprobe() -> None:
    script = (LOCALTRACE_ROOT / "packaging" / "build-windows.ps1").read_text(
        encoding="utf-8"
    )

    assert '"--hidden-import", "uiautomation"' in script


def test_windows_release_workflow_installs_uiautomation_dependency() -> None:
    workflow = (
        LOCALTRACE_ROOT / ".github" / "workflows" / "localtrace-release-windows.yml"
    ).read_text(encoding="utf-8")

    assert "uiautomation>=2.0,<3.0" in workflow


def test_core_launcher_propagates_main_exit_status() -> None:
    launcher = (
        LOCALTRACE_ROOT / "packaging" / "launchers" / "localtrace_launcher.py"
    ).read_text(encoding="utf-8")

    assert "raise SystemExit(main())" in launcher


def test_install_script_fails_fast_for_missing_required_artifacts() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$InstallDir = ""' in script
    assert 'throw "Release root missing required artifact:' in script
    assert "continue" not in script
    assert "Set-ItemProperty" in script


def test_install_script_prepares_browser_extension_for_manual_load() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "localtrace-extension.zip" in script
    assert "Expand-Archive" in script
    assert "Set-Clipboard" in script
    assert "chrome://extensions/" in script
    assert "edge://extensions/" in script
    assert "Load unpacked" in script
    assert "Load unpacked extension directory" in script


def test_check_script_diagnoses_winprobe_process_and_health_source() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "check-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "Get-Process -Name $Name" in script
    assert 'Test-ProcessRunning -Name "localtrace-winprobe"' in script
    assert "Invoke-RestMethod" in script
    assert "/health" in script
    assert "windows_probe" in script
    assert "probe_not_running" in script
    assert "probe_running_no_events" in script
    assert "last_observed_at" in script


def test_install_script_rejects_running_from_installed_copy() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    assert "[System.IO.Path]::GetFullPath" in script
    assert "ReleaseRoot and InstallDir must be different" in script
    assert "InstallDir must not be inside ReleaseRoot" in script
    assert ".StartsWith($releaseRootPrefix" in script


def test_install_script_computes_autostart_target_after_install_dir_default() -> None:
    script = (
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1"
    ).read_text(encoding="utf-8")

    default_index = script.index("if ([string]::IsNullOrWhiteSpace($InstallDir))")
    core_exe_index = script.index('$coreExe = Join-Path $InstallDir "localtrace.exe"')

    assert core_exe_index > default_index


def test_powershell_scripts_parse_when_powershell_is_available() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available in this environment")

    scripts = [
        LOCALTRACE_ROOT / "packaging" / "build-windows.ps1",
        LOCALTRACE_ROOT / "packaging" / "scripts" / "check-localtrace.ps1",
        LOCALTRACE_ROOT / "packaging" / "scripts" / "install-localtrace.ps1",
        LOCALTRACE_ROOT / "packaging" / "scripts" / "uninstall-localtrace.ps1",
    ]
    for script in scripts:
        command = (
            "$tokens = $null; $errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', "
            "[ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { "
            "Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_manifest_version_is_read_from_pyproject() -> None:
    source = (
        LOCALTRACE_ROOT / "localtrace_packaging" / "package_release.py"
    ).read_text(encoding="utf-8")

    assert '"version": "0.1.0"' not in source
    assert "tomllib" in source
    assert "_project_version()" in source


def test_packaging_docs_are_in_mkdocs_nav() -> None:
    mkdocs = (LOCALTRACE_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    docs = (LOCALTRACE_ROOT / "docs" / "PACKAGING.md").read_text(encoding="utf-8")

    assert "Packaging: PACKAGING.md" in mkdocs
    assert "HKCU" in docs
    assert "localtrace.exe" in docs
    assert "localtrace-winprobe.exe" in docs
    assert "LocalTraceWinprobe" in docs
    assert "LocalTrace-windows.zip" in docs
    assert "check-localtrace.ps1" in docs
    assert "The installer extracts the browser extension" in docs
    assert "Extract `extension/localtrace-extension.zip`" not in docs
    assert "Load unpacked" in docs
