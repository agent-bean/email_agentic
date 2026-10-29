"""Private, offline report-generation replay at the structured provider boundary.

No golden is read. Source gathering is a frozen input, not a replayed workflow.
"""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def generation_input(export):
    return {key: export[key] for key in ("run", "evidence", "branches")}


class ProviderTape:
    def __init__(self, document=None, delegate=None, model=None):
        self.document = document
        self.delegate = delegate
        self.model = model if delegate else document["model"]
        self.calls = []
        self.position = 0

    async def structured(self, run_id, schema, system, payload):
        request = {"model": self.model, "schema": schema.model_json_schema(),
                   "system": system, "payload": payload}
        request_sha = digest(request)
        if self.delegate:
            result = await self.delegate.structured(run_id, schema, system, payload)
            self.calls.append({"request_sha256": request_sha,
                               "response": result.model_dump(mode="json")})
            return result
        calls = self.document["calls"]
        if self.position >= len(calls) or calls[self.position]["request_sha256"] != request_sha:
            raise ValueError("Frozen provider request drift; refusing network fallback")
        call = calls[self.position]
        self.position += 1
        return schema.model_validate(call["response"])

    def assert_consumed(self):
        if not self.delegate and self.position != len(self.document["calls"]):
            raise ValueError("Frozen provider calls were not fully consumed")


async def generate(inputs, tape, as_of):
    from email_agentic.agents.report_generation import ReportGenerationAgent
    from email_agentic.workflows.research import cited_urls

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(as_of).astimezone(tz)

    with patch("email_agentic.agents.report_generation.datetime", FrozenDateTime):
        agent = ReportGenerationAgent(tape)
        draft = await agent.run(inputs["run"], inputs["evidence"], inputs["branches"])
        known = {item["url"] for item in inputs["evidence"]}
        if cited_urls(draft.markdown + "\n" + draft.email_body) - known:
            draft = await agent.run(inputs["run"], inputs["evidence"], inputs["branches"], previous_draft=draft)
        if cited_urls(draft.markdown + "\n" + draft.email_body) - known:
            raise ValueError("Generated report contains unsupported URLs")
    tape.assert_consumed()
    return draft.model_dump(mode="json")


class UsageJournal:
    """Persist real integration usage receipts without an application database."""

    def __init__(self):
        self.receipts = []

    async def execute(self, query, values):
        if not query.startswith("INSERT INTO model_usage("):
            raise ValueError("Replay harness only accepts model usage receipts")
        _, run_id, model, input_tokens, output_tokens, input_id = values
        self.receipts.append({"run_id": str(run_id), "model": model,
                              "input_tokens": input_tokens, "output_tokens": output_tokens,
                              "input_id": input_id})


async def run(args):
    if args.output.exists() or (args.command == "record" and args.cassette.exists()):
        raise ValueError("Refusing to overwrite private replay evidence")
    inputs = generation_input(json.loads(args.input.read_text()))
    if args.command == "record":
        import httpx
        from email_agentic.integrations.llm import LLM
        from email_agentic.platform.config import get_settings

        settings = get_settings()
        journal = UsageJournal()
        as_of = datetime.now(UTC).isoformat()
        async with httpx.AsyncClient() as client:
            tape = ProviderTape(delegate=LLM(journal, settings, client), model=settings.llm_model)
            result = await generate(inputs, tape, as_of)
        document = {"version": 1, "scope": "report_generation_structured_provider",
                    "as_of": as_of, "model": settings.llm_model,
                    "input_sha256": digest(inputs), "inputs": inputs,
                    "calls": tape.calls, "generation_sha256": digest(result),
                    "usage": journal.receipts}
        document["sha256"] = digest(document)
        write_private(args.cassette, document)
    else:
        document = json.loads(args.cassette.read_text())
        body = {key: value for key, value in document.items() if key != "sha256"}
        if document.get("version") != 1 or document.get("sha256") != digest(body):
            raise ValueError("Frozen provider cassette checksum changed")
        if digest(inputs) != document["input_sha256"] or inputs != document["inputs"]:
            raise ValueError("Frozen source input drift")
        # Replay constructs neither HTTP client nor live provider and has no fallback.
        tape = ProviderTape(document=document)
        result = await generate(inputs, tape, document["as_of"])
        if digest(result) != document["generation_sha256"]:
            raise ValueError("Frozen generation changed")
    write_private(args.output, {"scope": document["scope"], "mode": args.command,
                               "input_sha256": digest(inputs), "cassette_sha256": document["sha256"],
                               "generation_sha256": digest(result), "draft": result,
                               "factual_accuracy": "not_evaluated", "product_acceptance": "not_evaluated",
                               "collection_replay": "not_evaluated"})
    print("Report generation completed; mode=" + args.command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["record", "replay"])
    parser.add_argument("--input", type=Path, required=True, help="Private run/evidence/branches export")
    parser.add_argument("--cassette", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
