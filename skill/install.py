from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

SKILL_NAME = "localtrace"
COMMAND_NAME = "localtrace-skill"
CHROME_EXTENSIONS_URL = "chrome://extensions/"
EDGE_EXTENSIONS_URL = "edge://extensions/"
RUNTIME_ZIP_NAME = "LocalTrace-windows.zip"
DEFAULT_RUNTIME_ZIP_URL = (
    "https://github.com/CHZarles/LocalTrace/releases/latest/download/"
    f"{RUNTIME_ZIP_NAME}"
)
EXTENSION_RUNTIME_FILES = (
    "manifest.json",
    "event_builder.mjs",
    "offscreen.html",
    "offscreen.js",
    "popup.html",
    "popup.js",
    "service_worker.js",
)
RUNTIME_RELEASE_FILES = (
    "localtrace.exe",
    "localtrace-winprobe.exe",
    "manifest.json",
    "README.md",
)
RUNTIME_RELEASE_DIRS = ("web", "extension", "scripts")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the LocalTrace skill and command wrapper."
    )
    parser.add_argument("--target", type=Path, default=default_skill_target())
    parser.add_argument("--bin-dir", type=Path, default=default_bin_dir())
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--browser-extension-dir", type=Path, default=None)
    parser.add_argument("--runtime-app-dir", type=Path, default=None)
    parser.add_argument("--runtime-zip", type=Path, default=None)
    parser.add_argument(
        "--runtime-download-url",
        default=os.environ.get("LOCALTRACE_RUNTIME_ZIP_URL", DEFAULT_RUNTIME_ZIP_URL),
    )
    parser.add_argument("--no-bin", action="store_true")
    parser.add_argument("--no-runtime-install", action="store_true")
    parser.add_argument("--no-runtime-start", action="store_true")
    parser.add_argument("--skip-deps", action="store_true")
    args = parser.parse_args()

    source = Path(__file__).resolve().parent
    requirements = source / "requirements.txt"
    try:
        dependencies = requirements_from(requirements)
        if not args.skip_deps:
            install_dependencies(requirements, args.python)
        install_skill(source, args.target)
        command_path = None
        if not args.no_bin:
            command_path = install_command(args.bin_dir, args.target)
        runtime = (
            runtime_start_skipped("disabled")
            if args.no_runtime_start
            else ensure_installed_runtime(
                source,
                args.runtime_app_dir or default_runtime_app_path(),
                runtime_zip=args.runtime_zip,
                download_url=args.runtime_download_url,
                install_missing=not args.no_runtime_install,
            )
        )
        extension_dir = args.browser_extension_dir or default_browser_extension_path()
        extension_result = (
            prepare_browser_extension(source, extension_dir)
            if extension_dir is not None
            else {
                "prepared": False,
                "source_kind": "not_attempted",
                "source": None,
                "reason": (
                    "LOCALAPPDATA is not set and no browser extension directory "
                    "was provided."
                ),
            }
        )
        extension_result["clipboard"] = copy_browser_extension_path_to_clipboard(
            extension_result
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print_json({"ok": False, "error": str(exc)})
        return 1

    browser_extension = browser_extension_guidance(extension_result)
    must_tell_user_zh = browser_extension[
        "agent_message_zh"
    ] + runtime_agent_message_zh(runtime)
    print_json(
        {
            "ok": True,
            "skill_dir": str(args.target),
            "command": str(command_path) if command_path else None,
            "dependencies": dependencies,
            "browser_extension_unpacked_dir": browser_extension["unpacked_dir"],
            "chrome_extensions_url": browser_extension["chrome_url"],
            "edge_extensions_url": browser_extension["edge_url"],
            "must_tell_user_zh": must_tell_user_zh,
            "browser_extension": browser_extension,
            "runtime": runtime,
        }
    )
    return 0


def default_skill_target() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "skills" / SKILL_NAME
    return Path.home() / ".agents" / "skills" / SKILL_NAME


def default_bin_dir() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home()
        return base / "LocalTrace" / "bin"
    return Path.home() / ".local" / "bin"


def default_browser_extension_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = local_app_data.rstrip("\\/") if local_app_data else "%LOCALAPPDATA%"
    return base + r"\LocalTrace\App\extension\localtrace-extension"


def default_browser_extension_path() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return (
        Path(local_app_data)
        / "LocalTrace"
        / "App"
        / "extension"
        / "localtrace-extension"
    )


def default_runtime_app_path() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "LocalTrace" / "App"


def browser_extension_guidance(extension_result: dict[str, Any]) -> dict[str, Any]:
    unpacked_dir = str(
        extension_result.get("unpacked_dir") or default_browser_extension_dir()
    )
    prepared = bool(extension_result.get("prepared"))
    clipboard = extension_result.get("clipboard") or clipboard_skipped("not_attempted")
    status = (
        "浏览器插件加载目录已经准备好。"
        if prepared
        else (
            "浏览器插件加载目录尚未自动准备："
            f"{extension_result.get('reason', '未找到扩展包')}。"
        )
    )
    return {
        "unpacked_dir": unpacked_dir,
        "chrome_url": CHROME_EXTENSIONS_URL,
        "edge_url": EDGE_EXTENSIONS_URL,
        "prepared": prepared,
        "source_kind": str(extension_result.get("source_kind") or "unknown"),
        "source": extension_result.get("source"),
        "reason": extension_result.get("reason"),
        "clipboard": clipboard,
        "agent_message_zh": (
            f"必须告诉用户：{status}"
            f"插件解压路径：{unpacked_dir}；"
            f"Chrome 扩展页地址：{CHROME_EXTENSIONS_URL}；"
            f"Edge 扩展页地址：{EDGE_EXTENSIONS_URL}。"
            f"{'插件目录已复制到剪贴板。' if clipboard.get('copied') else ''}"
            "打开对应浏览器的扩展管理页，开启开发者模式，选择加载已解压的扩展，然后选择上面的目录。"
        ),
    }


def runtime_start_skipped(reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "ready_for_app_capture": False,
        "reason": reason,
        "app_dir": None,
        "core": None,
        "winprobe": None,
        "install": runtime_install_skipped(reason),
    }


def runtime_install_skipped(reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "installed": False,
        "reason": reason,
        "source_kind": None,
        "source": None,
    }


def ensure_installed_runtime(
    source: Path,
    app_dir: Path | None,
    *,
    platform: str = os.name,
    runtime_zip: Path | None = None,
    download_url: str = DEFAULT_RUNTIME_ZIP_URL,
    install_missing: bool = True,
    process_checker: Callable[[str], bool] | None = None,
    starter: Callable[[Path], Any] | None = None,
    autostart_registrar: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    runtime = start_installed_runtime(
        app_dir,
        platform=platform,
        process_checker=process_checker,
        starter=starter,
    )
    if runtime["ready_for_app_capture"]:
        runtime["install"] = runtime_install_skipped("already_ready")
    elif runtime.get("reason") == "missing_runtime":
        runtime["install"] = runtime_install_skipped("not_needed")
    if runtime["ready_for_app_capture"] or runtime.get("reason") != "missing_runtime":
        return runtime
    if not install_missing:
        runtime["install"] = runtime_install_skipped("disabled")
        return runtime

    install = install_runtime_package(
        source,
        app_dir,
        runtime_zip=runtime_zip,
        download_url=download_url,
        platform=platform,
        autostart_registrar=autostart_registrar,
    )
    if not install["installed"]:
        runtime["install"] = install
        runtime["reason"] = "runtime_install_failed"
        return runtime

    runtime = start_installed_runtime(
        app_dir,
        platform=platform,
        process_checker=process_checker,
        starter=starter,
    )
    runtime["install"] = install
    return runtime


def start_installed_runtime(
    app_dir: Path | None,
    *,
    platform: str = os.name,
    process_checker: Callable[[str], bool] | None = None,
    starter: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    if platform != "nt":
        return runtime_start_skipped("non_windows")
    if app_dir is None:
        return runtime_start_skipped("runtime_app_dir_unavailable")

    app_dir = app_dir.resolve()
    core = runtime_process_status("core", app_dir / "localtrace.exe")
    winprobe = runtime_process_status("winprobe", app_dir / "localtrace-winprobe.exe")
    result = {
        "attempted": True,
        "ready_for_app_capture": False,
        "reason": None,
        "app_dir": str(app_dir),
        "core": core,
        "winprobe": winprobe,
    }
    if not core["exists"] or not winprobe["exists"]:
        result["reason"] = "missing_runtime"
        return result

    process_checker = process_checker or is_windows_process_running
    starter = starter or start_windows_process
    for process in (core, winprobe):
        name = str(process["name"])
        if process_checker(name):
            process["status"] = "already_running"
            continue
        try:
            starter(Path(str(process["path"])))
        except OSError as exc:
            process["status"] = "error"
            process["error"] = str(exc)
        else:
            process["status"] = "started"

    ready_statuses = {"already_running", "started"}
    result["ready_for_app_capture"] = (
        core["status"] in ready_statuses and winprobe["status"] in ready_statuses
    )
    if not result["ready_for_app_capture"] and result["reason"] is None:
        result["reason"] = "start_failed"
    result["install"] = runtime_install_skipped("not_needed")
    return result


def install_runtime_package(
    source: Path,
    app_dir: Path | None,
    *,
    runtime_zip: Path | None = None,
    download_url: str = DEFAULT_RUNTIME_ZIP_URL,
    platform: str = os.name,
    downloader: Callable[[str, Path], Any] | None = None,
    autostart_registrar: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    if platform != "nt":
        return runtime_install_skipped("non_windows")
    if app_dir is None:
        return runtime_install_skipped("runtime_app_dir_unavailable")

    app_dir = app_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="localtrace-runtime-") as temp_name:
        temp_dir = Path(temp_name)
        try:
            zip_path, source_kind, source_value = runtime_zip_source(
                source,
                temp_dir,
                runtime_zip=runtime_zip,
                download_url=download_url,
                downloader=downloader,
            )
            extract_dir = temp_dir / "release"
            extract_zip_safely(zip_path, extract_dir)
            release_root = find_runtime_release_root(extract_dir)
            replace_directory(app_dir)
            copy_runtime_release(release_root, app_dir)
            registrar = autostart_registrar or register_runtime_autostart
            registrar(app_dir)
        except (OSError, zipfile.BadZipFile) as exc:
            return {
                "attempted": True,
                "installed": False,
                "reason": str(exc),
                "source_kind": None,
                "source": str(runtime_zip) if runtime_zip else download_url,
            }
    return {
        "attempted": True,
        "installed": True,
        "reason": None,
        "source_kind": source_kind,
        "source": source_value,
        "app_dir": str(app_dir),
    }


def runtime_zip_source(
    source: Path,
    temp_dir: Path,
    *,
    runtime_zip: Path | None,
    download_url: str,
    downloader: Callable[[str, Path], Any] | None,
) -> tuple[Path, str, str]:
    if runtime_zip is not None:
        return runtime_zip.resolve(), "runtime_zip", str(runtime_zip.resolve())

    local_zip = first_existing_path(
        [
            source.parent / "dist" / "windows" / RUNTIME_ZIP_NAME,
            source.parent / RUNTIME_ZIP_NAME,
        ]
    )
    if local_zip is not None:
        return local_zip.resolve(), "local_runtime_zip", str(local_zip.resolve())

    downloaded = temp_dir / RUNTIME_ZIP_NAME
    download_runtime_zip(download_url, downloaded, downloader=downloader)
    return downloaded, "downloaded_runtime_zip", download_url


def download_runtime_zip(
    url: str,
    destination: Path,
    *,
    downloader: Callable[[str, Path], Any] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if downloader is not None:
        downloader(url, destination)
        return
    with (
        urllib.request.urlopen(url, timeout=60) as response,
        destination.open("wb") as file,
    ):
        shutil.copyfileobj(response, file)


def extract_zip_safely(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise OSError(
                    f"Refusing to extract outside runtime directory: {member.filename}"
                )
            archive.extract(member, root)


def find_runtime_release_root(extract_dir: Path) -> Path:
    candidates = [extract_dir / "LocalTrace", extract_dir]
    candidates.extend(path.parent for path in extract_dir.rglob("localtrace.exe"))
    for candidate in candidates:
        if all((candidate / name).exists() for name in RUNTIME_RELEASE_FILES) and all(
            (candidate / name).is_dir() for name in RUNTIME_RELEASE_DIRS
        ):
            return candidate
    raise FileNotFoundError("runtime zip does not contain a LocalTrace release layout")


def copy_runtime_release(release_root: Path, app_dir: Path) -> None:
    for name in RUNTIME_RELEASE_FILES:
        shutil.copy2(release_root / name, app_dir / name)
    for name in RUNTIME_RELEASE_DIRS:
        shutil.copytree(release_root / name, app_dir / name)


def register_runtime_autostart(app_dir: Path) -> None:
    import winreg

    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key) as key:
        winreg.SetValueEx(
            key,
            "LocalTrace",
            0,
            winreg.REG_SZ,
            f'"{app_dir / "localtrace.exe"}"',
        )
        winreg.SetValueEx(
            key,
            "LocalTraceWinprobe",
            0,
            winreg.REG_SZ,
            f'"{app_dir / "localtrace-winprobe.exe"}"',
        )


def runtime_process_status(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "name": path.name,
        "path": str(path),
        "exists": path.is_file(),
        "status": "missing",
    }


def is_windows_process_running(
    process_name: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    completed = runner(
        ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
        check=False,
        capture_output=True,
        text=True,
    )
    return process_name.lower() in (completed.stdout or "").lower()


def start_windows_process(executable: Path) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    subprocess.Popen(  # noqa: S603
        [str(executable)],
        cwd=str(executable.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def runtime_agent_message_zh(runtime: dict[str, Any]) -> str:
    if runtime.get("ready_for_app_capture"):
        install = runtime.get("install", {})
        if install.get("installed"):
            return "LocalTrace Windows 运行时已自动安装，应用采集探针已经启动。"
        return "LocalTrace Windows 运行时和应用采集探针已经启动。"
    reason = runtime.get("reason")
    if reason == "non_windows":
        return (
            "当前不是 Windows 环境；Windows 应用采集需要在 Windows 上运行 "
            "localtrace.exe 和 localtrace-winprobe.exe。"
        )
    install = runtime.get("install", {})
    if install.get("attempted") and not install.get("installed"):
        return (
            "自动安装 LocalTrace Windows 运行时失败，暂时无法采集应用数据："
            f"{install.get('reason', '未知错误')}。"
        )
    if reason == "missing_runtime":
        app_dir = runtime.get("app_dir") or "%LOCALAPPDATA%\\LocalTrace\\App"
        return (
            "未找到 LocalTrace Windows 运行时，且本次未执行自动安装，"
            f"暂时无法采集应用数据。目标目录：{app_dir}。"
        )
    return "LocalTrace Windows 运行时未启动；暂时无法采集应用数据。"


def prepare_browser_extension(source: Path, unpacked_dir: Path) -> dict[str, Any]:
    source = source.resolve()
    unpacked_dir = unpacked_dir.resolve()
    extension_zip = first_existing_path(
        [
            unpacked_dir.parent / "localtrace-extension.zip",
            source.parent / "extension" / "localtrace-extension.zip",
        ]
    )
    if extension_zip is not None:
        replace_directory(unpacked_dir)
        extract_extension_zip(extension_zip, unpacked_dir)
        return prepared_extension_result(
            unpacked_dir,
            source_kind="extension_zip",
            source=extension_zip,
        )

    repo_extension_dir = source.parent / "extension"
    if (repo_extension_dir / "manifest.json").is_file():
        replace_directory(unpacked_dir)
        for name in EXTENSION_RUNTIME_FILES:
            runtime_file = repo_extension_dir / name
            if not runtime_file.is_file():
                raise FileNotFoundError(
                    f"Missing browser extension runtime file: {runtime_file}"
                )
            shutil.copy2(runtime_file, unpacked_dir / name)
        return prepared_extension_result(
            unpacked_dir,
            source_kind="repo_extension_dir",
            source=repo_extension_dir,
        )

    return {
        "prepared": False,
        "unpacked_dir": str(unpacked_dir),
        "source_kind": "missing",
        "source": None,
        "reason": (
            "could not find localtrace-extension.zip or repository extension "
            "runtime files"
        ),
    }


def first_existing_path(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def clipboard_skipped(reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "copied": False,
        "reason": reason,
    }


def copy_browser_extension_path_to_clipboard(
    extension_result: dict[str, Any],
    *,
    platform: str = os.name,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    if not extension_result.get("prepared"):
        return clipboard_skipped("extension_not_prepared")
    path = extension_result.get("unpacked_dir")
    if not path:
        return clipboard_skipped("extension_dir_unavailable")
    if platform != "nt":
        return clipboard_skipped("non_windows")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        runner(
            ["clip.exe"],
            input=str(path),
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "attempted": True,
            "copied": False,
            "reason": str(exc),
        }
    return {
        "attempted": True,
        "copied": True,
        "reason": None,
    }


def replace_directory(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)


def extract_extension_zip(extension_zip: Path, unpacked_dir: Path) -> None:
    root = unpacked_dir.resolve()
    with zipfile.ZipFile(extension_zip) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise OSError(
                    "Refusing to extract outside extension directory: "
                    f"{member.filename}"
                )
            archive.extract(member, root)


def prepared_extension_result(
    unpacked_dir: Path,
    *,
    source_kind: str,
    source: Path,
) -> dict[str, Any]:
    manifest = unpacked_dir / "manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"Prepared browser extension is missing manifest.json: {unpacked_dir}"
        )
    return {
        "prepared": True,
        "unpacked_dir": str(unpacked_dir),
        "source_kind": source_kind,
        "source": str(source),
        "reason": None,
    }


def install_skill(source: Path, target: Path) -> None:
    if target.exists():
        ensure_localtrace_target(target)
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )


def requirements_from(requirements: Path) -> list[str]:
    if not requirements.exists():
        return []
    return [
        line
        for line in (
            raw_line.strip()
            for raw_line in requirements.read_text(encoding="utf-8").splitlines()
        )
        if line and not line.startswith("#")
    ]


def install_dependencies(
    requirements: Path,
    python: Path,
    *,
    runner: Callable[[list[str]], Any] = subprocess.check_call,
) -> list[str]:
    dependencies = requirements_from(requirements)
    if not dependencies:
        return dependencies
    runner([str(python), "-m", "pip", "install", "-r", str(requirements)])
    return dependencies


def ensure_localtrace_target(target: Path) -> None:
    skill_file = target / "SKILL.md"
    if not skill_file.exists():
        raise OSError(f"refusing to replace non-skill directory: {target}")
    text = skill_file.read_text(encoding="utf-8")
    if "name: localtrace" not in text:
        raise OSError(f"refusing to replace non-LocalTrace skill: {target}")


def install_command(bin_dir: Path, skill_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        command_path = bin_dir / f"{COMMAND_NAME}.cmd"
        write_windows_command(command_path, skill_dir)
    else:
        command_path = bin_dir / COMMAND_NAME
        write_posix_command(command_path, skill_dir)
    return command_path


def write_posix_command(command_path: Path, skill_dir: Path) -> None:
    script = skill_dir / "scripts" / "localtrace.py"
    command_path.write_text(
        f'#!/usr/bin/env sh\nexec "{sys.executable}" "{script}" "$@"\n',
        encoding="utf-8",
    )
    mode = command_path.stat().st_mode
    command_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_windows_command(command_path: Path, skill_dir: Path) -> None:
    script = skill_dir / "scripts" / "localtrace.py"
    command_path.write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
        encoding="utf-8",
    )


def print_json(body: dict[str, Any]) -> None:
    print(json.dumps(body, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
