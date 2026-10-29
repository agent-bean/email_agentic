"""Verify uploaded scripts cannot be consumed by a command reading stdin."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('vps_ssh', Path(__file__).parents[1] / 'vps-ssh.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_stdin_reader_preserves_remaining_commands(tmp_path):
    result = subprocess.run(
        [sys.executable, '-c', module.SCRIPT_DRIVER],
        input=b'cat >/dev/null\nprintf "finished"\n', capture_output=True,
        env={**os.environ, 'TMPDIR': str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout == b'finished'
    assert list(tmp_path.iterdir()) == []


def test_failure_is_propagated_and_script_removed(tmp_path):
    result = subprocess.run(
        [sys.executable, '-c', module.SCRIPT_DRIVER],
        input=b'exit 23\nprintf "unreachable"\n', capture_output=True,
        env={**os.environ, 'TMPDIR': str(tmp_path)},
    )
    assert result.returncode == 23
    assert result.stdout == b''
    assert list(tmp_path.iterdir()) == []
