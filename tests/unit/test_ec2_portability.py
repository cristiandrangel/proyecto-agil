"""Docker Desktop control plane contracts; no Docker or external provider calls."""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts import ec2_emulation as ec2


@pytest.mark.parametrize(
    "architecture,expected",
    [("amd64", "x86_64"), ("x86_64", "x86_64"), ("arm64", "arm64"), ("aarch64", "arm64")],
)
def test_daemon_architecture_not_host_uname(monkeypatch, architecture, expected):
    monkeypatch.setattr(
        ec2,
        "run",
        lambda *args, **kw: subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"OSType": "linux", "Architecture": architecture}).encode()
        ),
    )
    assert ec2.docker_architecture() == expected


def test_low_desktop_memory_is_an_actionable_recommendation_not_a_false_reservation(
    monkeypatch, capsys
):
    info = {"OSType": "linux", "Architecture": "arm64", "MemTotal": 6 * 1024**3, "NCPU": 4}
    monkeypatch.setattr(
        ec2,
        "run",
        lambda *args, **kw: subprocess.CompletedProcess([], 0, stdout=json.dumps(info).encode()),
    )
    import shutil

    monkeypatch.setattr(
        shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100 * 1024**3, 0, 100 * 1024**3)
    )
    ec2.doctor()
    output = capsys.readouterr().out
    assert "not a reservation" in output
    assert "Limited RAM" in output


def test_windows_crlf_context_is_executable_and_has_native_arm_catalog(tmp_path):
    script = tmp_path / "guest-entrypoint.sh"
    script.write_bytes(b"#!/bin/sh\r\necho ready\r\n")
    script.chmod(0o644)
    catalog = tmp_path / "image-catalog.yaml"
    catalog.write_bytes(b"architecture: x86_64\r\n")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        ec2.add_public_file(tar, script, script.name)
        ec2.add_public_file(tar, catalog, catalog.name, architecture="arm64")
    with tarfile.open(fileobj=io.BytesIO(output.getvalue())) as tar:
        assert tar.getmember(script.name).mode == 0o755
        assert tar.extractfile(script.name).read() == b"#!/bin/sh\necho ready\n"
        assert tar.extractfile(catalog.name).read() == b"architecture: arm64\n"


def test_ssh_uses_ephemeral_private_key_on_desktop_mount(tmp_path, monkeypatch):
    key = tmp_path / "id_ed25519"
    key.write_bytes(b"private test fixture")
    key.chmod(0o777)
    monkeypatch.setattr(ec2, "LOCAL", tmp_path)
    monkeypatch.setattr(ec2, "CONTROL_HOST", "engine")
    used = []

    def run(command, **kw):
        copied = Path(command[command.index("-i") + 1])
        assert copied.read_bytes() == key.read_bytes()
        assert copied.stat().st_mode & 0o777 == 0o600
        assert copied != key
        assert "root@engine" in command
        used.append(copied)

    monkeypatch.setattr(ec2, "run", run)
    ec2.ssh("true")
    assert not used[0].exists()


def test_tunnel_publishes_loopback_and_copies_only_ssh_files(tmp_path, monkeypatch):
    for name in ("id_ed25519", "known_hosts", "evaluator.env", "state.json"):
        (tmp_path / name).write_text("fixture " + name)
    monkeypatch.setattr(ec2, "LOCAL", tmp_path)
    monkeypatch.setattr(ec2, "CONTROL_HOST", "engine")
    calls = []
    monkeypatch.setattr(ec2, "run", lambda command, **kw: calls.append((command, kw)))
    ec2.start_access_tunnel()
    create = calls[0][0]
    assert create[create.index("--network") + 1] == ec2.CONTROL_NETWORK
    assert "host" not in create and "--mount" not in create and "--user" not in create
    for port in (18080, 13000, 19090):
        assert f"127.0.0.1:{port}:{port}" in create
    with tarfile.open(fileobj=io.BytesIO(calls[1][1]["input"])) as tar:
        assert set(tar.getnames()) == {"id_ed25519", "known_hosts"}
        assert all(entry.mode == 0o600 for entry in tar)


