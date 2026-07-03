import ast
import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlparse

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skill" / "scripts"
SKILL_DIR = Path(__file__).resolve().parents[1] / "skill"


class FakeLocalTraceServer:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.requests: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FakeLocalTraceServer":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(self.path)
                route = owner.routes.get(urlparse(self.path).path)
                if route is None:
                    self._write_json(404, {"ok": False, "error": "not found"})
                    return
                body = route["body"]
                if callable(body):
                    body = body(self.path)
                self._write_json(
                    route.get("status", 200), body, route.get("headers", {})
                )

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write_json(
                self,
                status: int,
                body: dict[str, Any],
                headers: dict[str, str] | None = None,
            ) -> None:
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        return Handler


def run_script(
    script_name: str, args: list[str], base_url: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if base_url is not None:
        env["LOCALTRACE_BASE_URL"] = base_url
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *args],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(result.stdout)


def parse_request(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(path)
    return parsed.path, parse_qs(parsed.query)


def sample_events() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "observed_at": "2026-07-01T09:00:00.000Z",
            "received_at": "2026-07-01T09:00:01.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": None,
            "payload": {"activity": "focus"},
        },
        {
            "id": 2,
            "observed_at": "2026-07-01T09:30:00.000Z",
            "received_at": "2026-07-01T09:30:01.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "title": None,
            "payload": {"activity": "focus"},
        },
        {
            "id": 3,
            "observed_at": "2026-07-01T10:00:00.000Z",
            "received_at": "2026-07-01T10:00:01.000Z",
            "source": "windows_probe",
            "kind": "app_active",
            "entity_type": "app",
            "entity": "Code.exe",
            "title": None,
            "payload": {"activity": "focus"},
        },
    ]


def event_at(
    event_id: int, observed_at: str, entity: str = "Code.exe"
) -> dict[str, Any]:
    return {
        "id": event_id,
        "observed_at": observed_at,
        "received_at": observed_at,
        "source": "windows_probe",
        "kind": "app_active",
        "entity_type": "app",
        "entity": entity,
        "title": None,
        "payload": {"activity": "focus"},
    }


def many_events(count: int, entity: str = "busy-app.exe") -> list[dict[str, Any]]:
    return [
        event_at(
            index + 1,
            f"2026-07-01T{index // 3600:02d}:{(index // 60) % 60:02d}:"
            f"{index % 60:02d}.000Z",
            entity,
        )
        for index in range(count)
    ]


def events_route(events: list[dict[str, Any]]):
    def route(path: str) -> dict[str, Any]:
        _request_path, query = parse_request(path)
        selected = events
        if "from" in query:
            selected = [
                event for event in selected if event["observed_at"] >= query["from"][0]
            ]
        if "to" in query:
            selected = [
                event for event in selected if event["observed_at"] < query["to"][0]
            ]
        selected = sorted(
            selected,
            key=lambda event: (event["observed_at"], event["id"]),
        )
        if "limit" in query:
            selected = selected[: int(query["limit"][0])]
        return {"ok": True, "events": selected}

    return route


def test_health_script_returns_core_health_json() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 0
    assert output_json(result) == {"ok": True, "service": "localtrace"}
    assert server.requests == ["/health"]


def test_unified_entrypoint_invokes_health_subcommand() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script("localtrace.py", ["health"], server.base_url)

    assert result.returncode == 0
    assert output_json(result) == {"ok": True, "service": "localtrace"}
    assert server.requests == ["/health"]


def test_dashboard_script_opens_web_dashboard(monkeypatch, capsys) -> None:
    opened: list[tuple[str, int]] = []
    module = load_script_module("localtrace_dashboard.py")
    monkeypatch.setattr(
        module.webbrowser,
        "open",
        lambda url, new=0: opened.append((url, new)) or True,
    )

    with FakeLocalTraceServer(
        {
            "/health": {
                "body": {
                    "ok": True,
                    "service": "localtrace",
                    "tracking": {"paused": False},
                }
            }
        }
    ) as server:
        result = module.main(["--base-url", server.base_url])

    assert result == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["opened"] is True
    assert body["dashboard_url"] == f"{server.base_url}/"
    assert body["health"]["service"] == "localtrace"
    assert opened == [(f"{server.base_url}/", 2)]
    assert server.requests == ["/health"]


