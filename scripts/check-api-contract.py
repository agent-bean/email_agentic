"""Generate or verify web contracts from OpenAPI without loading runtime settings."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from email_agentic.main import create_app
from email_agentic.platform.config import Settings


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "apps/web/src/lib/api-schema.ts"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the committed types have drifted")
    args = parser.parse_args()
    # model_construct uses declared defaults only: no dotenv, credentials, DB or lifespan.
    app = create_app(Settings.model_construct(environment="test"))
    with tempfile.TemporaryDirectory(prefix="email-api-contract-") as directory:
        schema = Path(directory) / "openapi.json"
        generated = Path(directory) / "api-schema.ts"
        schema.write_text(json.dumps(app.openapi(), sort_keys=True), encoding="utf-8")
        subprocess.run(
            [str(ROOT / "apps/web/node_modules/.bin/openapi-typescript"), str(schema), "-o", str(generated)],
            cwd=ROOT, check=True,
        )
        content = generated.read_bytes()
    if args.check:
        if not TARGET.exists() or TARGET.read_bytes() != content:
            raise SystemExit("API contracts changed. Run make api-generate and commit the generated types.")
        print("API contracts match the backend OpenAPI schema.")
        return

    TARGET.write_bytes(content)
    print("Generated web API contracts.")


if __name__ == "__main__":
    main()