def test_windows_delivery_uses_checked_host_acl_but_still_rejects_owner_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(ec2, "ROOT", tmp_path)
    delivery = tmp_path / ".env.entrega"
    delivery.write_text("OPENAI_API_KEY=fixture-only\n")
    delivery.chmod(0o777)
    monkeypatch.delenv("EC2_WINDOWS_ACL", raising=False)
    with pytest.raises(ValueError, match="private file"):
        ec2.load_delivery(delivery)
    monkeypatch.setenv("EC2_WINDOWS_ACL", "checked")
    assert ec2.load_delivery(delivery)["OPENAI_API_KEY"] == "fixture-only"
    owner = tmp_path / ".env"
    owner.write_text("OPENAI_API_KEY=fixture-owner\n")
    with pytest.raises(ValueError, match="owner environment"):
        ec2.load_delivery(owner)


@pytest.mark.parametrize(
    "desktop,endpoint,expected_socket",
    [
        (False, "unix:///tmp/custom.sock", "/tmp/custom.sock"),
        (True, "unix:///Users/test/.docker/run/docker.sock", "/var/run/docker.sock"),
    ],
)
def test_bash_launcher_handles_spaces_context_socket_and_fixed_container_path(
    tmp_path, desktop, endpoint, expected_socket
):
    repo = tmp_path / "checkout with spaces"
    repo.mkdir()
    launcher = Path(ec2.__file__).parents[1] / "emulate-ec2.sh"
    (repo / "emulate-ec2.sh").write_text(launcher.read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    log = tmp_path / "calls.jsonl"
    fake.write_text("""#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
with open(os.environ['FAKE_DOCKER_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
if args[:1]==['info']: print('linux|'+os.environ['FAKE_DOCKER_OS'])
if args[:2]==['context','inspect']: print(os.environ['FAKE_DOCKER_ENDPOINT'])
if args[:2]==['network','inspect'] and '--format' in args: print('control')
""")
    fake.chmod(0o755)
    env = dict(
        os.environ,
        PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
        FAKE_DOCKER_LOG=str(log),
        FAKE_DOCKER_OS="Docker Desktop" if desktop else "Linux",
        FAKE_DOCKER_ENDPOINT=endpoint,
    )
    env.pop("DOCKER_HOST", None)
    subprocess.run(
        ["bash", str(repo / "emulate-ec2.sh"), "up", "--delivery-file", str(repo / ".env.entrega")],
        check=True,
        env=env,
    )
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    run = next(command for command in commands if command[0] == "run")
    assert f"type=bind,src={expected_socket},dst=/var/run/docker.sock" in run
    assert f"type=bind,src={repo},dst=/workspace" in run
    assert run[-1] == "/workspace/.env.entrega"
    assert "/etc/passwd" not in " ".join(run) and "host" not in run


def test_evals_forwards_arguments_as_literals_to_existing_guest_backend(monkeypatch):
    import shlex

    calls = []
    monkeypatch.setattr(ec2, "state", lambda: {"instance_id": "existing-guest"})
    monkeypatch.setattr(ec2, "compose", lambda command, **kwargs: calls.append((command, kwargs)))
    arguments = [
        "--output",
        "report with spaces.json",
        "--case",
        "literal$(touch /tmp/forbidden)'value",
    ]
    ec2.evals(arguments)
    assert shlex.split(calls[0][0]) == [
        "exec",
        "-T",
        "backend",
        "python",
        "-m",
        "scripts.run_evals",
        *arguments,
    ]
    assert calls[0][1] == {"capture": False}
    assert len(calls) == 1


def test_legacy_engine_attaches_bridge_without_recreating_running_daemon(monkeypatch):
    calls = []
    info = {
        "Config": {
            "Labels": {
                "com.docker.compose.project": ec2.PROJECT,
                "com.docker.compose.service": "engine",
            }
        },
        "State": {"Running": True},
        "NetworkSettings": {"Networks": {"legacy-default": {}}},
    }

    def run(command, **kwargs):
        calls.append(command)
        if command[-3:] == ["ps", "-aq", "engine"]:
            return subprocess.CompletedProcess(command, 0, stdout=b"legacy-engine-id\n")
        if command[1] == "inspect":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps([info]).encode())
        return subprocess.CompletedProcess(command, 0, stdout=b"")

    monkeypatch.setattr(ec2, "run", run)
    ec2.resume_outer_engine()
    assert [
        "docker",
        "network",
        "connect",
        "--alias",
        "engine",
        ec2.CONTROL_NETWORK,
        "legacy-engine-id",
    ] in calls
    assert not any(
        "up" in command or "start" in command or "restart" in command for command in calls
    )


