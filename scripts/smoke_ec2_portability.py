"""Isolated Docker/SSH smoke: no application data, integrations or public connector.

Run with ./emulate-ec2.sh smoke-portability (Windows: emulate-ec2.ps1).
Only this run's uniquely named containers, image and network are removed.
"""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
import urllib.request
import uuid
from pathlib import Path

from scripts import ec2_emulation as ec2


def main():
    token = "agil-portability-" + uuid.uuid4().hex[:10]
    server, tunnel, image = token + "-server", token + "-tunnel", token + ":guest"
    original_run = ec2.run
    original = (ec2.LOCAL, ec2.CONTROL_HOST, ec2.CONTROL_NETWORK, ec2.TUNNEL_NAME)
    created = []
    network_created = False

    def run(command, **kwargs):
        # Random host ports permit this smoke beside the running demonstration.
        command = [
            arg.replace("127.0.0.1:18080:18080", "127.0.0.1::18080")
            .replace("127.0.0.1:13000:13000", "127.0.0.1::13000")
            .replace("127.0.0.1:19090:19090", "127.0.0.1::19090")
            for arg in command
        ]
        return original_run(command, **kwargs)

    try:
        original_run(
            [
                "docker",
                "network",
                "create",
                "--label",
                "io.proyecto-agil.emulation=portability-smoke",
                token,
            ]
        )
        network_created = True
        original_run(
            [
                "docker",
                "build",
                "-t",
                image,
                "-f",
                str(ec2.ROOT / "infra/floci-runtime/Dockerfile.guest"),
                str(ec2.ROOT / "infra/floci-runtime"),
            ],
            capture=False,
        )
        original_run(
            [
                "docker",
                "create",
                "--name",
                server,
                "--network",
                token,
                "--network-alias",
                "engine",
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                "mkdir -p /run/sshd; exec /usr/sbin/sshd -D -p 2244",
            ]
        )
        created.append(server)
        with tempfile.TemporaryDirectory(prefix="agil-portability-") as directory:
            ec2.LOCAL = Path(directory)
            ec2.CONTROL_HOST, ec2.CONTROL_NETWORK, ec2.TUNNEL_NAME = "engine", token, tunnel
            original_run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(ec2.LOCAL / "id_ed25519")]
            )
            output = io.BytesIO()
            public_key = (ec2.LOCAL / "id_ed25519.pub").read_bytes()
            with tarfile.open(fileobj=output, mode="w") as tar:
                folder = tarfile.TarInfo(".ssh")
                folder.type, folder.mode = tarfile.DIRTYPE, 0o700
                tar.addfile(folder)
                entry = tarfile.TarInfo(".ssh/authorized_keys")
                entry.mode, entry.size = 0o600, len(public_key)
                tar.addfile(entry, io.BytesIO(public_key))
            original_run(["docker", "cp", "-", server + ":/root"], input=output.getvalue())
            original_run(["docker", "start", server])
            # Obtain the host key without disabling strict checking on the tunnel.
            key = (
                original_run(["docker", "exec", server, "cat", "/etc/ssh/ssh_host_ed25519_key.pub"])
                .stdout.decode()
                .split()
            )
            (ec2.LOCAL / "known_hosts").write_text("[engine]:2244 " + key[0] + " " + key[1] + "\n")
            http = "from http.server import BaseHTTPRequestHandler,HTTPServer\nfrom threading import Thread\nclass Handler(BaseHTTPRequestHandler):\n def do_GET(self):\n  self.send_response(200);self.end_headers();self.wfile.write(b'portability-ok')\n def log_message(self,*args): pass\nfor port in (8080,3000,9090): Thread(target=HTTPServer(('0.0.0.0',port),Handler).serve_forever,daemon=True).start()\nimport time;time.sleep(3600)"
            original_run(["docker", "exec", "-d", server, "python3", "-c", http])
            ec2.run = run
            created.append(tunnel)
            ec2.start_access_tunnel()
            probe = (
                "import urllib.request; assert all(urllib.request.urlopen('http://"
                + tunnel
                + ":'+str(port)+'/health',timeout=5).read()==b'portability-ok' for port in (18080,13000,19090));print('bridge SSH forwards: OK')"
            )
            ec2.wait_for(
                lambda: original_run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        token,
                        "--entrypoint",
                        "python3",
                        ec2.RUNNER_IMAGE,
                        "-c",
                        probe,
                    ]
                ),
                timeout=45,
            )
            inspected = json.loads(original_run(["docker", "inspect", tunnel]).stdout)[0]
            assert inspected["HostConfig"]["NetworkMode"] == token
            assert not inspected["Mounts"]
            bindings = inspected["NetworkSettings"]["Ports"]
            assert all(
                binding["HostIp"] == "127.0.0.1" for rows in bindings.values() for binding in rows
            )
            host_checked = False
            if not __import__("os").environ.get("EC2_CONTROL_HOST"):
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for rows in bindings.values():
                    with opener.open(
                        "http://127.0.0.1:" + rows[0]["HostPort"] + "/health", timeout=5
                    ) as response:
                        assert response.read() == b"portability-ok"
                host_checked = True
            report = {
                "status": "ok",
                "architecture": ec2.docker_architecture(),
                "bridge_ssh_forwards": 3,
                "loopback_only_published_ports": True,
                "host_loopback_http_checked": host_checked,
                "host_socket_or_key_mount_in_tunnel": False,
                "providers_contacted": False,
                "active_projects_modified": False,
            }
            print(json.dumps(report, indent=2))
            return report
    finally:
        ec2.run = original_run
        ec2.LOCAL, ec2.CONTROL_HOST, ec2.CONTROL_NETWORK, ec2.TUNNEL_NAME = original
        for container in reversed(created):
            original_run(["docker", "rm", "-f", "-v", container], check=False)
        if network_created:
            original_run(["docker", "network", "rm", token], check=False)
        original_run(["docker", "image", "rm", image], check=False)


if __name__ == "__main__":
    main()
