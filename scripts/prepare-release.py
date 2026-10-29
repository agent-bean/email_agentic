"""Package deployment source from a clean Git commit, excluding private/runtime files."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    "apps/backend",
    "apps/web",
    "infra",
    "scripts/backup-production.sh",
    "scripts/retention-production.sh",
    ".dockerignore",
)


def prepare(root, output):
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    ).strip():
        raise SystemExit(
            "Commit or preserve pending changes before preparing a release"
        )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    source = subprocess.check_output(
        ["git", "archive", "--format=tar", revision, "--", *INPUTS], cwd=root
    )
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle_path = output / f"email-agentic-{revision}.tar.gz"
    if bundle_path.exists():
        raise SystemExit(
            "Release archive already exists; preserve it and use another output directory"
        )
    with tarfile.open(fileobj=io.BytesIO(source)) as archive:
        members = archive.getmembers()
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or any(
                    part in {"node_modules", "private"}
                    or (part.startswith(".") and part != ".dockerignore")
                    for part in path.parts
                )
            ):
                raise SystemExit(
                    "Unsafe or private file in release inputs; no archive created"
                )
        with bundle_path.open("xb") as stream:
            bundle_path.chmod(0o600)
            with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
                for member in members:
                    bundle.addfile(
                        member, archive.extractfile(member) if member.isfile() else None
                    )
                metadata = tarfile.TarInfo(".release-id")
                content = (revision + "\n").encode()
                metadata.size, metadata.mode = len(content), 0o644
                bundle.addfile(metadata, io.BytesIO(content))
    digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    manifest = bundle_path.with_suffix(bundle_path.suffix + ".json")
    manifest.write_text(
        json.dumps(
            {"revision": revision, "archive": bundle_path.name, "sha256": digest},
            indent=2,
        )
        + "\n"
    )
    manifest.chmod(0o600)
    print(f"Prepared {bundle_path.name}; checksum recorded in {manifest.name}")
    return bundle_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/releases")
    args = parser.parse_args()
    prepare(ROOT, args.output.resolve())


if __name__ == "__main__":
    main()
