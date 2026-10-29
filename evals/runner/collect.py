"""Collect live research drafts for review without approving or publishing them."""

import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path

import httpx


def save_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def collect(client, case, output, confirm_identities, wait_seconds):
    response = client.post("/api/v1/runs", json=case["input"],
                           headers={"Idempotency-Key": f"eval:{case['case_id']}:{uuid.uuid4()}"})
    response.raise_for_status()
    run_id = response.json()["id"]
    record = {"case_id": case["case_id"], "run_id": run_id, "status": "queued"}
    save_private(output / f"{case['case_id'].lower()}-collection.json", record)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        response.raise_for_status()
        detail = response.json()
        record["status"] = detail["run"]["status"]
        if record["status"] == "awaiting_identity":
            if not confirm_identities:
                break
            response = client.post(f"/api/v1/runs/{run_id}/identity",
                                   json={"version": detail["run"]["version"]})
            response.raise_for_status()
        elif detail["reports"] or record["status"] == "failed":
            assert not detail["actions"], "Unexpected publication action"
            assert all(not report["send_email"] and not report["save_kb"] for report in detail["reports"])
            break
        time.sleep(1)
    else:
        record["collection_error"] = "wait_timeout"
    target = output / f"{case['case_id'].lower()}-output.json"
    save_private(target, detail)
    record["output"] = str(target)
    record["output_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    record["quality"] = detail["reports"][0]["quality"] if detail["reports"] else None
    save_private(output / f"{case['case_id'].lower()}-collection.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--case", type=Path, action="append", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-identities", action="store_true",
                        help="Explicitly confirm the company identities specified by the selected cases")
    parser.add_argument("--wait-seconds", type=float, default=600)
    args = parser.parse_args()
    url = httpx.URL(args.api)
    if url.host not in {"127.0.0.1", "localhost", "::1"} or args.wait_seconds <= 0:
        parser.error("Use a loopback API and a positive wait budget")
    results = []
    with httpx.Client(base_url=args.api, headers={"Origin": args.api}, timeout=30) as client:
        for path in args.case:
            case = json.loads(path.read_text())
            record = collect(client, case, args.output_directory, args.confirm_identities, args.wait_seconds)
            results.append(record)
            save_private(args.output_directory / "manifest.json", {"runs": results, "human_review": "pending"})
            print(f"{case['case_id']}: {record['status']}", flush=True)


if __name__ == "__main__":
    main()
