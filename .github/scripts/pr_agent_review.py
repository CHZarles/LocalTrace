from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COMMENT_MARKER = "<!-- localtrace-pr-agent-review -->"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
MAX_DOC_CHARS = 5000
MAX_ISSUE_CHARS = 5000
MAX_DIFF_CHARS = 65000
REQUEST_TIMEOUT_SECONDS = 300

DOC_PATHS = [
    "README.md",
    "DEVELOPING.md",
    "WINDOWS_DEV.md",
    "RELEASING.md",
    "DEVELOPMENT_WORKFLOW.md",
    "docs/WORKFLOW.md",
    "docs/LOCALTRACE_SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/EVENT_SCHEMA.md",
    "docs/INFRASTRUCTURE.md",
    "docs/ISSUES.md",
]


def main() -> int:
    args = parse_args()
    event = load_github_event()
    repo = required_env("GITHUB_REPOSITORY")
    token = required_env("GITHUB_TOKEN")
    pr = event["pull_request"]
    pr_number = int(pr["number"])

    try:
        body = build_review_comment(
            repo, token, pr, Path(args.diff_file), Path(args.repo_root)
        )
    except Exception as exc:  # noqa: BLE001
        body = failure_comment(exc)

    upsert_comment(repo, token, pr_number, body)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post review-only PR findings.")
    parser.add_argument("--diff-file", required=True)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def build_review_comment(
    repo: str, token: str, pr: dict[str, Any], diff_path: Path, repo_root: Path
) -> str:
    api_key = os.environ.get("REVIEW_AGENT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("REVIEW_AGENT_MODEL") or os.environ.get("OPENAI_MODEL")

    if not api_key or not model:
        return configuration_comment()

    prompt = build_prompt(repo, token, pr, diff_path, repo_root)
    review = request_model_review(api_key=api_key, model=model, prompt=prompt)
    return f"{COMMENT_MARKER}\n## PR Agent Review\n\n{review.strip()}\n"


def build_prompt(
    repo: str, token: str, pr: dict[str, Any], diff_path: Path, repo_root: Path
) -> str:
    docs = "\n\n".join(read_doc(repo_root, path) for path in DOC_PATHS)
    issues = "\n\n".join(
        fetch_issue(repo, token, number) for number in issue_numbers(pr)
    )
    diff = truncate(diff_path.read_text(encoding="utf-8"), MAX_DIFF_CHARS)

    return f"""
You are a review-only PR agent for LocalTrace.

Authority:
- You cannot approve, merge, close issues, modify code, or change scope.
- Human review remains required.

Review focus:
- Scope drift from linked issues and docs.
- Bugs, regressions, privacy/security risks, missing verification.
- LocalTrace-specific constraints: local-only, no auth/token/login, no LAN/cloud,
  raw events only, no derived block/timeline/top/report tables unless approved.

Return concise Markdown with:
- Blocking findings first, then important findings, then minor findings.
- File and line references when possible.
- If no issues are found, say that and list residual risks/test gaps.

PR:
Title: {pr.get("title", "")}
Number: {pr.get("number", "")}
Body:
{truncate(pr.get("body") or "", MAX_ISSUE_CHARS)}

Linked issues:
{issues or "No linked issues found in PR body/title."}

Relevant docs:
{docs}

Diff:
{diff}
""".strip()


def request_model_review(api_key: str, model: str, prompt: str) -> str:
    base_url = (
        os.environ.get("REVIEW_AGENT_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict, review-only code reviewer.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    data = request_json(
        "POST",
        f"{base_url}/chat/completions",
        token=api_key,
        payload=payload,
        accept="application/json",
    )
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Review model returned an unexpected response") from exc


def upsert_comment(repo: str, token: str, pr_number: int, body: str) -> None:
    comments = github_request(
        "GET",
        repo,
        f"/issues/{pr_number}/comments?per_page=100",
        token,
    )
    for comment in comments:
        if COMMENT_MARKER in str(comment.get("body", "")):
            github_request(
                "PATCH",
                repo,
                f"/issues/comments/{comment['id']}",
                token,
                {"body": body},
            )
            return
    github_request("POST", repo, f"/issues/{pr_number}/comments", token, {"body": body})


def issue_numbers(pr: dict[str, Any]) -> list[int]:
    text = f"{pr.get('title', '')}\n{pr.get('body') or ''}"
    numbers = re.findall(r"(?:Fixes|Closes|Refs|Resolves):?\s+#(\d+)", text, re.I)
    return sorted({int(number) for number in numbers})


def fetch_issue(repo: str, token: str, number: int) -> str:
    issue = github_request("GET", repo, f"/issues/{number}", token)
    return (
        f"## Issue #{number}: {issue.get('title', '')}\n"
        f"{truncate(issue.get('body') or '', MAX_ISSUE_CHARS)}"
    )


def read_doc(repo_root: Path, path: str) -> str:
    file_path = repo_root / path
    if not file_path.exists():
        return f"## {path}\nMissing."
    text = file_path.read_text(encoding="utf-8")
    return f"## {path}\n{truncate(text, MAX_DOC_CHARS)}"


def configuration_comment() -> str:
    return f"""{COMMENT_MARKER}
## PR Agent Review

Review Agent is installed but not configured.

Required repository secrets:

- `REVIEW_AGENT_API_KEY` or `OPENAI_API_KEY`
- `REVIEW_AGENT_MODEL` or `OPENAI_MODEL`

Optional repository secret:

- `REVIEW_AGENT_BASE_URL` or `OPENAI_BASE_URL`

No approval, merge, issue closure, or code modification was performed.
"""


def failure_comment(exc: Exception) -> str:
    return f"""{COMMENT_MARKER}
## PR Agent Review

Review Agent failed before producing findings.

Failure:

```text
{type(exc).__name__}: {exc}
```

No approval, merge, issue closure, or code modification was performed.
"""


def load_github_event() -> dict[str, Any]:
    event_path = required_env("GITHUB_EVENT_PATH")
    return json.loads(Path(event_path).read_text(encoding="utf-8"))


def github_request(
    method: str,
    repo: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    return request_json(
        method,
        f"https://api.github.com/repos/{repo}{path}",
        token=token,
        payload=payload,
    )


def request_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
) -> Any:
    body = None
    headers = {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "localtrace-pr-agent-review",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {exc.code} {detail}") from exc
    return json.loads(raw) if raw else {}


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    omitted = len(value) - limit
    return f"{value[:limit]}\n\n[truncated {omitted} chars]"


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    sys.exit(main())