def test_unified_entrypoint_invokes_dashboard_subcommand_without_opening() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script(
            "localtrace.py", ["dashboard", "--no-open"], server.base_url
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["opened"] is False
    assert body["dashboard_url"] == f"{server.base_url}/"
    assert server.requests == ["/health"]


def test_focus_switches_reports_facts_without_scoring() -> None:
    events = [
        {
            **event_at(1, "2026-07-01T09:00:00.000Z", "Code.exe"),
            "title": "LocalTrace",
        },
        {
            "id": 2,
            "observed_at": "2026-07-01T09:02:00.000Z",
            "received_at": "2026-07-01T09:02:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "title": "Review PR",
            "payload": {"activity": "focus"},
        },
        {
            "id": 3,
            "observed_at": "2026-07-01T09:04:00.000Z",
            "received_at": "2026-07-01T09:04:00.000Z",
            "source": "browser_extension",
            "kind": "tab_active",
            "entity_type": "domain",
            "entity": "github.com",
            "title": "Review PR",
            "payload": {"activity": "focus"},
        },
        {
            "id": 4,
            "observed_at": "2026-07-01T09:05:00.000Z",
            "received_at": "2026-07-01T09:05:00.000Z",
            "source": "windows_probe",
            "kind": "app_audio",
            "entity_type": "app",
            "entity": "Spotify.exe",
            "title": None,
            "payload": {"activity": "audio"},
        },
        {
            **event_at(5, "2026-07-01T09:20:00.000Z", "Code.exe"),
            "title": "Terminal",
        },
    ]
    with FakeLocalTraceServer(
        {
            "/settings": {
                "body": {
                    "ok": True,
                    "settings": {"capture": {"idle_cutoff_seconds": 300}},
                }
            },
            "/events": {"body": events_route(events)},
        }
    ) as server:
        result = run_script(
            "localtrace_focus_switches.py",
            ["--to", "2026-07-04T00:00:00.000Z"],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["from"] == "2026-07-01T00:00:00.000Z"
    assert body["to"] == "2026-07-04T00:00:00.000Z"
    assert body["idle_cutoff_seconds"] == 300
    assert body["focus_event_count"] == 4
    assert body["focus_target_count"] == 3
    assert body["switch_count"] == 2
    assert body["unknown_or_idle_seconds"] == 660
    assert body["long_gap_count"] == 1
    assert body["target_durations"] == [
        {
            "entity_type": "domain",
            "entity": "github.com",
            "title": "Review PR",
            "event_count": 2,
            "duration_seconds": 420,
        },
        {
            "entity_type": "app",
            "entity": "Code.exe",
            "title": "LocalTrace",
            "event_count": 1,
            "duration_seconds": 120,
        },
        {
            "entity_type": "app",
            "entity": "Code.exe",
            "title": "Terminal",
            "event_count": 1,
            "duration_seconds": 0,
        },
    ]
    assert body["switches"] == [
        {
            "at": "2026-07-01T09:02:00.000Z",
            "from": {
                "entity_type": "app",
                "entity": "Code.exe",
                "title": "LocalTrace",
            },
            "to": {
                "entity_type": "domain",
                "entity": "github.com",
                "title": "Review PR",
            },
            "gap_seconds": 120,
        },
        {
            "at": "2026-07-01T09:20:00.000Z",
            "from": {
                "entity_type": "domain",
                "entity": "github.com",
                "title": "Review PR",
            },
            "to": {
                "entity_type": "app",
                "entity": "Code.exe",
                "title": "Terminal",
            },
            "gap_seconds": 960,
        },
    ]
    assert "prompt_context" in body
    assert "attention_score" not in body
    assert [parse_request(request)[0] for request in server.requests] == [
        "/settings",
        "/events",
    ]


def test_unified_entrypoint_invokes_focus_switches_subcommand() -> None:
    with FakeLocalTraceServer(
        {
            "/settings": {"body": {"ok": True, "settings": {"capture": {}}}},
            "/events": {"body": events_route([])},
        }
    ) as server:
        result = run_script(
            "localtrace.py",
            ["focus-switches", "--to", "2026-07-04T00:00:00.000Z"],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["focus_event_count"] == 0
    assert body["switch_count"] == 0


def test_skill_installer_copies_skill_and_creates_invocation_command(
    tmp_path: Path,
) -> None:
    target = tmp_path / "skills" / "localtrace"
    bin_dir = tmp_path / "bin"

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "install.py"),
            "--target",
            str(target),
            "--bin-dir",
            str(bin_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "必须告诉用户" in result.stdout
    body = json.loads(result.stdout)
    assert body["ok"] is True
    assert body["skill_dir"] == str(target)
    assert body["browser_extension_unpacked_dir"].endswith(
        r"LocalTrace\App\extension\localtrace-extension"
    )
    assert body["chrome_extensions_url"] == "chrome://extensions/"
    assert body["edge_extensions_url"] == "edge://extensions/"
    assert "必须告诉用户" in body["must_tell_user_zh"]
    assert "插件解压路径" in body["must_tell_user_zh"]
    assert "Chrome 扩展页地址" in body["must_tell_user_zh"]
    assert "Edge 扩展页地址" in body["must_tell_user_zh"]
    assert body["browser_extension"]["unpacked_dir"].endswith(
        r"LocalTrace\App\extension\localtrace-extension"
    )
    assert body["browser_extension"]["chrome_url"] == "chrome://extensions/"
    assert body["browser_extension"]["edge_url"] == "edge://extensions/"
    assert "插件解压路径" in body["browser_extension"]["agent_message_zh"]
    assert "Chrome" in body["browser_extension"]["agent_message_zh"]
    assert "Edge" in body["browser_extension"]["agent_message_zh"]
    assert (target / "SKILL.md").exists()
    assert (target / "README.md").exists()
    assert (target / "scripts" / "localtrace.py").exists()
    assert not (target / "scripts" / "__pycache__").exists()

    command_name = "localtrace-skill.cmd" if os.name == "nt" else "localtrace-skill"
    command = bin_dir / command_name
    assert command.exists()
    if os.name != "nt":
        assert os.access(command, os.X_OK)

    help_result = subprocess.run(
        [str(command), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "health" in help_result.stdout
    assert "recent-events" in help_result.stdout
    assert "dashboard" in help_result.stdout
    assert "focus-switches" in help_result.stdout


def test_powershell_installer_is_available_for_windows_users() -> None:
    installer = SKILL_DIR / "install.ps1"

    assert installer.exists()
    text = installer.read_text(encoding="utf-8")
    assert "install.py" in text
    assert "LOCALTRACE_SKILL_ARCHIVE" in text
    assert "Windows_NT" in text
    assert "$args" in text
    assert "ConvertFrom-Json" in text
    assert "must_tell_user_zh" in text
    assert "请转告用户" in text
    assert "Write-Host" in text


def test_installer_parses_runtime_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "\n# comment\nrequests==2.32.0\n\ncharset-normalizer>=3\n",
        encoding="utf-8",
    )

    installer = load_install_module()

    assert installer.requirements_from(requirements) == [
        "requests==2.32.0",
        "charset-normalizer>=3",
    ]


def test_installer_runs_pip_for_declared_runtime_requirements(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests==2.32.0\n", encoding="utf-8")
    calls: list[list[str]] = []

    installer = load_install_module()
    installer.install_dependencies(
        requirements,
        Path("/usr/bin/python3"),
        runner=lambda command: calls.append(command),
    )

    assert calls == [
        [
            "/usr/bin/python3",
            "-m",
            "pip",
            "install",
            "-r",
            str(requirements),
        ]
    ]


def test_skill_docs_show_windows_agent_install_and_invocation() -> None:
    skill_readme = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
    skill_file = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    project_readme = (SKILL_DIR.parent / "README.md").read_text(encoding="utf-8")

    assert "PowerShell" in skill_readme
    assert ".\\skill\\install.ps1" in skill_readme
    assert "%USERPROFILE%\\.agents\\skills\\localtrace" in skill_readme
    assert "%LOCALAPPDATA%\\LocalTrace\\bin\\localtrace-skill.cmd" in skill_readme
    assert "localtrace.exe" in skill_readme
    assert "localtrace-winprobe.exe" in skill_readme
    assert "dashboard" in skill_readme
    assert "focus-switches" in skill_readme
    assert "prompt_context" in skill_readme
    assert "Do not ask the user to run commands manually" in skill_file
    assert "opens the Web UI" in skill_file
    assert "focus-switches" in skill_file
    assert "prompt_context" in skill_file
    assert "https://github.com/CHZarles/LocalTrace" in project_readme
    assert "请从 GitHub 仓库" in project_readme
    assert "不要让我手动运行命令" in project_readme
    assert "安装入口只有一个" in project_readme
    assert "安装完成后，agent 必须马上输出浏览器插件加载信息" in project_readme
    assert "马上输出浏览器插件解压路径" in project_readme
    assert "插件解压路径" in project_readme
    assert "Chrome 扩展页地址" in project_readme
    assert "Edge 扩展页地址" in project_readme
    assert "安装器会自动解压浏览器插件" in project_readme
    assert "把插件目录复制到剪贴板" in project_readme
    assert "extension/localtrace-extension.zip" not in project_readme
    assert "PowerShell" not in project_readme
    assert ".\\skill\\install.ps1" not in project_readme
    assert "localtrace.exe" not in project_readme
    assert "localtrace-winprobe.exe" not in project_readme
    assert "```" not in project_readme
    assert "sh skill/install.sh" not in skill_readme
    assert "sh skill/install.sh" not in project_readme
    assert "WSL, Linux, and macOS" not in skill_readme
    assert "WSL, Linux, and macOS" not in project_readme


def test_skill_markdown_is_concise_and_agent_oriented() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    description = frontmatter_field(text, "description")

    assert len(lines) <= 100
    assert description is not None
    assert not description.startswith("Use when")
    assert ". Use when " in description
    assert "loopback HTTP" in description
    assert "captured activity" in description

    for heading in [
        "## Quick start",
        "## Workflows",
        "## Command reference",
        "## Guardrails",
    ]:
        assert heading in text

    assert "localtrace.exe" in text
    assert "localtrace-winprobe.exe" in text
    assert "Do not ask the user to run commands manually" in text
    assert "After installation, immediately relay" in text
    assert "must_tell_user_zh" in text
    assert "browser_extension.unpacked_dir" in text
    assert "browser_extension.chrome_url" in text
    assert "browser_extension.edge_url" in text
    assert "browser_extension.agent_message_zh" in text
    assert "Do not read SQLite" in text
    assert "Do not import LocalTrace runtime modules" in text
    assert "dashboard" in text
    assert "focus-switches" in text
    assert "prompt_context" in text


def frontmatter_field(text: str, key: str) -> str | None:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        prefix = f"{key}: "
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def load_install_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "localtrace_skill_install", SKILL_DIR / "install.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_script_module(script_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"localtrace_skill_{script_name.removesuffix('.py')}",
        SCRIPTS_DIR / script_name,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_recent_events_script_scans_backward_from_requested_end() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "5",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["events"] == sample_events()[-2:]
    assert body["recent_limit"] == 2
    assert body["scan_limit"] == 5
    assert body["search_from"] == "2026-07-01T00:00:00.000Z"
    assert body["search_to"] == "2026-07-02T00:00:00.000Z"
    assert body["windows_scanned"] == 1
    assert body["truncated"] is False
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T00:00:00.000Z"]
    assert query["to"] == ["2026-07-02T00:00:00.000Z"]
    assert query["limit"] == ["6"]


def test_recent_events_refuses_partial_window_when_scan_limit_is_exceeded() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "2",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    assert output_json(result) == {
        "ok": False,
        "partial": True,
        "error": "recent events window exceeds scan limit; increase --scan-limit",
        "truncated": True,
        "scan_limit": 2,
        "window_from": "2026-07-01T00:00:00.000Z",
        "window_to": "2026-07-02T00:00:00.000Z",
    }
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_recent_events_accumulates_across_backward_windows() -> None:
    events = [
        event_at(1, "2026-06-30T23:00:00.000Z", "older.exe"),
        event_at(2, "2026-07-01T23:00:00.000Z", "newer.exe"),
    ]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "5",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "3",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert [event["id"] for event in body["events"]] == [1, 2]
    assert body["windows_scanned"] == 2
    assert body["lookback_exhausted"] is False
    assert len(server.requests) == 2


def test_recent_events_reports_lookback_exhausted() -> None:
    events = [event_at(1, "2026-07-01T23:00:00.000Z")]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "2",
                "--scan-limit",
                "5",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "1",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert [event["id"] for event in body["events"]] == [1]
    assert body["windows_scanned"] == 1
    assert body["lookback_exhausted"] is True


def test_recent_events_accepts_scan_limit_at_core_cap() -> None:
    with FakeLocalTraceServer({"/events": {"body": events_route([])}}) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "1",
                "--scan-limit",
                "5000",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "1",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["scan_limit"] == 5000
    assert body["events"] == []
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["5000"]


def test_recent_events_accepts_exact_core_cap_response() -> None:
    capped_events = many_events(5000)
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(capped_events)}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "1",
                "--scan-limit",
                "5000",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["scan_limit"] == 5000
    assert [event["id"] for event in body["events"]] == [5000]


def test_recent_events_marks_partial_for_more_than_core_cap() -> None:
    capped_events = many_events(5001)
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(capped_events)}}
    ) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "1",
                "--scan-limit",
                "5000",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert (
        body["error"]
        == "recent events window exceeds scan limit; increase --scan-limit"
    )
    assert body["scan_limit"] == 5000


def test_events_between_script_validates_range_and_filters() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": [sample_events()[0]]}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01T09:00:00.000Z",
                "--to",
                "2026-07-01T10:00:00.000Z",
                "--source",
                "windows_probe",
                "--kind",
                "app_active",
                "--limit",
                "10",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    assert output_json(result)["events"] == [sample_events()[0]]
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T09:00:00.000Z"]
    assert query["to"] == ["2026-07-01T10:00:00.000Z"]
    assert query["source"] == ["windows_probe"]
    assert query["kind"] == ["app_active"]
    assert query["limit"] == ["10"]


def test_events_between_script_rejects_invalid_timestamp_without_http_call() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": []}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01 09:00",
                "--to",
                "2026-07-01T10:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "--from must be RFC3339 UTC",
    }
    assert server.requests == []


