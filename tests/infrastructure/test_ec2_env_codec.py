"""Opt-in host Docker check, separate from the socket-free acceptance container."""

import json
import shutil
import subprocess
from uuid import uuid4

import pytest

from scripts.ec2_live_config import quote_env, read_environment


def test_compose_created_container_receives_exact_private_fixture_values(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker CLI unavailable; pure codec regression remains covered")
    available = subprocess.run(["docker", "info"], capture_output=True)
    if available.returncode:
        pytest.skip("Docker daemon unavailable")
    image = "alpine:3.20"
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
        pytest.skip("Fixture image not cached; this test never pulls images")
    values = [
        r"a\b",
        r"x\n",
        r"one\\two",
        "a'b",
        "a\\'b",
        "tail\\",
        r"$foo${BAR}$$z",
        r"back\\",
        r"\t\r\"",
        "slash\\'$abc",
    ]
    expected = {"AGIL_CODEC_" + str(i): value for i, value in enumerate(values)}
    envfile = tmp_path / "fixture.env"
    envfile.write_text(
        "".join(key + "=" + quote_env(value) + "\n" for key, value in expected.items())
    )
    envfile.chmod(0o600)
    spec = tmp_path / "compose.json"
    spec.write_text(
        json.dumps(
            {
                "services": {
                    "fixture": {
                        "image": image,
                        "network_mode": "none",
                        "environment": {key: "${" + key + "}" for key in expected},
                    }
                }
            }
        )
    )
    project = "agil-codec-" + uuid4().hex[:12]
    command = ["docker", "compose", "-p", project, "--env-file", str(envfile), "-f", str(spec)]
    try:
        subprocess.run(command + ["create", "--pull", "never"], capture_output=True, check=True)
        container_id = subprocess.check_output(command + ["ps", "-aq"]).decode().strip()
        created = json.loads(subprocess.check_output(["docker", "inspect", container_id]))[0]
        assert created["State"]["Status"] == "created"
        assert created["HostConfig"]["NetworkMode"] == "none"
        actual = dict(value.split("=", 1) for value in created["Config"]["Env"])
        assert {key: actual[key] for key in expected} == expected
        assert read_environment(envfile.read_text()) == expected
    finally:
        subprocess.run(command + ["down"], capture_output=True, check=True)