def test_zip_delivery_uses_allowlist_and_never_discovers_private_or_extra_files(
    tmp_path, monkeypatch
):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/public-source-manifest.txt").write_text(
        "public.txt\n.env.entrega\n.local/token\nlinked/public.txt\n.env.example\n"
    )
    (tmp_path / "public.txt").write_text("public fixture")
    (tmp_path / ".env.example").write_text("PUBLIC_EXAMPLE=\n")
    (tmp_path / ".env.entrega").write_text("PRIVATE")
    (tmp_path / "unlisted.txt").write_text("must not be discovered")
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local/token").write_text("PRIVATE")
    (tmp_path / "linked").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(ec2, "ROOT", tmp_path)
    monkeypatch.setattr(
        ec2,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 128, stdout=b"", stderr=b"not a git repository"
        ),
    )
    with tarfile.open(fileobj=io.BytesIO(ec2.source_archive())) as tar:
        assert set(tar.getnames()) == {"public.txt", ".env.example"}


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../.env", "a/../secret", "C:/secret", "a\\secret", "a//secret", "a/./secret"],
)
def test_zip_manifest_rejects_absolute_traversal_and_windows_alias_paths(
    tmp_path, monkeypatch, path
):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra/public-source-manifest.txt").write_text(path + "\n")
    monkeypatch.setattr(ec2, "ROOT", tmp_path)
    monkeypatch.setattr(
        ec2, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 128, stdout=b"")
    )
    with pytest.raises(ValueError, match="unsafe path"):
        ec2.source_archive()


@pytest.mark.parametrize("architecture", ["x86_64", "arm64"])
def test_first_launch_requests_an_instance_compatible_with_native_image(
    tmp_path, monkeypatch, architecture
):
    from types import SimpleNamespace

    userdata = tmp_path / "infra/floci-runtime/user-data.sh"
    userdata.parent.mkdir(parents=True)
    userdata.write_text("#!/bin/sh\ntrue\n")
    monkeypatch.setattr(ec2, "ROOT", tmp_path)
    local = tmp_path / "local"
    local.mkdir()
    (local / "id_ed25519").write_text("fixture-private")
    (local / "id_ed25519.pub").write_text("fixture-public")
    monkeypatch.setattr(ec2, "LOCAL", local)
    monkeypatch.setattr(ec2, "doctor", lambda: None)
    monkeypatch.setattr(ec2, "docker_architecture", lambda: architecture)
    monkeypatch.setattr(ec2, "stage_guest_context", lambda: None)
    monkeypatch.setattr(ec2, "run", lambda *a, **k: None)
    monkeypatch.setattr(ec2, "engine", lambda *a, **k: None)
    monkeypatch.setattr(ec2, "wait_for", lambda *a, **k: None)
    requests = []
    client = SimpleNamespace(
        delete_key_pair=lambda **kw: None,
        import_key_pair=lambda **kw: None,
        run_instances=lambda **kw: (
            requests.append(kw) or {"Instances": [{"InstanceId": "fixture"}]}
        ),
    )
    monkeypatch.setattr(ec2, "ec2", lambda: client)
    ec2.create()
    assert (
        requests[0]["InstanceType"] == {"arm64": "m6g.large", "x86_64": "t2.xlarge"}[architecture]
    )
    assert requests[0]["ImageId"] == "ami-agil-compose"


@pytest.mark.parametrize("architecture", ["x86_64", "arm64"])
def test_resource_verification_checks_the_requested_native_profile(architecture):
    profile = ec2.GUEST_PROFILES[architecture]
    memory = profile["memory_gib"] * 1024**3
    limits = {"Memory": memory, "NanoCpus": profile["cpus"] * 1_000_000_000}
    cgroup = [str(memory), "0", f"{profile['cpus'] * 100000} 100000"]
    ec2.verify_guest_resource_limits(profile["instance_type"], limits, cgroup)
    with pytest.raises(RuntimeError, match="cgroup"):
        ec2.verify_guest_resource_limits(
            profile["instance_type"], limits, [str(memory), "0", "max 100000"]
        )
    with pytest.raises(RuntimeError, match="CPU/RAM"):
        ec2.verify_guest_resource_limits(profile["instance_type"], dict(limits, Memory=0), cgroup)
