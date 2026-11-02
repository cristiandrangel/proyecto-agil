"""Run the full Compose stack in a real Docker-backed Floci EC2 guest.

Only local emulation; never consumes AWS profiles or the owner's .env/data.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config

from scripts.ec2_live_config import parse_delivery

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local" / "ec2-emulation"
FLOCI = "floci/floci:latest@sha256:5ee85db604c4aa74ac76e07ea5cc83086f37bb472bf3dbb97e34019e48efae9c"
PROJECT = "agil-ec2-emulation"
GUEST_PROJECT = "agil-ec2-fixture"
GUEST_CONTEXT = "/var/lib/docker/agil-ec2-context"
CONTROL_HOST = os.environ.get("EC2_CONTROL_HOST", "127.0.0.1")
CONTROL_NETWORK = os.environ.get("EC2_CONTROL_NETWORK", "agil-ec2-control")
TUNNEL_NAME = "agil-ec2-tunnel"
RUNNER_IMAGE = "agil-ec2-runner:local"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "infra/compose.floci-runtime.yaml")]


def run(args, *, input=None, capture=True, check=True):
    return subprocess.run(
        args,
        input=input,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def engine(*args, **kwargs):
    return run(COMPOSE + ["exec", "-T", "engine", "docker", *args], **kwargs)


def ec2():
    # Hard-coded loopback endpoint and fictional credentials; no host AWS config.
    return boto3.client(
        "ec2",
        endpoint_url=f"http://{CONTROL_HOST}:{4566 if CONTROL_HOST == 'engine' else 4567}",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
        config=Config(proxies={}, retries={"max_attempts": 0}, read_timeout=180),
    )


def state():
    return json.loads((LOCAL / "state.json").read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def ssh(command, *, input=None, capture=True, check=True):
    # Desktop/Windows bind mounts may expose mode 0777. OpenSSH requires a
    # private POSIX key; keep a short-lived copy on the runner's Linux filesystem.
    with tempfile.TemporaryDirectory(prefix="agil-ssh-") as directory:
        key = Path(directory) / "id_ed25519"
        key.write_bytes((LOCAL / "id_ed25519").read_bytes())
        key.chmod(0o600)
        return run(
            [
                "ssh",
                "-i",
                str(key),
                "-p",
                "2244",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "UserKnownHostsFile=" + str(LOCAL / "known_hosts"),
                "-o",
                "ConnectTimeout=5",
                "root@" + CONTROL_HOST,
                command,
            ],
            input=input,
            capture=capture,
            check=check,
        )


def compose(command, **kwargs):
    return ssh(
        "cd /srv/proyecto-agil/app && docker compose -p "
        + GUEST_PROJECT
        + " --env-file .env -f infra/compose.yaml "
        + command,
        **kwargs,
    )


def wait_for(action, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            return action()
        except Exception:
            time.sleep(2)
    raise RuntimeError("Timed out waiting for emulation readiness")


def validate_source_name(name):
    # ZIP manifests use POSIX paths regardless of the evaluator's OS. Fail closed
    # on absolute paths, drive names, traversal, aliases and Windows separators.
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError("Public source manifest contains an unsafe path")
    return name


def public_source_names():
    result = run(["git", "-C", str(ROOT), "ls-files", "-z"], check=False)
    files = set(result.stdout.decode().split("\0")) - {""} if result.returncode == 0 else set()
    manifest = ROOT / "infra/public-source-manifest.txt"
    if manifest.is_file() and not manifest.is_symlink():
        files.update(
            validate_source_name(line)
            for line in manifest.read_text().splitlines()
            if line and not line.startswith("#")
        )
    elif result.returncode != 0:
        raise RuntimeError(
            "ZIP delivery requires infra/public-source-manifest.txt; extract the complete release"
        )
    # Only explicit implementation files for an in-progress Git checkout.
    files.update(
        {
            "scripts/ec2_emulation.py",
            "scripts/ec2_live_config.py",
            "infra/compose.floci-runtime.yaml",
        }
    )
    return files


def source_archive():
    # Git-tracked paths are preferred; a versioned allowlist also supports ZIPs.
    # Never recurse into a checkout or guess that arbitrary untracked files are public.
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name in sorted(public_source_names()):
            validate_source_name(name)
            parts = Path(name).parts
            if any(
                part.lower() in {".git", ".local", ".venv", "references", "data", "uploads", "logs"}
                for part in parts
            ):
                continue
            if Path(name).name.lower().startswith(".env") and name != ".env.example":
                continue
            if Path(name).suffix.lower() in {".pem", ".key", ".dump", ".sql"}:
                continue
            path = ROOT / name
            # Exclude symlinked files AND parent directories, including links back
            # inside the checkout: the whitelist describes regular public files.
            if any(
                (ROOT.joinpath(*parts[:index])).is_symlink() for index in range(1, len(parts) + 1)
            ):
                continue
            if path.is_file():
                add_public_file(archive, path, name)
    return output.getvalue()


def stage_guest_context(destination=GUEST_CONTEXT):
    architecture = docker_architecture()
    # Only this public image build directory is copied to the isolated engine.
    run(COMPOSE + ["exec", "-T", "engine", "mkdir", "-p", destination])
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode="w") as tar:
        for name in (
            "Dockerfile.guest",
            "guest-entrypoint.sh",
            "sshd-forwarding.conf",
            "image-catalog.yaml",
        ):
            path = ROOT / "infra/floci-runtime" / name
            if path.is_symlink():
                raise ValueError("Guest image context must contain regular public files")
            add_public_file(tar, path, name, architecture=architecture)
    run(
        COMPOSE + ["exec", "-T", "engine", "tar", "xf", "-", "-C", destination],
        input=context.getvalue(),
    )


def docker_architecture():
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
    architecture = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(info.get("Architecture"))
    if info.get("OSType") != "linux" or architecture is None:
        raise RuntimeError("Use Linux containers on an amd64 or arm64 Docker Engine/Desktop")
    return architecture


def doctor():
    """Read-only diagnostics; maximum cgroup limits are not reserved memory."""
    import shutil

    architecture = docker_architecture()
    info = json.loads(run(["docker", "info", "--format", "{{json .}}"]).stdout)
    if info.get("SecurityOptions") and any("rootless" in x for x in info["SecurityOptions"]):
        raise RuntimeError("Nested privileged Docker requires rootful Engine or Docker Desktop")
    if shutil.disk_usage(ROOT).free < 15 * 1024**3:
        raise RuntimeError("Need 15 GiB free workspace disk; no unrelated resources will be pruned")
    memory_gib = info["MemTotal"] / 1024**3
    print(
        f"Docker Linux {architecture}: {info['NCPU']} CPU, {memory_gib:.1f} GiB visible RAM",
        flush=True,
    )
    if memory_gib < 12:
        print(
            "Limited RAM: start with 12+ GiB for Docker and monitor memory pressure (recommendation, not a measured minimum). 24 GiB is the outer limit, not a reservation.",
            flush=True,
        )
    if info["NCPU"] < 4:
        raise RuntimeError(
            "Allocate at least 4 CPUs to Docker Desktop: the emulated t2.xlarge requires a 4-CPU quota"
        )
    os.environ["EC2_ENGINE_CPUS"] = str(min(8, info["NCPU"]))
    print(
        "Requires privileged containers; Desktop Enhanced Container Isolation must permit Docker-in-Docker. No host networking setting needed.",
        flush=True,
    )


def add_public_file(archive, path, name, *, architecture=None):
    data = path.read_bytes()
    if path.suffix in {".sh", ".py", ".yaml", ".yml", ".toml"} or path.name.startswith(
        "Dockerfile"
    ):
        data = data.replace(b"\r\n", b"\n")
    if name == "image-catalog.yaml" and architecture:
        data = data.replace(b"architecture: x86_64", ("architecture: " + architecture).encode())
    entry = archive.gettarinfo(str(path), arcname=name)
    entry.size = len(data)
    # Git executable bits are not reliable on Windows checkouts.
    if path.suffix == ".sh":
        entry.mode = 0o755
    archive.addfile(entry, io.BytesIO(data))


def start_access_tunnel():
    # Keys travel through the Docker API, not a host path or a shared secret volume.
    command = [
        "docker",
        "create",
        "--name",
        TUNNEL_NAME,
        "--label",
        "io.proyecto-agil.emulation=tunnel",
        "--restart",
        "unless-stopped",
        "--network",
        CONTROL_NETWORK,
    ]
    for port in (18080, 13000, 19090):
        command += ["-p", f"127.0.0.1:{port}:{port}"]
    command += [
        "--entrypoint",
        "ssh",
        RUNNER_IMAGE,
        "-i",
        "/run/id_ed25519",
        "-p",
        "2244",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=/run/known_hosts",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-N",
    ]
    for local, remote in ((18080, 8080), (13000, 3000), (19090, 9090)):
        command += ["-L", f"0.0.0.0:{local}:127.0.0.1:{remote}"]
    command += ["root@" + CONTROL_HOST]
    run(command)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for name in ("id_ed25519", "known_hosts"):
            path = LOCAL / name
            entry = tar.gettarinfo(str(path), arcname=name)
            entry.mode = 0o600
            tar.addfile(entry, io.BytesIO(path.read_bytes()))
    run(["docker", "cp", "-", TUNNEL_NAME + ":/run"], input=output.getvalue())
    run(["docker", "start", TUNNEL_NAME])


def resume_outer_engine():
    """Attach the control bridge without recreating a legacy engine/guest."""
    result = run(COMPOSE + ["ps", "-aq", "engine"])
    container = result.stdout.decode().strip()
    if not container:
        run(COMPOSE + ["up", "-d", "--wait", "engine"], capture=False)
        return
    info = json.loads(run(["docker", "inspect", container]).stdout)[0]
    labels = info["Config"].get("Labels", {})
    if (
        labels.get("com.docker.compose.project") != PROJECT
        or labels.get("com.docker.compose.service") != "engine"
    ):
        raise RuntimeError("Refusing to resume an engine outside this emulation project")
    if not info["State"]["Running"]:
        run(["docker", "start", container])
    if CONTROL_NETWORK not in info.get("NetworkSettings", {}).get("Networks", {}):
        run(["docker", "network", "connect", "--alias", "engine", CONTROL_NETWORK, container])
    wait_for(lambda: engine("info"))


def create():
    doctor()
    LOCAL.mkdir(parents=True, exist_ok=True)
    LOCAL.chmod(0o700)
    if (LOCAL / "state.json").exists():
        # The outer engine may have stopped with the PC. Preserve its volume,
        # restart the existing emulator, then reconcile via EC2 lifecycle APIs.
        resume_outer_engine()
        stage_guest_context()
        emulator = json.loads(engine("inspect", "agil-floci").stdout)[0]
        # Compatibility with guests created before context moved to persistent storage.
        if any(bind.startswith("/tmp/guest/") for bind in emulator["HostConfig"].get("Binds", [])):
            stage_guest_context("/tmp/guest")
        if not emulator["State"]["Running"]:
            engine("start", "agil-floci")
        client = ec2()
        wait_for(lambda: client.describe_availability_zones())
        instance = state()["instance_id"]
        current = client.describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][
            0
        ]["State"]["Name"]
        guests = json.loads(engine("inspect", *engine("ps", "-aq").stdout.decode().split()).stdout)
        guest = next(row for row in guests if instance in row["Name"])
        if not guest["State"]["Running"] and current == "running":
            client.stop_instances(InstanceIds=[instance])
            client.get_waiter("instance_stopped").wait(
                InstanceIds=[instance], WaiterConfig={"Delay": 1, "MaxAttempts": 90}
            )
            current = "stopped"
        if current == "stopped":
            client.start_instances(InstanceIds=[instance])
        wait_for(lambda: ssh("docker info >/dev/null"), timeout=240)
        return
    run(COMPOSE + ["up", "-d", "--wait", "engine"], capture=False)
    engine("pull", FLOCI, capture=False)
    stage_guest_context()
    engine(
        "build",
        "-t",
        "agil-ec2-guest:local",
        "-f",
        GUEST_CONTEXT + "/Dockerfile.guest",
        GUEST_CONTEXT,
        capture=False,
    )
    engine("rm", "-f", "agil-floci", check=False)
    engine(
        "run",
        "-d",
        "--name",
        "agil-floci",
        "--restart",
        "unless-stopped",
        "-p",
        "4566:4566",
        "-p",
        "9169:9169",
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        GUEST_CONTEXT + "/image-catalog.yaml:/etc/floci-images.yaml:ro",
        "-v",
        "floci_state:/app/data",
        "-e",
        "FLOCI_HOSTNAME=172.17.0.1",
        "-e",
        "FLOCI_STORAGE_MODE=persistent",
        "-e",
        "FLOCI_DOCKER_RESOURCE_NAMESPACE=agil-ec2-emulation",
        "-e",
        "FLOCI_SERVICES_EC2_MOCK=false",
        "-e",
        "FLOCI_SERVICES_EC2_INSTANCE_RESOURCE_LIMITS=true",
        "-e",
        "FLOCI_NETWORK_SECURITY_GROUP_ENFORCEMENT_ENABLED=false",
        "-e",
        "FLOCI_SERVICES_EC2_VPC_NETWORKS_ENABLED=false",
        "-e",
        "FLOCI_SERVICES_EC2_PUBLISH_SECURITY_GROUP_PORTS=false",
        "-e",
        "FLOCI_SERVICES_EC2_VOLUME_BLOCK_DEVICES=false",
        "-e",
        "FLOCI_SERVICES_EC2_IMAGE_CATALOG_PATH=/etc/floci-images.yaml",
        "-e",
        "FLOCI_SERVICES_EC2_SSH_PORT_RANGE_START=2244",
        "-e",
        "FLOCI_SERVICES_EC2_SSH_PORT_RANGE_END=2244",
        "-e",
        "FLOCI_SERVICES_UI_ENABLED=false",
        FLOCI,
    )
    client = ec2()
    wait_for(lambda: client.describe_availability_zones())
    if not (LOCAL / "id_ed25519").exists():
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(LOCAL / "id_ed25519")])
    client.delete_key_pair(KeyName="agil-fixture-key")
    client.import_key_pair(
        KeyName="agil-fixture-key", PublicKeyMaterial=(LOCAL / "id_ed25519.pub").read_bytes()
    )
    instance = client.run_instances(
        ImageId="ami-agil-compose",
        InstanceType="t2.xlarge",
        MinCount=1,
        MaxCount=1,
        KeyName="agil-fixture-key",
        UserData=(ROOT / "infra/floci-runtime/user-data.sh").read_text().replace("\r\n", "\n"),
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": GUEST_PROJECT}]}
        ],
    )["Instances"][0]["InstanceId"]
    write_json(LOCAL / "state.json", {"instance_id": instance, "project": PROJECT})
    wait_for(
        lambda: ssh("test -f /srv/proyecto-agil/user-data-ready && docker info >/dev/null"),
        timeout=240,
    )
    print("EC2 guest running; UserData and SSH verified", flush=True)


def prepare_guest_environment():
    state()
    ssh(
        "mkdir -p /srv/proyecto-agil/app && tar xzf - -C /srv/proyecto-agil/app",
        input=source_archive(),
    )
    # Generate new internal credentials from the PUBLIC example inside the guest.
    ssh(
        "cd /srv/proyecto-agil/app && python3 - <<'PY'\n"
        "from pathlib import Path\nfrom scripts.configure_env import configure\n"
        "p=Path('.env')\n"
        "if p.exists(): raise SystemExit(0)\n"
        "configure(p)\nvalues=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))\n"
        "values.update(COMPOSE_PROJECT_NAME='agil-ec2-fixture', PUBLIC_BASE_URL='http://localhost:18080', LANGFUSE_PUBLIC_URL='http://localhost:13000', "
        "ENABLE_LOCAL_MESSAGE_ENDPOINT='false', OPENAI_API_KEY='', CHATWOOT_BASE_URL='http://127.0.0.1:9', "
        "CHATWOOT_CONTACTS_BASE_URL='http://127.0.0.1:9', CHATWOOT_API_TOKEN='fixture-disabled', "
        "CHATWOOT_CONTACTS_API_TOKEN='fixture-disabled', CHATWOOT_ACCOUNT_ID='999', CHATWOOT_INBOX_ID='999', "
        "CHATWOOT_WEBHOOK_SECRET='fixture-disabled', CLOUDFLARE_TUNNEL_TOKEN='', LANGFUSE_CAPTURE_CONTENT='false', LANGFUSE_MEDIA_PUBLIC_ENDPOINT='http://localhost:19090')\n"
        "lines=[line.split('=',1)[0]+'='+values[line.split('=',1)[0]] if '=' in line and not line.lstrip().startswith('#') else line for line in p.read_text().splitlines()]\n"
        "p.write_text('COMPOSE_PROJECT_NAME=agil-ec2-fixture\\n'+'\\n'.join(lines)+'\\n')\np.chmod(0o600)\nPY"
    )


def bootstrap(delivery_file=None):
    prepare_guest_environment()
    if delivery_file:
        # Before Compose creates any Langfuse DB/container, so known delivery
        # credentials become the actual first-initialization credentials.
        configure_live(delivery_file)
    compose("up -d --build --wait --wait-timeout 600", capture=False)
    compose("exec -T backend python -m scripts.seed", capture=False)
    current = state()
    if current.get("live_configured"):
        current["live_applied"] = True
        write_json(LOCAL / "state.json", current)
    print("Fixture stack bootstrapped inside guest", flush=True)


def verify(mode="auto"):
    if mode == "auto":
        mode = "live" if state().get("live_applied") else "fixture"
    instance = state()["instance_id"]
    described = ec2().describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][0]
    containers = [
        json.loads(line)
        for line in compose("ps --format json").stdout.decode().splitlines()
        if line.strip()
    ]
    guest_info = json.loads(ssh("docker info --format '{{json .}}'").stdout)
    # All application IDs must be absent from the actual host daemon.
    host_ids = set(run(["docker", "ps", "-aq", "--no-trunc"]).stdout.decode().split())
    outer_ids = set(engine("ps", "-aq", "--no-trunc").stdout.decode().split())
    inner_ids = {row["ID"] for row in containers}
    if not inner_ids or any(
        any(host.startswith(inner) for host in host_ids | outer_ids) for inner in inner_ids
    ):
        raise RuntimeError("Application containers are missing or unexpectedly on host Docker")
    for url in [
        "http://127.0.0.1:8080/health",
        "http://127.0.0.1:8080/ready",
        "http://127.0.0.1:3000/api/public/health",
    ]:
        ssh("curl --fail --silent " + shlex.quote(url))
    expected = {
        "backend",
        "worker",
        "central",
        "central-db",
        "memory-db",
        "langfuse-web",
        "langfuse-worker",
        "langfuse-db",
        "langfuse-redis",
        "langfuse-clickhouse",
        "langfuse-minio",
    }
    actual = {row["Service"] for row in containers}
    if not expected.issubset(actual) or actual - expected - {"cloudflared"}:
        raise RuntimeError("Unexpected services in guest fixture")
    if any(
        row.get("Health") not in ("healthy", "") or row.get("State") != "running"
        for row in containers
    ):
        raise RuntimeError("Not all guest services are healthy")
    outer_containers = json.loads(engine("inspect", *outer_ids).stdout)
    guest_container = next(
        row
        for row in outer_containers
        if row["Config"].get("Labels", {}).get("io.floci.resource-id") == instance
        or instance in row["Name"]
    )
    limits = guest_container["HostConfig"]
    cgroup = (
        ssh(
            "cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.current; cat /sys/fs/cgroup/cpu.max"
        )
        .stdout.decode()
        .splitlines()
    )
    if cgroup[0] != str(16 * 1024**3) or cgroup[2] != "400000 100000":
        raise RuntimeError("Guest cgroup does not enforce requested resource limits")
    if limits["Memory"] != 16 * 1024**3 or limits["NanoCpus"] != 4_000_000_000:
        raise RuntimeError("Unexpected effective guest CPU/RAM limits")
    if any(m["Destination"] == "/var/run/docker.sock" for m in guest_container.get("Mounts", [])):
        raise RuntimeError("Guest must not receive an exterior Docker socket")
    central = (
        compose(
            'exec -T central-db psql -U central -d central -Atc "SELECT (SELECT count(*) FROM customer), (SELECT count(*) FROM debt), (SELECT count(*) FROM settlement)"'
        )
        .stdout.decode()
        .strip()
    )
    memory = (
        compose(
            'exec -T memory-db psql -U memory -d memory -Atc "SELECT (SELECT count(*) FROM campaign), (SELECT count(*) FROM inbox_event), (SELECT count(*) FROM outbox), (SELECT count(*) FROM inference_reservation)"'
        )
        .stdout.decode()
        .strip()
    )
    if mode == "fixture" and (central != "13|14|0" or memory != "0|0|0|0"):
        raise RuntimeError("Fixture is not pristine")
    report = {
        "instance_id": instance,
        "ec2_state": described["State"]["Name"],
        "execution": "floci_docker_linux_guest_nested_compose",
        "mock": False,
        "guest_engine_id": guest_info["ID"],
        "guest_memory_bytes": guest_info["MemTotal"],
        "guest_services": [
            {k: r.get(k) for k in ("Service", "State", "Health")} for r in containers
        ],
        "guest_container_ids_absent_from_host_and_outer": True,
        "effective_guest_memory_limit_bytes": limits["Memory"],
        "effective_guest_nano_cpus": limits["NanoCpus"],
        "guest_has_no_exterior_docker_socket": True,
        "guest_cgroup_memory_limit_bytes": int(cgroup[0]),
        "guest_cgroup_memory_current_bytes": int(cgroup[1]),
        "guest_cgroup_cpu_max": cgroup[2],
        "verification_mode": mode,
        "fixtures": dict(
            zip(("customers", "debts", "settlements"), map(int, central.split("|")), strict=True)
        )
        | dict(
            zip(
                ("campaigns", "inbox", "outbox", "inference_reservations"),
                map(int, memory.split("|")),
                strict=True,
            )
        ),
        "external_integrations": "disabled; no messages or inference"
        if mode == "fixture"
        else "configured separately; health-only check, no messages or inference performed",
        "verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    previous_path = LOCAL / "verification.json"
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        if (
            previous.get("instance_id") == instance
            and previous.get("stop_start_postgres_persistence") == "passed"
        ):
            report["stop_start_postgres_persistence"] = "passed"
            report["stop_start_verified_at_utc"] = previous.get(
                "stop_start_verified_at_utc", previous["verified_at_utc"]
            )
    write_json(LOCAL / "verification.json", report)
    print(json.dumps(report, indent=2))
    return report


def restart():
    instance = state()["instance_id"]
    # Persistence marker in actual PostgreSQL, not an API metadata record.
    compose(
        "exec -T central-db psql -U central -d central -c \"CREATE TABLE IF NOT EXISTS ec2_emulation_probe (id integer PRIMARY KEY, value text); INSERT INTO ec2_emulation_probe VALUES (1, 'fixture-persisted') ON CONFLICT (id) DO NOTHING;\""
    )
    client = ec2()
    client.stop_instances(InstanceIds=[instance])
    client.get_waiter("instance_stopped").wait(
        InstanceIds=[instance], WaiterConfig={"Delay": 2, "MaxAttempts": 90}
    )
    client.start_instances(InstanceIds=[instance])
    wait_for(lambda: ssh("docker info >/dev/null"), timeout=240)
    # Restart policies bring the existing containers back; no reseed or new volumes.
    wait_for(lambda: ssh("curl --fail --silent http://127.0.0.1:8080/ready"), timeout=300)
    persisted = (
        compose(
            'exec -T central-db psql -U central -d central -Atc "SELECT value FROM ec2_emulation_probe WHERE id=1"'
        )
        .stdout.decode()
        .strip()
    )
    if persisted != "fixture-persisted":
        raise RuntimeError("PostgreSQL persistence check failed")
    compose('exec -T central-db psql -U central -d central -c "DROP TABLE ec2_emulation_probe"')
    compose("up -d --wait --wait-timeout 300")
    report = verify()
    report["stop_start_postgres_persistence"] = "passed"
    report["stop_start_verified_at_utc"] = report["verified_at_utc"]
    write_json(LOCAL / "verification.json", report)
    print("EC2 Stop/Start preserved actual PostgreSQL fixture marker", flush=True)


def access():
    state()
    # Alpine ships SSH forwarding disabled. The same public configuration is in
    # the image recipe; deploy it over SSH for an existing guest on upgrade.
    forwarding = (
        (ROOT / "infra/floci-runtime/sshd-forwarding.conf").read_bytes().replace(b"\r\n", b"\n")
    )
    ssh(
        'cat > /etc/ssh/sshd_config.d/00-agil-forwarding.conf && /usr/sbin/sshd -t && kill -HUP "$(cat /run/sshd.pid)"',
        input=forwarding,
    )
    close_access()
    # Credentials remain local and private; never print the environment.
    result = ssh("cat /srv/proyecto-agil/app/.env")
    destination = LOCAL / "evaluator.env"
    destination.write_bytes(result.stdout)
    destination.chmod(0o600)
    start_access_tunnel()
    # Probe from the runner's bridge network; published host ports still bind loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in ["18080/login", "13000/api/public/health"]:
        url = "http://" + TUNNEL_NAME + ":" + path

        def reachable(url=url):
            with opener.open(url, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError("HTTP forward did not return 200")

        wait_for(reachable, timeout=120)
    print("Host HTTP /login and Langfuse health verified through SSH forwards")
    exported = {}
    for line in result.stdout.decode().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            value = value.strip()
            exported[key.strip()] = (
                ast.literal_eval(value) if value.startswith(('"', "'")) else value
            )
    central_origin = exported.get("PUBLIC_BASE_URL", "http://localhost:18080")
    print("Central: " + central_origin.rstrip("/") + "/central")
    if exported.get("APP_ENV") == "production":
        print(
            "Central login uses the configured HTTPS origin; localhost is only an administrative forward."
        )
    print("Langfuse: http://localhost:13000")
    print("Private fixture credentials: " + str(destination))


def evals(arguments):
    """Forward explicit evaluator options to the existing guest backend."""
    state()
    command = "exec -T backend python -m scripts.run_evals"
    if arguments:
        command += " " + shlex.join(arguments)
    compose(command, capture=False)


def status():
    run(COMPOSE + ["ps"], capture=False)
    if (LOCAL / "state.json").exists():
        print("EC2 instance: " + state()["instance_id"])
        compose("ps", capture=False)


def load_delivery(delivery_file):
    path = Path(delivery_file)
    if (
        not path.is_file()
        or path.is_symlink()
        or (path.stat().st_mode & 0o077 and os.environ.get("EC2_WINDOWS_ACL") != "checked")
    ):
        raise ValueError("Delivery file must be a regular private file with mode 0600")
    if path.resolve() == (ROOT / ".env").resolve():
        raise ValueError("The owner environment is not a delivery integration file")
    values = parse_delivery(path.read_text())
    values.setdefault("LANGFUSE_MEDIA_PUBLIC_ENDPOINT", "http://localhost:19090")
    return values


def configure_live(delivery_file):
    state()
    values = load_delivery(delivery_file)
    # Deploy the public helper, then send only whitelisted integration values via
    # SSH stdin. Neither command arguments nor logs contain these values.
    ssh(
        "cat > /srv/proyecto-agil/app/scripts/ec2_live_config.py",
        input=(ROOT / "scripts/ec2_live_config.py").read_bytes(),
    )
    result = ssh(
        "cd /srv/proyecto-agil/app && python3 -m scripts.ec2_live_config",
        input=json.dumps(values).encode(),
    )
    report = json.loads(result.stdout)
    current = state()
    current["live_configured"] = True
    current["live_applied"] = False
    write_json(LOCAL / "state.json", current)
    write_json(LOCAL / "live-provisioning.json", report)
    print("Private integration configuration staged; internal guest secrets and data preserved.")
    print("No service restarted, no tunnel started. Apply explicitly after the authorized cutover.")


def apply_live():
    current = state()
    if not current.get("live_configured"):
        raise RuntimeError("Configure an explicit private delivery file first")
    # Captured output cannot reveal credentials via diagnostic logs. No tunnel,
    # databases, Langfuse or external provider is created or contacted here.
    ssh(
        "mkdir -p /srv/proyecto-agil/app && tar xzf - -C /srv/proyecto-agil/app",
        input=source_archive(),
    )
    compose("build backend worker")
    compose(
        "up -d --no-deps --force-recreate --wait --wait-timeout 300 backend worker langfuse-web"
    )
    current["live_applied"] = True
    write_json(LOCAL / "state.json", current)
    print(
        "Backend, worker and Langfuse web recreated with staged integrations; public tunnel remains operator-controlled."
    )


def preflight(*, report_name="preflight.json"):
    # No --live-inference: only read provider configuration/status, never send.
    result = compose(
        "exec -T backend python -m scripts.preflight --base-url http://localhost:8000", check=False
    )
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("Read-only preflight produced no valid report") from None
    write_json(LOCAL / report_name, report)
    if (
        result.returncode != 0
        or report.get("status") != "ok"
        or report.get("inference_opt_in")
        or report.get("channel_writes") != 0
    ):
        raise RuntimeError(
            "Read-only preflight failed; no public connector was started by this check"
        )
    print(json.dumps(report, indent=2))
    return report


def start_public():
    current = state()
    if not current.get("live_configured") or not current.get("live_applied"):
        raise RuntimeError(
            "Public startup requires explicitly provisioned and applied private integrations"
        )
    preflight(report_name="public-preflight.json")
    compose("--profile public up -d --no-deps cloudflared")
    print(
        "Read-only preflight passed; this guest public connector started. Other projects were not changed."
    )


def stop():
    # The instance owns its connector and application containers. Stop only this
    # exact EC2 resource, preserving all emulator and guest storage for up.
    instance = state()["instance_id"]
    client = ec2()
    client.stop_instances(InstanceIds=[instance])
    client.get_waiter("instance_stopped").wait(
        InstanceIds=[instance], WaiterConfig={"Delay": 2, "MaxAttempts": 90}
    )
    close_access()
    print("EC2 guest stopped; guest volumes and private configuration preserved. Resume with up.")


def up(delivery_file=None, *, public=False):
    if delivery_file:
        load_delivery(delivery_file)  # Fail before allocating resources for an invalid file.
    elif public and (not (LOCAL / "state.json").exists() or not state().get("live_configured")):
        raise RuntimeError(
            "--public requires an explicit delivery file or an already configured private guest"
        )
    create()
    bootstrap(delivery_file)
    verify()
    access()
    if public:
        start_public()


def close_access():
    existing = run(["docker", "inspect", TUNNEL_NAME], check=False)
    if existing.returncode == 0:
        info = json.loads(existing.stdout)[0]
        if info["Config"].get("Labels", {}).get("io.proyecto-agil.emulation") != "tunnel":
            raise RuntimeError("Refusing to remove a container without this fixture label")
        run(["docker", "rm", "-f", "-v", TUNNEL_NAME])


def cleanup():
    close_access()
    # Fixed unique Compose project; never prune, never delete another project's data.
    if (LOCAL / "state.json").exists():
        instance = state()["instance_id"]
        ec2().terminate_instances(InstanceIds=[instance])
        ec2().get_waiter("instance_terminated").wait(
            InstanceIds=[instance], WaiterConfig={"Delay": 2, "MaxAttempts": 90}
        )
    run(COMPOSE + ["down", "-v"], capture=False)
    for name in ("state.json", "known_hosts"):
        (LOCAL / name).unlink(missing_ok=True)
    print("Only the isolated emulation project and its volume were removed")


def main():
    if sys.argv[1:2] == ["evals"]:
        evals(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "evals",
            "smoke-portability",
            "doctor",
            "create",
            "bootstrap",
            "verify",
            "restart",
            "cleanup",
            "up",
            "access",
            "status",
            "close-access",
            "configure-live",
            "apply-live",
            "preflight",
            "stop",
        ],
    )
    parser.add_argument("--delivery-file")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Start only this guest connector after a successful read-only preflight",
    )
    parser.add_argument("--mode", choices=["auto", "fixture", "live"], default="auto")
    args = parser.parse_args()
    action = args.action
    if args.public and action != "up":
        parser.error("--public is only supported with up")
    if args.delivery_file and action not in {"up", "configure-live"}:
        parser.error("--delivery-file is only supported with up or configure-live")
    if action == "smoke-portability":
        from scripts.smoke_ec2_portability import main as smoke

        smoke()
        return
    if action == "configure-live":
        if not args.delivery_file:
            parser.error("configure-live requires --delivery-file explicitly")
        configure_live(args.delivery_file)
        return
    if action == "verify":
        verify(args.mode)
        return
    if action == "up":
        up(args.delivery_file, public=args.public)
    else:
        globals()[action.replace("-", "_")]()


if __name__ == "__main__":
    main()
