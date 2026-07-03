from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

SKILL_NAME = "localtrace"
COMMAND_NAME = "localtrace-skill"
CHROME_EXTENSIONS_URL = "chrome://extensions/"
EDGE_EXTENSIONS_URL = "edge://extensions/"
EXTENSION_RUNTIME_FILES = (
    "manifest.json",
    "event_builder.mjs",
    "offscreen.html",
    "offscreen.js",
    "popup.html",
    "popup.js",
    "service_worker.js",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the LocalTrace skill and command wrapper."
    )
    parser.add_argument("--target", type=Path, default=default_skill_target())
    parser.add_argument("--bin-dir", type=Path, default=default_bin_dir())
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--browser-extension-dir", type=Path, default=None)
    parser.add_argument("--no-bin", action="store_true")
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
    except (OSError, subprocess.CalledProcessError) as exc:
        print_json({"ok": False, "error": str(exc)})
        return 1

    browser_extension = browser_extension_guidance(extension_result)
    print_json(
        {
            "ok": True,
            "skill_dir": str(args.target),
            "command": str(command_path) if command_path else None,
            "dependencies": dependencies,
            "browser_extension_unpacked_dir": browser_extension["unpacked_dir"],
            "chrome_extensions_url": browser_extension["chrome_url"],
            "edge_extensions_url": browser_extension["edge_url"],
            "must_tell_user_zh": browser_extension["agent_message_zh"],
            "browser_extension": browser_extension,
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


def browser_extension_guidance(extension_result: dict[str, Any]) -> dict[str, Any]:
    unpacked_dir = str(
        extension_result.get("unpacked_dir") or default_browser_extension_dir()
    )
    prepared = bool(extension_result.get("prepared"))
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
        "agent_message_zh": (
            f"必须告诉用户：{status}"
            f"插件解压路径：{unpacked_dir}；"
            f"Chrome 扩展页地址：{CHROME_EXTENSIONS_URL}；"
            f"Edge 扩展页地址：{EDGE_EXTENSIONS_URL}。"
            "打开对应浏览器的扩展管理页，开启开发者模式，选择加载已解压的扩展，然后选择上面的目录。"
        ),
    }


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
