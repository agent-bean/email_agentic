"""Offline runner exports output only; it never sends golden data to the application."""

import argparse
import json
from pathlib import Path

import httpx

from evals.golden import load_locked
from evals.scoring.score import score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Exported run JSON, or path to save an API export",
    )
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument(
        "--api", help="Optional loopback API base URL for fetching an existing run"
    )
    parser.add_argument("--run-id")
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    golden, sha = load_locked(args.golden)
    case = json.loads(args.case.read_text())
    if case.get("fixture_status") in {"requires_fixture_binding", "requires_case_source"}:
        raise SystemExit("Use the effective *-input.json exported by the collector to score bound cases")
    if (
        case["case_id"],
        case["dataset_version"],
        case["source_mode"],
        case["input"]["domain"],
        case["input"]["company_name"],
    ) != (
        golden.case_id,
        golden.version,
        golden.source_mode,
        golden.domain,
        golden.company_name,
    ):
        raise SystemExit("Case and locked golden do not match")
    if not set(case["required_checks"]).issubset(golden.readiness_checklist):
        raise SystemExit("Golden omits required case checks")
    if args.api:
        url = httpx.URL(args.api)
        if url.host not in {"127.0.0.1", "localhost", "::1"} or not args.run_id:
            raise SystemExit("API export requires a loopback URL and --run-id")
        response = httpx.get(
            args.api.rstrip("/") + "/api/v1/runs/" + args.run_id, timeout=30
        )
        response.raise_for_status()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(response.json(), ensure_ascii=False, indent=2) + "\n"
        )
    output = json.loads(args.output.read_text())
    review = json.loads(args.review.read_text()) if args.review else None
    if any(
        output.get("run", {}).get(key, "") != value
        for key, value in case["input"].items()
    ):
        raise SystemExit("Run input does not match case")
    result = score(output, golden, sha, review)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Evaluation recorded; eligible=" + str(result["eligible"]).lower())


if __name__ == "__main__":
    main()