def test_recent_events_script_returns_json_for_invalid_limit() -> None:
    result = run_script("localtrace_recent_events.py", ["--limit", "0"])

    assert result.returncode == 2
    assert output_json(result) == {"ok": False, "error": "--limit must be at least 1"}


def test_day_summary_script_derives_counts_and_observed_spans() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": sample_events()}}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py", ["--date", "2026-07-01"], server.base_url
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["date"] == "2026-07-01"
    assert body["event_count"] == 3
    assert body["observed_start"] == "2026-07-01T09:00:00.000Z"
    assert body["observed_end"] == "2026-07-01T10:00:00.000Z"
    assert body["by_source"] == {
        "browser_extension": {
            "count": 1,
            "first_observed_at": "2026-07-01T09:30:00.000Z",
            "last_observed_at": "2026-07-01T09:30:00.000Z",
        },
        "windows_probe": {
            "count": 2,
            "first_observed_at": "2026-07-01T09:00:00.000Z",
            "last_observed_at": "2026-07-01T10:00:00.000Z",
        },
    }
    assert body["by_kind"] == {
        "app_active": {
            "count": 2,
            "first_observed_at": "2026-07-01T09:00:00.000Z",
            "last_observed_at": "2026-07-01T10:00:00.000Z",
        },
        "tab_active": {
            "count": 1,
            "first_observed_at": "2026-07-01T09:30:00.000Z",
            "last_observed_at": "2026-07-01T09:30:00.000Z",
        },
    }
    assert body["by_entity"][0] == {
        "entity_type": "app",
        "entity": "Code.exe",
        "count": 2,
        "first_observed_at": "2026-07-01T09:00:00.000Z",
        "last_observed_at": "2026-07-01T10:00:00.000Z",
    }
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["from"] == ["2026-07-01T00:00:00.000Z"]
    assert query["to"] == ["2026-07-02T00:00:00.000Z"]


