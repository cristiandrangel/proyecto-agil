"""Privacy regression for the public source transfer into a fresh EC2 guest."""

import io
import subprocess
import tarfile

from scripts import ec2_emulation


def test_source_transfer_excludes_private_files_even_if_accidentally_tracked(tmp_path, monkeypatch):
    files = [
        ".env",
        ".env.production",
        ".env.example",
        ".local/token",
        ".git/config",
        "infra/floci-runtime/public.sh",
        "public.txt",
        "private.key",
        "backup.dump",
        "link.txt",
    ]
    for name in files[:-1]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SECRET" if name != "public.txt" else "public source")
    (tmp_path / "link.txt").symlink_to(tmp_path / ".env")
    monkeypatch.setattr(ec2_emulation, "ROOT", tmp_path)
    monkeypatch.setattr(
        ec2_emulation,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            [], 0, stdout="\0".join(files).encode(), stderr=b""
        ),
    )
    archive = ec2_emulation.source_archive()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert set(tar.getnames()) == {
            ".env.example",
            "infra/floci-runtime/public.sh",
            "public.txt",
        }
        assert tar.extractfile("public.txt").read() == b"public source"
