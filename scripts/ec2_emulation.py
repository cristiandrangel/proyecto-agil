"""Run the full Compose stack in a real Docker-backed Floci EC2 guest.

Only local emulation; never consumes AWS profiles or the owner's .env/data.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local" / "ec2-emulation"
FLOCI = "floci/floci:latest@sha256:5ee85db604c4aa74ac76e07ea5cc83086f37bb472bf3dbb97e34019e48efae9c"
PROJECT = "agil-ec2-emulation"
GUEST_PROJECT = "agil-ec2-fixture"
GUEST_CONTEXT = "/var/lib/docker/agil-ec2-context"
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
        endpoint_url="http://127.0.0.1:4567",
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
    return run(
        [
            "ssh",
            "-i",
            str(LOCAL / "id_ed25519"),
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
            "root@127.0.0.1",
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


def source_archive():
    # Whitelist Git-tracked files plus only this implementation's uncommitted
    # public files. Never traverses the working tree or includes private state.
    files = set(run(["git", "-C", str(ROOT), "ls-files", "-z"]).stdout.decode().split("\0"))
    files.update(str(p.relative_to(ROOT)) for p in (ROOT / "infra/floci-runtime").glob("*"))
    files.update(["scripts/ec2_emulation.py", "infra/compose.floci-runtime.yaml"])
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name in sorted(files):
            if not name or any(
                part in {".git", ".local", ".venv", "references", "data", "uploads", "logs"}
                for part in Path(name).parts
            ):
                continue
            if Path(name).name.startswith(".env") and name != ".env.example":
                continue
            if Path(name).suffix in {".pem", ".key", ".dump", ".sql"}:
                continue
            path = ROOT / name
            if path.is_file() and not path.is_symlink():
                archive.add(path, arcname=name, recursive=False)
    return output.getvalue()


def stage_guest_context(destination=GUEST_CONTEXT):
    # Only this public image build directory is copied to the isolated engine.
    run(COMPOSE + ["exec", "-T", "engine", "mkdir", "-p", destination])
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode="w") as tar:
        for path in (ROOT / "infra/floci-runtime").iterdir():
            if path.is_file():
                tar.add(path, arcname=path.name)
    run(
        COMPOSE + ["exec", "-T", "engine", "tar", "xf", "-", "-C", destination],
        input=context.getvalue(),
    )


def create():
    LOCAL.mkdir(parents=True, exist_ok=True)
    LOCAL.chmod(0o700)
    if (LOCAL / "state.json").exists():
        # The outer engine may have stopped with the PC. Preserve its volume,
        # restart the existing emulator, then reconcile via EC2 lifecycle APIs.
        run(COMPOSE + ["up", "-d", "--wait"], capture=False)
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
    import shutil

    if shutil.disk_usage(ROOT).free < 15 * 1024**3:
        raise RuntimeError("Need at least 15 GiB free disk; never prune unrelated resources")
    run(COMPOSE + ["up", "-d", "--wait"], capture=False)
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
        UserData=(ROOT / "infra/floci-runtime/user-data.sh").read_text(),
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


def bootstrap():
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
        "CHATWOOT_WEBHOOK_SECRET='fixture-disabled', CLOUDFLARE_TUNNEL_TOKEN='', LANGFUSE_CAPTURE_CONTENT='false')\n"
        "lines=[line.split('=',1)[0]+'='+values[line.split('=',1)[0]] if '=' in line and not line.lstrip().startswith('#') else line for line in p.read_text().splitlines()]\n"
        "p.write_text('COMPOSE_PROJECT_NAME=agil-ec2-fixture\\n'+'\\n'.join(lines)+'\\n')\np.chmod(0o600)\nPY"
    )
    compose("up -d --build --wait --wait-timeout 600", capture=False)
    compose("exec -T backend python -m scripts.seed", capture=False)
    print("Fixture stack bootstrapped inside guest", flush=True)


def verify():
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
    if {row["Service"] for row in containers} != expected:
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
    if central != "13|14|0" or memory != "0|0|0|0":
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
        "fixtures": {
            "customers": 13,
            "debts": 14,
            "settlements": 0,
            "campaigns": 0,
            "inbox": 0,
            "outbox": 0,
            "inference_reservations": 0,
        },
        "external_integrations": "disabled; no messages or inference",
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
    forwarding = (ROOT / "infra/floci-runtime/sshd-forwarding.conf").read_bytes()
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
    tunnel = run(["docker", "inspect", "agil-ec2-tunnel"], check=False)
    if tunnel.returncode == 0:
        existing = json.loads(tunnel.stdout)[0]
        if existing["Config"].get("Labels", {}).get("io.proyecto-agil.emulation") != "tunnel":
            raise RuntimeError("Tunnel name belongs to another container")
        if not existing["State"]["Running"]:
            run(["docker", "rm", "agil-ec2-tunnel"])
            tunnel = None
    if tunnel is None or tunnel.returncode != 0:
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "agil-ec2-tunnel",
                "--label",
                "io.proyecto-agil.emulation=tunnel",
                "--restart",
                "unless-stopped",
                "--network",
                "host",
                "--user",
                str(os.getuid()) + ":" + str(os.getgid()),
                "--mount",
                "type=bind,src=" + str(LOCAL) + ",dst=" + str(LOCAL) + ",readonly",
                "--mount",
                "type=bind,src=/etc/passwd,dst=/etc/passwd,readonly",
                "--mount",
                "type=bind,src=/etc/group,dst=/etc/group,readonly",
                "--entrypoint",
                "ssh",
                "agil-ec2-runner:local",
                "-i",
                str(LOCAL / "id_ed25519"),
                "-p",
                "2244",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=" + str(LOCAL / "known_hosts"),
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-N",
                "-L",
                "127.0.0.1:18080:127.0.0.1:8080",
                "-L",
                "127.0.0.1:13000:127.0.0.1:3000",
                "-L",
                "127.0.0.1:19090:127.0.0.1:9090",
                "root@127.0.0.1",
            ]
        )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in ["http://127.0.0.1:18080/login", "http://127.0.0.1:13000/api/public/health"]:

        def reachable(url=url):
            with opener.open(url, timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError("HTTP forward did not return 200")

        wait_for(reachable, timeout=120)
    print("Host HTTP /login and Langfuse health verified through SSH forwards")
    print("Central: http://localhost:18080/central")
    print("Langfuse: http://localhost:13000")
    print("Private fixture credentials: " + str(destination))


def status():
    run(COMPOSE + ["ps"], capture=False)
    if (LOCAL / "state.json").exists():
        print("EC2 instance: " + state()["instance_id"])
        compose("ps", capture=False)


def close_access():
    existing = run(["docker", "inspect", "agil-ec2-tunnel"], check=False)
    if existing.returncode == 0:
        info = json.loads(existing.stdout)[0]
        if info["Config"].get("Labels", {}).get("io.proyecto-agil.emulation") != "tunnel":
            raise RuntimeError("Refusing to remove a container without this fixture label")
        run(["docker", "rm", "-f", "agil-ec2-tunnel"])


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "create",
            "bootstrap",
            "verify",
            "restart",
            "cleanup",
            "up",
            "access",
            "status",
            "close-access",
        ],
    )
    action = parser.parse_args().action
    if action == "up":
        create()
        bootstrap()
        verify()
        access()
    else:
        globals()[action.replace("-", "_")]()


if __name__ == "__main__":
    main()
