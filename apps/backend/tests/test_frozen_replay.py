"""Provider-boundary contract tests use controlled data, not acceptance evidence."""
import argparse
import json

import pytest

from email_agentic.agents.contracts import Draft
from evals.runner.replay import ProviderTape, digest, generate, run


def inputs():
    return {"run": {"id": "controlled", "company_name": "Example", "domain": "example.com",
                    "context": "Discuss workflow", "source_email": "Original inbound message"},
            "evidence": [{"url": "https://example.com/page", "content": "Controlled source"}],
            "branches": []}


class ControlledProvider:
    async def structured(self, *args):
        return Draft(markdown="Controlled [source](https://example.com/page)",
                     email_subject="Discussion", email_body="What is the priority?")


async def test_real_prompt_construction_replays_and_rejects_prompt_drift():
    data = inputs()
    tape = ProviderTape(delegate=ControlledProvider(), model="controlled-model")
    as_of = "2026-10-29T10:00:00+00:00"
    expected = await generate(data, tape, as_of)
    document = {"model": tape.model, "calls": tape.calls}
    assert await generate(data, ProviderTape(document=document), as_of) == expected
    data["run"]["source_email"] = "Changed inbound"
    with pytest.raises(ValueError, match="request drift"):
        await generate(data, ProviderTape(document=document), as_of)


async def test_replay_rejects_unconsumed_calls_and_schema_errors():
    data = inputs()
    tape = ProviderTape(delegate=ControlledProvider(), model="controlled-model")
    await generate(data, tape, "2026-10-29T10:00:00+00:00")
    document = {"model": tape.model, "calls": tape.calls * 2}
    with pytest.raises(ValueError, match="fully consumed"):
        await generate(data, ProviderTape(document=document), "2026-10-29T10:00:00+00:00")
    document["calls"] = [dict(tape.calls[0], response={"markdown": "missing fields"})]
    with pytest.raises(ValueError):
        await generate(data, ProviderTape(document=document), "2026-10-29T10:00:00+00:00")


async def test_cli_replay_is_offline_and_binds_source_input_and_cassette(tmp_path, monkeypatch):
    import httpx

    def network_forbidden(*args, **kwargs):
        raise AssertionError("Replay must never create a network client")

    data = inputs()
    tape = ProviderTape(delegate=ControlledProvider(), model="controlled-model")
    as_of = "2026-10-29T10:00:00+00:00"
    result = await generate(data, tape, as_of)
    document = {"version": 1, "scope": "report_generation_structured_provider", "as_of": as_of,
                "model": tape.model, "calls": tape.calls, "inputs": data,
                "input_sha256": digest(data), "generation_sha256": digest(result)}
    document["sha256"] = digest(document)
    source, cassette, output = (tmp_path / name for name in ("input.json", "cassette.json", "output.json"))
    source.write_text(json.dumps(data))
    cassette.write_text(json.dumps(document))
    args = argparse.Namespace(command="replay", input=source, cassette=cassette, output=output)
    monkeypatch.setattr(httpx, "AsyncClient", network_forbidden)
    await run(args)
    assert json.loads(output.read_text())["generation_sha256"] == digest(result)
    output.unlink()
    data["run"]["source_email"] = "changed"
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source input drift"):
        await run(args)
    source.write_text(json.dumps(document["inputs"]))
    document["calls"][0]["response"]["markdown"] = "tampered"
    cassette.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="checksum"):
        await run(args)
