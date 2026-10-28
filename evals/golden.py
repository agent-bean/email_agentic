"""Offline-only golden authoring and locking. Never imported by application runtime."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    statement: str = Field(min_length=5)
    important: bool = True
    source_file: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    locator: str = Field(min_length=1)


class Golden(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^TC-0[1-6]$")
    version: str
    company_name: str
    domain: str
    reference_time: datetime
    source_mode: str = Field(pattern=r"^(frozen|live)$")
    status: str = Field(pattern=r"^(draft|reviewed|locked)$")
    reviewer: str | None = None
    facts: list[Fact] = Field(default_factory=list)
    readiness_checklist: list[str] = Field(default_factory=list)

    @field_validator("reference_time")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Reference time must include a timezone")
        return value


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_sources(golden, directory):
    if not golden.facts or not golden.readiness_checklist or not golden.reviewer:
        raise ValueError("Facts, readiness checklist and human reviewer are required")
    if len({fact.id for fact in golden.facts}) != len(golden.facts):
        raise ValueError("Duplicate fact IDs")
    for fact in golden.facts:
        path = (directory / fact.source_file).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(
                "Source must be an existing file inside the private golden directory"
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != fact.source_sha256:
            raise ValueError("Source snapshot checksum changed")


def load_locked(path):
    document = json.loads(path.read_text())
    golden = Golden.model_validate(document["golden"])
    if golden.status != "locked" or document.get("sha256") != digest(
        document["golden"]
    ):
        raise ValueError("Golden is not locked or has changed")
    if document.get("review_sha256") != digest(
        {**document["golden"], "status": "reviewed"}
    ):
        raise ValueError("Golden changed after review")
    validate_sources(golden, path.parent)
    return golden, document["sha256"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["draft", "review", "lock", "verify"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--case", default="TC-01")
    parser.add_argument("--reviewer")
    parser.add_argument("--company")
    parser.add_argument("--domain")
    parser.add_argument("--source-mode", choices=["frozen", "live"], default="live")
    args = parser.parse_args()
    if args.command == "draft":
        if args.path.exists():
            raise SystemExit("Refusing to overwrite a dataset")
        args.path.parent.mkdir(parents=True, exist_ok=True)
        if not args.company or not args.domain:
            raise SystemExit("Draft requires --company and --domain")
        golden = Golden(
            case_id=args.case,
            version="1",
            company_name=args.company,
            domain=args.domain,
            reference_time=datetime.now(UTC),
            source_mode=args.source_mode,
            status="draft",
        )
        args.path.write_text(
            json.dumps(
                {"golden": golden.model_dump(mode="json")}, ensure_ascii=False, indent=2
            )
            + "\n"
        )
    elif args.command == "verify":
        load_locked(args.path)
    else:
        document = json.loads(args.path.read_text())
        golden = Golden.model_validate(document["golden"])
        if args.command == "review":
            if golden.status != "draft" or not args.reviewer:
                raise SystemExit(
                    "Review needs a draft and an identified human reviewer"
                )
            golden.reviewer = args.reviewer
            validate_sources(golden, args.path.parent)
            golden.status = "reviewed"
        else:
            if golden.status != "reviewed":
                raise SystemExit("Only a reviewed golden can be locked")
            if document.get("review_sha256") != digest(golden.model_dump(mode="json")):
                raise SystemExit(
                    "Golden changed after review; create a new draft for review"
                )
            validate_sources(golden, args.path.parent)
            golden.status = "locked"
        review_sha = (
            digest(golden.model_dump(mode="json"))
            if golden.status == "reviewed"
            else document["review_sha256"]
        )
        document = {
            "golden": golden.model_dump(mode="json"),
            "review_sha256": review_sha,
        }
        if golden.status == "locked":
            document["sha256"] = digest(document["golden"])
        args.path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print("Golden operation completed")


if __name__ == "__main__":
    main()