def test_explain_gap_script_reports_before_inside_and_after_context() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(sample_events())}}
    ) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:20:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["gap_detected"] is True
    assert body["inside_event_count"] == 0
    assert body["before"]["id"] == 1
    assert body["after"]["id"] == 2
    assert body["gap_seconds"] == 600
    assert body["previous_event_delta_seconds"] == 600
    assert body["next_event_delta_seconds"] == 600
    assert body["explanation"] == (
        "No stored events were observed in this 600-second window; "
        "nearest context events are 600 seconds before and 600 seconds after."
    )
    assert len(server.requests) == 3
    before_path, before_query = parse_request(server.requests[1])
    assert before_path == "/events"
    assert before_query["from"] == ["2026-06-30T09:10:00.000Z"]
    assert before_query["to"] == ["2026-07-01T09:10:00.000Z"]
    assert before_query["limit"] == ["1001"]
    after_path, after_query = parse_request(server.requests[2])
    assert after_path == "/events"
    assert after_query["from"] == ["2026-07-01T09:20:00.000Z"]
    assert after_query["to"] == ["2026-07-02T09:20:00.000Z"]
    assert after_query["limit"] == ["1"]


def test_explain_gap_preserves_millisecond_precision() -> None:
    events = [
        event_at(1, "2026-07-01T09:09:59.750Z", "before.exe"),
        event_at(2, "2026-07-01T09:10:00.500Z", "after.exe"),
    ]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:10:00.250Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["gap_seconds"] == 0.25
    assert body["previous_event_delta_seconds"] == 0.25
    assert body["next_event_delta_seconds"] == 0.25
    assert body["explanation"] == (
        "No stored events were observed in this 0.25-second window; "
        "nearest context events are 0.25 seconds before and 0.25 seconds after."
    )


