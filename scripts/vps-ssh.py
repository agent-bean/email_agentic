"""Run a command or a local shell script through the configured VPS SSH key."""
import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Buffer the script before execution so commands reading stdin cannot consume it.
SCRIPT_DRIVER = """import os, subprocess, sys, tempfile
with tempfile.NamedTemporaryFile(prefix='email-agentic-ssh-', delete=False) as script:
    path = script.name
    script.write(sys.stdin.buffer.read())
try:
    result = subprocess.run(['bash', '-e', path], stdin=subprocess.DEVNULL)
finally:
    os.unlink(path)
sys.exit(result.returncode)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', help='Override configured SSH user for migration checks.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--command')
    group.add_argument('--script', type=Path)
    args = parser.parse_args()
    key = (ROOT / os.environ['VPS_SSH_KEY_FILE']).resolve()
    port = str(int(os.environ.get('VPS_SSH_PORT', '22')))
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'ConnectTimeout=12', '-o', 'ConnectionAttempts=1',
               '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3',
               '-o', 'StrictHostKeyChecking=yes',
               '-o', f'UserKnownHostsFile={ROOT / ".runtime/ssh-known-hosts"} {Path.home() / ".ssh/known_hosts"}',
               '-p', port, '-i', str(key),
               (args.user or os.environ['VPS_SSH_USER']) + '@' + os.environ['VPS_HOST'],
               'python3 -c ' + shlex.quote(SCRIPT_DRIVER) if args.script else args.command]
    result = subprocess.run(command, input=args.script.read_bytes() if args.script else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1500)
    sys.stdout.buffer.write(result.stdout)
    if result.returncode:
        # Avoid printing destination addresses or arbitrary provider diagnostics.
        reason = 'authentication' if b'Permission denied' in result.stderr else 'timeout' if b'timed out' in result.stderr else 'remote command or connection'
        print(f'SSH failed: {reason}; exit={result.returncode}', file=sys.stderr)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
