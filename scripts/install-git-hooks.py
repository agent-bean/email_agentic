"""Opt into local hooks while preserving existing user hook configuration."""

import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if configured == "scripts/git-hooks":
        print("Repository hooks already enabled")
        return
    if configured:
        raise SystemExit(
            "Existing core.hooksPath preserved; integrate the pre-push guard manually"
        )
    hooks = subprocess.check_output(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=root,
        text=True,
    ).strip()
    hook_path = Path(hooks)
    if not hook_path.is_absolute():
        hook_path = root / hook_path
    if hook_path.exists() and any(
        p.is_file() and not p.name.endswith(".sample") for p in hook_path.iterdir()
    ):
        raise SystemExit(
            "Existing Git hooks preserved; integrate the pre-push guard manually"
        )
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", "scripts/git-hooks"],
        cwd=root,
        check=True,
    )
    print("Repository pre-push guard enabled for this checkout")


if __name__ == "__main__":
    main()
