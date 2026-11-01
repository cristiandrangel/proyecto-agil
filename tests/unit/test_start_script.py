"""Docker-only launcher routing; fake Docker prevents changing running services."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "origin,token,public",
    [
        ("http://localhost:8080", "", False),
        ("https://demo.example.test", "test-token-not-a-real-secret", True),
        ("https://demo.example.test", "", False),
        ('"https://demo.example.test"', '"test-token-not-a-real-secret"', True),
    ],
)
def test_start_uses_configured_origin_and_enables_only_required_public_profile(
    tmp_path, origin, token, public
):
    repo = Path(__file__).resolve().parents[2]
    start = tmp_path / "start.sh"
    start.write_bytes((repo / "start.sh").read_bytes())
    start.chmod(0o755)
    (tmp_path / ".env").write_text(f"PUBLIC_BASE_URL={origin}\nCLOUDFLARE_TUNNEL_TOKEN={token}\n")
    executable = tmp_path / "docker"
    executable.write_text("""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == run ]]; then
  if [[ "${*: -1}" == scripts/configure_env.py ]]; then
    printf '%s\\n' 'Private configuration prepared.'
  else
    exec "$START_TEST_PYTHON" -
  fi
elif [[ "$1" == compose ]]; then
  printf '%s\\n' "$@" > "$START_TEST_LOG"
else
  exit 2
fi
""")
    executable.chmod(0o755)
    environment = os.environ | {
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "START_TEST_PYTHON": sys.executable,
        "START_TEST_LOG": str(tmp_path / "compose-args"),
    }
    result = subprocess.run(
        [str(start)], env=environment, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    args = (tmp_path / "compose-args").read_text().splitlines()
    assert ("--profile" in args) == public
    if public:
        assert args.index("--profile") < args.index("up")
    assert f"Aplicación: {origin.strip(chr(34))}/central" in result.stdout
    assert token.strip(chr(34)) not in result.stdout if token else True


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:secret@example.test",
        "https://example.test?private=secret",
        "https://example.test/path",
        "https://example.test/#fragment",
    ],
)
def test_start_rejects_unsafe_origin_without_echoing_private_url(tmp_path, origin):
    repo = Path(__file__).resolve().parents[2]
    script = (repo / "start.sh").read_text()
    embedded = script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    (tmp_path / ".env").write_text(f"PUBLIC_BASE_URL={origin}\n")
    result = subprocess.run(
        [sys.executable, "-c", embedded], cwd=tmp_path, text=True, capture_output=True, check=False
    )
    assert result.returncode != 0
    assert origin not in result.stderr and origin not in result.stdout


def test_start_does_not_execute_private_env_content(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    embedded = (repo / "start.sh").read_text().split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    sentinel = tmp_path / "should-not-exist"
    (tmp_path / ".env").write_text(
        f"PUBLIC_BASE_URL=https://example.test\nCLOUDFLARE_TUNNEL_TOKEN=$(touch {sentinel})\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", embedded], cwd=tmp_path, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["https://example.test", "public"]
    assert not sentinel.exists()
