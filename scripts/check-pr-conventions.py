"""Validate PR metadata without interpolating untrusted text into shell commands."""

import json
import os
import re
from pathlib import Path

TITLE = re.compile(
    r"^(feat|fix|docs|refactor|test|build|ci|chore|perf|revert)(\([a-z0-9-]+\))?!?: .+\S$"
)
BRANCH = re.compile(
    r"^(feat|fix|docs|refactor|test|build|ci|chore|perf|revert)/[a-z0-9]+(?:[/-][a-z0-9]+)*$"
)


def validate(title, branch):
    errors = []
    if not TITLE.fullmatch(title):
        errors.append("Use a conventional PR title: feat(scope): meaningful summary")
    if not BRANCH.fullmatch(branch):
        errors.append(
            "Use a topic branch: feat/short-description (or fix/docs/test/ci/...)"
        )
    return errors


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    errors = validate(pr["title"], pr["head"]["ref"])
    if errors:
        raise SystemExit("\n".join(errors))
