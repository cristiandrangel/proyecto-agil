"""Privacy regression for the public source transfer into a fresh EC2 guest."""

import io
import subprocess
import tarfile

from scripts import ec2_emulation


def test_source_transfer_excludes_private_files_even_if_accidentally_tracked(tmp_path, monkeypatch):
    files = [
        ".env",
        ".env.production",
        ".env.entrega",
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


def test_private_live_delivery_updates_only_integrations_and_keeps_internal_secrets(tmp_path):
    from dotenv import dotenv_values

    from scripts.ec2_live_config import parse_delivery, provision

    env = tmp_path / ".env"
    env.write_text(
        "SESSION_SECRET=fresh-internal\nCENTRAL_DB_PASSWORD=fresh-db\nOPENAI_API_KEY=\n# ACCESOS WEB DEL EVALUADOR\nOPERATOR_PASSWORD=fresh-operator\nCHATWOOT_UI_PASSWORD=\n"
    )
    values = parse_delivery('OPENAI_API_KEY="fixture-key"\nCHATWOOT_UI_PASSWORD="pa$sw\\\'ord"\n')
    report = provision(env, values)
    parsed = dotenv_values(env)
    assert parsed["SESSION_SECRET"] == "fresh-internal"
    assert parsed["CENTRAL_DB_PASSWORD"] == "fresh-db"
    assert parsed["OPERATOR_PASSWORD"] == "fresh-operator"
    assert parsed["CHATWOOT_UI_PASSWORD"] == "pa$sw'ord"
    assert parsed["OPENAI_API_KEY"] == "fixture-key"
    assert "# ACCESOS WEB DEL EVALUADOR" in env.read_text()
    assert env.stat().st_mode & 0o777 == 0o600
    assert report["application_restarted"] is False
    assert report["tunnel_started"] is False
    assert "fixture-key" not in str(report)


def test_live_delivery_cannot_copy_internal_secrets_or_change_payment_mode(tmp_path):
    import pytest

    from scripts.ec2_live_config import parse_delivery, provision

    env = tmp_path / ".env"
    original = "CENTRAL_DB_PASSWORD=fresh-db\nOPENAI_API_KEY=\n"
    env.write_text(original)
    for text in [
        "CENTRAL_DB_PASSWORD=forbidden\n",
        "DEMO_MODE=false\n",
        "AI_LOCAL_SPEND_LIMIT_USD=10.01\n",
        'OPENAI_API_KEY="secret-value\n',
    ]:
        with pytest.raises(ValueError) as error:
            provision(env, parse_delivery(text))
        assert "secret-value" not in str(error.value)
        assert env.read_text() == original


def test_known_delivery_ui_credentials_are_applied_before_first_database_initialization(tmp_path):
    from dotenv import dotenv_values

    from scripts.ec2_live_config import parse_delivery, provision

    env = tmp_path / ".env"
    env.write_text(
        "SESSION_SECRET=fresh-session\nCENTRAL_DB_PASSWORD=fresh-db\nOPERATOR_PASSWORD=random-op\nLANGFUSE_INIT_USER_EMAIL=random@example.test\nLANGFUSE_INIT_USER_PASSWORD=random-lf\n"
    )
    delivery = parse_delivery(
        'OPERATOR_USERNAME="evaluador"\nOPERATOR_PASSWORD="known-op"\nLANGFUSE_INIT_USER_EMAIL="evaluator@example.test"\nLANGFUSE_INIT_USER_NAME="Evaluator"\nLANGFUSE_INIT_USER_PASSWORD="known-lf"\n'
    )
    provision(env, delivery, initialized=False)
    values = dotenv_values(env)
    assert values["OPERATOR_PASSWORD"] == "known-op"
    assert values["LANGFUSE_INIT_USER_PASSWORD"] == "known-lf"
    assert values["LANGFUSE_INIT_USER_EMAIL"] == "evaluator@example.test"
    assert values["CENTRAL_DB_PASSWORD"] == "fresh-db"
    assert values["SESSION_SECRET"] == "fresh-session"


def test_existing_langfuse_initial_credentials_cannot_be_changed_or_misrepresented(tmp_path):
    import pytest

    from scripts.ec2_live_config import provision

    env = tmp_path / ".env"
    original = "LANGFUSE_INIT_USER_EMAIL=known@example.test\nLANGFUSE_INIT_USER_NAME=Evaluator\nLANGFUSE_INIT_USER_PASSWORD=known-lf\n"
    env.write_text(original)
    with pytest.raises(ValueError, match="already initialized"):
        provision(env, {"LANGFUSE_INIT_USER_PASSWORD": "different-password"}, initialized=True)
    assert env.read_text() == original
    # Supplying the same known credentials is safe and keeps re-runs usable.
    provision(env, {"LANGFUSE_INIT_USER_PASSWORD": "known-lf"}, initialized=True)
    from dotenv import dotenv_values

    assert dotenv_values(env)["LANGFUSE_INIT_USER_PASSWORD"] == "known-lf"


def test_bootstrap_provisions_delivery_before_first_compose_start(monkeypatch):
    events = []
    monkeypatch.setattr(
        ec2_emulation, "prepare_guest_environment", lambda: events.append("fresh-internal-env")
    )
    monkeypatch.setattr(
        ec2_emulation, "configure_live", lambda path: events.append(("private-delivery", path))
    )
    monkeypatch.setattr(ec2_emulation, "compose", lambda command, **kw: events.append(command))
    monkeypatch.setattr(ec2_emulation, "state", lambda: {"live_configured": True})
    monkeypatch.setattr(ec2_emulation, "write_json", lambda *args: None)
    ec2_emulation.bootstrap(".env.entrega")
    assert events[:3] == [
        "fresh-internal-env",
        ("private-delivery", ".env.entrega"),
        "up -d --build --wait --wait-timeout 600",
    ]


def test_initialized_detection_includes_retained_database_volumes(monkeypatch):
    from scripts import ec2_live_config

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=b"" if command[1] == "ps" else b"retained-langfuse-db\n", stderr=b""
        )

    monkeypatch.setattr(ec2_live_config.subprocess, "run", fake_run)
    assert ec2_live_config.runtime_initialized() is True
    assert len(calls) == 2
    assert all(
        command[-1] == "label=com.docker.compose.project=agil-ec2-fixture" for command in calls
    )