def test_explain_gap_searches_context_across_day_boundary() -> None:
    events = [
        event_at(1, "2026-07-01T23:59:00.000Z", "before.exe"),
        event_at(2, "2026-07-02T00:02:00.000Z", "after.exe"),
    ]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-02T00:00:00.000Z",
                "--to",
                "2026-07-02T00:01:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["before"]["id"] == 1
    assert body["after"]["id"] == 2
    assert body["previous_event_delta_seconds"] == 60
    assert body["next_event_delta_seconds"] == 60
    before_path, before_query = parse_request(server.requests[1])
    assert before_path == "/events"
    assert before_query["from"] == ["2026-07-01T00:00:00.000Z"]
    after_path, after_query = parse_request(server.requests[2])
    assert after_path == "/events"
    assert after_query["to"] == ["2026-07-03T00:01:00.000Z"]


def test_explain_gap_marks_before_context_inexact_when_none_exists() -> None:
    events = [event_at(1, "2026-07-01T09:30:00.000Z", "after.exe")]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:20:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["before"] is None
    assert body["before_context_truncated"] is False
    assert body["before_context_exact"] is False
    assert body["after"]["id"] == 1


def test_explain_gap_finds_nearest_before_in_dense_context_window() -> None:
    events = [
        event_at(1, "2026-07-01T09:00:00.000Z", "before-1.exe"),
        event_at(2, "2026-07-01T09:01:00.000Z", "before-2.exe"),
        event_at(3, "2026-07-01T09:02:00.000Z", "before-3.exe"),
        event_at(4, "2026-07-01T09:30:00.000Z", "after.exe"),
    ]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:20:00.000Z",
                "--limit",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["before"]["id"] == 3
    assert body["after"]["id"] == 4
    assert body["previous_event_delta_seconds"] == 480
    assert body["next_event_delta_seconds"] == 600
    assert body["before_context_truncated"] is False
    assert body["before_context_exact"] is True
    assert len(server.requests) > 3


