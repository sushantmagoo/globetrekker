"""Settings, all overridable with environment variables."""

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


# Read and edit code, run the backend's checks, inspect git. Everything else is denied:
# in headless mode nobody is there to approve it.
ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Grep",
        "Glob",
        "Edit",
        "Write",
        "Bash(uv run --directory be pytest:*)",
        "Bash(uv run --directory be ruff:*)",
        "Bash(uv run --directory be mypy:*)",
        "Bash(git status:*)",
        "Bash(git diff:*)",
        "Bash(git log:*)",
    ]
)
DISALLOWED_TOOLS = ",".join(
    [
        "Bash(git commit:*)",
        "Bash(git push:*)",
        "Bash(git reset:*)",
        "Bash(git checkout:*)",
        "Bash(git restore:*)",
        "Bash(git stash:*)",
        "Bash(git clean:*)",
        "Bash(docker:*)",
        "Bash(aws:*)",
        "Bash(gh:*)",
        "Bash(curl:*)",
        "WebFetch",
        "WebSearch",
    ]
)
DEFAULT_AGENT_CMD = [
    "claude",
    "-p",
    "--output-format",
    "stream-json",
    "--verbose",
    "--permission-mode",
    "acceptEdits",
    "--allowedTools",
    ALLOWED_TOOLS,
    "--disallowedTools",
    DISALLOWED_TOOLS,
]


@dataclass
class Settings:
    incidents_dir: Path = field(
        default_factory=lambda: Path(_env("ONCALL_INCIDENTS_DIR", str(SERVICE_DIR / "incidents")))
    )
    # The Globetrekker checkout the agent works in.
    repo_dir: Path = field(
        default_factory=lambda: Path(_env("ONCALL_REPO_DIR", str(SERVICE_DIR.parent))).resolve()
    )

    # Observability backends, as reachable from the host.
    prometheus_url: str = field(
        default_factory=lambda: _env("PROMETHEUS_URL", "http://127.0.0.1:9090")
    )
    loki_url: str = field(default_factory=lambda: _env("LOKI_URL", "http://127.0.0.1:3100"))
    tempo_url: str = field(default_factory=lambda: _env("TEMPO_URL", "http://127.0.0.1:3200"))
    service_name: str = field(
        default_factory=lambda: _env("ONCALL_SERVICE_NAME", "globetrekker-backend")
    )
    lookback_minutes: int = field(
        default_factory=lambda: int(_env("ONCALL_LOOKBACK_MINUTES", "15"))
    )
    max_logs: int = field(default_factory=lambda: int(_env("ONCALL_MAX_LOGS", "50")))
    max_traces: int = field(default_factory=lambda: int(_env("ONCALL_MAX_TRACES", "5")))

    agent_enabled: bool = field(default_factory=lambda: _bool("ONCALL_AGENT_ENABLED", True))
    # The prompt is passed on stdin.
    agent_command: list[str] = field(
        default_factory=lambda: shlex.split(_env("ONCALL_AGENT_CMD", "")) or list(DEFAULT_AGENT_CMD)
    )
    agent_timeout_seconds: int = field(
        default_factory=lambda: int(_env("ONCALL_AGENT_TIMEOUT_SECONDS", "1800"))
    )
    # Grafana re-sends firing alerts; one incident per alert fingerprint in this period.
    dedup_seconds: int = field(default_factory=lambda: int(_env("ONCALL_DEDUP_SECONDS", "3600")))
