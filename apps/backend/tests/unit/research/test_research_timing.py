
import pytest


def test_prd_timing_includes_queues_and_excludes_identity_wait():
    from datetime import datetime, UTC
    from email_agentic.workflows.research import prd_timing

    run = {"identity_confirmed": True, "config": {"target_seconds": 42, "timing": {
        "version": 1,
        "received_at": "2026-10-29T08:00:00+00:00",
        "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
        "identity_confirmed_at": "2026-10-30T08:00:08+00:00",
    }}}
    # Eight seconds initial queue, ten after confirmation, thirty processing.
    quality = prd_timing(run, datetime(2026, 10, 30, 8, 0, 48, tzinfo=UTC))
    assert quality["prd_elapsed_seconds"] == 48
    assert quality["identity_wait_seconds"] == 86400
    assert quality["prd_time_target_met"] is False


@pytest.mark.parametrize("timing", [
    {}, {"version": 1},
    {"version": 1, "received_at": "2026-10-29T08:00:00+00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00"},
    {"version": 1, "received_at": "2026-10-29T08:00:00+00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
     "identity_confirmed_at": "2026-10-29T08:00:07+00:00"},
    {"version": 1, "received_at": "2026-10-29T08:00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
     "identity_confirmed_at": "2026-10-29T08:00:09+00:00"},
])
def test_prd_timing_does_not_claim_legacy_or_incomplete_wait(timing):
    from datetime import datetime, UTC
    from email_agentic.workflows.research import prd_timing

    result = prd_timing({"identity_confirmed": True,
                         "config": {"target_seconds": 42, "timing": timing}}, datetime.now(UTC))
    assert result["prd_elapsed_seconds"] is None
    assert result["prd_time_target_met"] is None