def test_explain_gap_marks_before_context_inexact_for_dense_same_millisecond() -> None:
    events = [
        event_at(1, "2026-07-01T09:09:59.999Z", "before-1.exe"),
        event_at(2, "2026-07-01T09:09:59.999Z", "before-2.exe"),
        event_at(3, "2026-07-01T09:09:59.999Z", "before-3.exe"),
        event_at(4, "2026-07-01T09:30:00.000Z", "after.exe"),
    ]
    with FakeLocalTraceServer({"/events": {"body": events_route(events)}}) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:20:00.000Z",
                "--limit",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["before"]["observed_at"] == "2026-07-01T09:09:59.999Z"
    assert body["before_context_truncated"] is True
    assert body["before_context_exact"] is False
    assert body["after"]["id"] == 4


def test_scripts_return_machine_readable_error_when_core_is_unavailable() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "http://127.0.0.1:1"])

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert "LocalTrace request failed" in body["error"]


def test_scripts_return_machine_readable_error_for_non_object_json() -> None:
    with FakeLocalTraceServer({"/events": {"body": []}}) as server:
        result = run_script(
            "localtrace_recent_events.py",
            [
                "--limit",
                "1",
                "--to",
                "2026-07-02T00:00:00.000Z",
                "--lookback-days",
                "1",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    assert output_json(result) == {
        "ok": False,
        "error": "LocalTrace request failed: expected JSON object response",
    }


def test_scripts_return_machine_readable_error_for_http_200_error_body() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": False, "error": "store unavailable"}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01T00:00:00.000Z",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    assert output_json(result) == {
        "ok": False,
        "error": "LocalTrace request failed: store unavailable",
    }


def test_scripts_return_machine_readable_error_for_non_array_events() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": {"id": 1}}}}
    ) as server:
        result = run_script(
            "localtrace_events_between.py",
            [
                "--from",
                "2026-07-01T00:00:00.000Z",
                "--to",
                "2026-07-02T00:00:00.000Z",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    assert output_json(result) == {
        "ok": False,
        "error": "LocalTrace request failed: events must be a JSON array",
    }


def test_health_script_uses_env_base_url_override() -> None:
    with FakeLocalTraceServer(
        {"/health": {"body": {"ok": True, "service": "localtrace"}}}
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 0
    assert output_json(result)["service"] == "localtrace"
    assert server.requests == ["/health"]


def test_http_helper_does_not_follow_redirects() -> None:
    with FakeLocalTraceServer(
        {
            "/health": {
                "status": 302,
                "headers": {"Location": "http://example.com/health"},
                "body": {"ok": False, "error": "redirect"},
            }
        }
    ) as server:
        result = run_script("localtrace_health.py", [], server.base_url)

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert "HTTP 302" in body["error"]


def test_scripts_reject_non_loopback_base_url_before_http_request() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "http://example.com"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must use 127.0.0.1",
    }


def test_scripts_reject_localhost_base_url_before_http_request() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "http://localhost"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must use 127.0.0.1",
    }


def test_scripts_reject_base_url_with_path_before_http_request() -> None:
    result = run_script(
        "localtrace_health.py", ["--base-url", "http://127.0.0.1:8765/api"]
    )

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must not include a path, query, or fragment",
    }


def test_scripts_reject_https_base_url_before_http_request() -> None:
    result = run_script("localtrace_health.py", ["--base-url", "https://localhost"])

    assert result.returncode == 2
    assert output_json(result) == {
        "ok": False,
        "error": "base URL must use http",
    }


def test_day_summary_refuses_partial_output_when_event_limit_is_exceeded() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": sample_events()}}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py",
            ["--date", "2026-07-01", "--limit", "2"],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert body["error"] == "day summary exceeds event limit; increase --limit"
    assert body["truncated"] is True
    assert body["source_event_limit"] == 2
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_day_summary_accepts_limit_at_core_cap() -> None:
    with FakeLocalTraceServer(
        {"/events": {"body": {"ok": True, "events": sample_events()}}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py",
            ["--date", "2026-07-01", "--limit", "5000"],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["source_event_limit"] == 5000
    assert body["event_count"] == 3
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["5000"]


def test_day_summary_accepts_exact_core_cap_response() -> None:
    capped_events = many_events(5000)
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(capped_events)}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py",
            ["--date", "2026-07-01", "--limit", "5000"],
            server.base_url,
        )

    assert result.returncode == 0
    body = output_json(result)
    assert body["ok"] is True
    assert body["event_count"] == 5000
    assert body["source_event_limit"] == 5000
    assert body["by_entity"][0]["count"] == 5000


def test_day_summary_marks_partial_for_more_than_core_cap() -> None:
    capped_events = many_events(5001)
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(capped_events)}}
    ) as server:
        result = run_script(
            "localtrace_day_summary.py",
            ["--date", "2026-07-01", "--limit", "5000"],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert body["error"] == "day summary exceeds event limit; increase --limit"
    assert body["source_event_limit"] == 5000


def test_explain_gap_refuses_partial_output_when_event_limit_is_exceeded() -> None:
    crowded_events = [
        {
            **sample_events()[0],
            "id": index + 10,
            "observed_at": f"2026-07-01T09:1{index}:00.000Z",
            "entity": f"app-{index}.exe",
        }
        for index in range(3)
    ]
    with FakeLocalTraceServer(
        {"/events": {"body": events_route(crowded_events)}}
    ) as server:
        result = run_script(
            "localtrace_explain_gap.py",
            [
                "--from",
                "2026-07-01T09:10:00.000Z",
                "--to",
                "2026-07-01T09:13:00.000Z",
                "--limit",
                "2",
            ],
            server.base_url,
        )

    assert result.returncode == 1
    body = output_json(result)
    assert body["ok"] is False
    assert body["partial"] is True
    assert body["error"] == "gap explanation exceeds event limit; increase --limit"
    assert body["truncated"] is True
    assert body["source_event_limit"] == 2
    path, query = parse_request(server.requests[0])
    assert path == "/events"
    assert query["limit"] == ["3"]


def test_skill_scripts_do_not_import_core_or_sqlite() -> None:
    script_paths = sorted(SCRIPTS_DIR.glob("*.py"))

    assert script_paths
    forbidden_modules = {"localtrace_core", "sqlite3"}
    for script_path in script_paths:
        text = script_path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(script_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert imported.isdisjoint(forbidden_modules)
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.module.split(".")[0] not in forbidden_modules
