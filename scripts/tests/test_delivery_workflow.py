"""Exercise local branch guards and mutual exclusion of production operations."""

import fcntl
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pr_conventions", ROOT / "scripts/check-pr-conventions.py"
)
conventions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conventions)

app_spec = importlib.util.spec_from_file_location("app_control", ROOT / "scripts/app-control.py")
app_control = importlib.util.module_from_spec(app_spec)
app_spec.loader.exec_module(app_control)


@pytest.mark.parametrize("mode", ["test", "web-test"])
def test_db_test_routes_prepare_database_before_running(mode, tmp_path, monkeypatch):
    monkeypatch.setattr(app_control, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["app-control.py", mode])
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-password/@")
    monkeypatch.setenv("TEST_DATABASE_URL", "ignored-ambient-url")
    calls = []

    def run(command, **kwargs):
        calls.append((command, {**kwargs, "env": dict(kwargs["env"])}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app_control.subprocess, "run", run)
    with pytest.raises(SystemExit) as result:
        app_control.main()
    assert result.value.code == 0
    assert len(calls) == 4
    assert calls[0][0][-3:] == ["run", "--rm", "migrate"]
    assert calls[1][0][-3:-1] == ["python", "-c"]
    assert calls[2][0][-3:] == ["--env", "DATABASE_URL", "migrate"]
    assert all(options["check"] for _, options in calls[:3])
    command, options = calls[3]
    assert "DATABASE_URL" not in options["env"]
    assert options["env"]["TEST_DATABASE_URL"] == (
        "postgresql://email_agentic:test-password%2F%40@127.0.0.1:5432/email_agentic_test"
    )
    if mode == "web-test":
        assert command == ["npm", "run", "test:e2e", "--prefix", "apps/web"]
    else:
        assert command[-1] == "--require-database"


def test_web_tests_do_not_start_after_backup_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(app_control, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["app-control.py", "web-test"])
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(app_control.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        app_control.main()
    assert len(calls) == 1
    assert calls[0][-1] == "migrate"


@pytest.mark.parametrize("target,allowed", [("main", False), ("feat/tests", True)])
def test_pre_push_checks_remote_destination(target, allowed):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/git-hooks/pre-push")],
        input=f"refs/heads/feature {'a' * 40} refs/heads/{target} {'b' * 40}\n",
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) is allowed


def test_conventional_metadata():
    assert conventions.validate("feat(web): add review flow", "feat/review-flow") == []
    assert conventions.validate("update stuff", "main")


def test_deploy_and_retention_share_exclusive_lock(tmp_path):
    blocks = []
    for name in ("deploy-production.sh", "retention-production.sh"):
        source = (ROOT / "scripts" / name).read_text()
        blocks.append(re.search(r"exec 9>([^\n]+)\nflock -n 9[^\n]+", source))
    assert all(blocks)
    assert blocks[0][1] == blocks[1][1]
    lock = tmp_path / "operation.lock"
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for block in blocks:
            result = subprocess.run(
                ["bash", "-c", block[0].replace(block[1], str(lock))],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 1
    result = subprocess.run(
        ["bash", "-c", blocks[1][0].replace(blocks[1][1], str(lock))],
        capture_output=True,
    )
    assert result.returncode == 0


def test_hook_installer_preserves_existing_configuration(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    installer = scripts / "install-git-hooks.py"
    installer.write_bytes((ROOT / "scripts/install-git-hooks.py").read_bytes())
    subprocess.run(
        ["git", "config", "core.hooksPath", "custom-hooks"], cwd=tmp_path, check=True
    )
    result = subprocess.run([sys.executable, str(installer)], capture_output=True)
    assert result.returncode != 0
    assert (
        subprocess.check_output(
            ["git", "config", "core.hooksPath"], cwd=tmp_path
        ).strip()
        == b"custom-hooks"
    )