def test_public_startup_requires_read_only_preflight_success(monkeypatch, tmp_path):
    import json

    import pytest

    monkeypatch.setattr(ec2_emulation, "LOCAL", tmp_path)
    monkeypatch.setattr(
        ec2_emulation, "state", lambda: {"live_configured": True, "live_applied": True}
    )
    for report in [
        {"status": "failed", "inference_opt_in": False, "channel_writes": 0},
        {"status": "ok", "inference_opt_in": True, "channel_writes": 0},
        {"status": "ok", "inference_opt_in": False, "channel_writes": 1},
    ]:
        calls = []

        def fake_compose(command, report=report, calls=calls, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(
                [], 0, stdout=json.dumps(report).encode(), stderr=b""
            )

        monkeypatch.setattr(ec2_emulation, "compose", fake_compose)
        with pytest.raises(RuntimeError):
            ec2_emulation.start_public()
        assert len(calls) == 1 and "--live-inference" not in calls[0]
    calls = []

    def successful_compose(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            [], 0, stdout=b'{"status":"ok","inference_opt_in":false,"channel_writes":0}', stderr=b""
        )

    monkeypatch.setattr(ec2_emulation, "compose", successful_compose)
    ec2_emulation.start_public()
    assert calls[-1] == "--profile public up -d --no-deps cloudflared"
    assert len(calls) == 2


def test_stop_targets_only_the_recorded_ec2_instance_and_preserves_storage(monkeypatch):
    events = []

    class Client:
        def stop_instances(self, **kwargs):
            events.append(("stop", kwargs))

        def get_waiter(self, name):
            assert name == "instance_stopped"
            return self

        def wait(self, **kwargs):
            events.append(("wait", kwargs))

    monkeypatch.setattr(ec2_emulation, "state", lambda: {"instance_id": "i-private-fixture"})
    monkeypatch.setattr(ec2_emulation, "ec2", lambda: Client())
    monkeypatch.setattr(ec2_emulation, "close_access", lambda: events.append("close-forwards"))
    ec2_emulation.stop()
    assert events[0] == ("stop", {"InstanceIds": ["i-private-fixture"]})
    assert events[1][1]["InstanceIds"] == ["i-private-fixture"]
    assert events[-1] == "close-forwards"


def test_delivery_up_starts_public_connector_only_with_explicit_flag(monkeypatch):
    events = []
    monkeypatch.setattr(
        ec2_emulation, "load_delivery", lambda path: events.append(("validate-explicit", path))
    )
    monkeypatch.setattr(ec2_emulation, "create", lambda: events.append("create"))
    monkeypatch.setattr(ec2_emulation, "bootstrap", lambda path: events.append(("bootstrap", path)))
    monkeypatch.setattr(ec2_emulation, "verify", lambda: events.append("health"))
    monkeypatch.setattr(ec2_emulation, "access", lambda: events.append("local-access"))
    monkeypatch.setattr(
        ec2_emulation, "start_public", lambda: events.append("preflight-and-public")
    )
    ec2_emulation.up(".env.entrega")
    assert "preflight-and-public" not in events
    events.clear()
    ec2_emulation.up(".env.entrega", public=True)
    assert events[0] == ("validate-explicit", ".env.entrega")
    assert events[-1] == "preflight-and-public"


def test_guest_environment_codec_preserves_backslashes_quotes_and_literal_dollars():
    from scripts.ec2_live_config import parse_delivery, quote_env, read_environment

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
    for value in values:
        encoded = quote_env(value)
        assert (
            read_environment("CHATWOOT_UI_PASSWORD=" + encoded + "\n")["CHATWOOT_UI_PASSWORD"]
            == value
        )
    assert quote_env(r"a\b") == "'a\\b'"
    # A caller's explicit single-quoted delivery follows Compose literal rules,
    # rather than Python's interpretation of backspace/newline escapes.
    assert parse_delivery("CHATWOOT_UI_PASSWORD='a\\b\\n'\n")["CHATWOOT_UI_PASSWORD"] == r"a\b\n"
