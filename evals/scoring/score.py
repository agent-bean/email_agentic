import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from evals.golden import canonical


def normalize(value):
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            parts.query,
            "",
        )
    )


def source_links(text):
    # Independent evaluator: inspect all written links, including plain URLs in email.
    links = set()
    for value in re.findall(r'https?://[^\s<>\]"\x27]+', text):
        value = value.rstrip(".,;:!?。")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        links.add(normalize(value))
    return links


def prd_elapsed(run, report):
    """Recompute acceptance latency from timestamps, independently of runtime totals."""
    timing = run.get("config", {}).get("timing") or {}
    if timing.get("version") != 1:
        return None, None
    try:
        received, waiting, confirmed = (
            datetime.fromisoformat(timing[key])
            for key in ("received_at", "identity_wait_started_at", "identity_confirmed_at")
        )
        ready = datetime.fromisoformat(report.get("quality", {})["markdown_ready_at"])
        if any(value.tzinfo is None for value in (received, waiting, confirmed, ready)):
            return None, None
        if not received <= waiting <= confirmed <= ready:
            return None, None
    except (KeyError, TypeError, ValueError):
        return None, None
    excluded = (confirmed - waiting).total_seconds()
    return (ready - received).total_seconds() - excluded, excluded


def score(output, golden, golden_sha, review=None):
    output_sha = hashlib.sha256(canonical(output)).hexdigest()
    reports = output.get("reports", [])
    if not reports:
        return {"eligible": False, "reason": "No report", "output_sha256": output_sha}
    run = output["run"]
    if (
        run.get("domain") != golden.domain
        or run.get("company_name") != golden.company_name
    ):
        return {
            "eligible": False,
            "reason": "Run does not match golden company/domain",
            "output_sha256": output_sha,
        }
    if golden.source_mode == "frozen":
        return {
            "eligible": False,
            "reason": "Frozen full-workflow scoring is unavailable; report-generation provider replay alone is not product acceptance",
            "output_sha256": output_sha,
        }
    report = reports[0]
    citations = source_links(report["markdown"])
    all_links = citations | source_links(report.get("email_body", ""))
    evidence = {normalize(item["url"]): item for item in output.get("evidence", [])}
    supported = citations & evidence.keys()
    run = output["run"]
    measured, identity_wait = prd_elapsed(run, report)
    target = run["config"]["target_seconds"]
    time_target_met = measured <= target if measured is not None else None
    reference = (
        datetime.fromisoformat(run["created_at"])
        if golden.source_mode == "live"
        else golden.reference_time
    )
    dated = []
    for url in supported:
        value = evidence[url].get("published_at")
        if value:
            published = datetime.fromisoformat(value)
            if published.tzinfo is None:
                continue
            if timedelta(0) <= reference - published <= timedelta(days=30):
                dated.append(url)
    valid_review = bool(
        review
        and review.get("reviewer")
        and review.get("reviewer_kind", "human") == "human"
        and review.get("output_sha256") == output_sha
        and review.get("golden_sha256") == golden_sha
    )
    verdicts = review.get("facts", {}) if valid_review else {}
    complete = sum(
        verdicts.get(fact.id) == "correct_with_evidence" for fact in golden.facts
    )
    critical_ok = all(
        verdicts.get(fact.id) == "correct_with_evidence"
        for fact in golden.facts
        if fact.important
    )
    readiness = (
        all(
            review.get("readiness", {}).get(item) is True
            for item in golden.readiness_checklist
        )
        if valid_review
        else False
    )
    eligible = valid_review and set(verdicts) == {fact.id for fact in golden.facts}
    passed = bool(
        eligible
        and complete / len(golden.facts) >= 0.98
        and critical_ok
        and readiness
        and len(supported) >= 12
        and not all_links - evidence.keys()
        and review.get("distinct_sources_verified") is True
        and review.get("news_freshness_passed") is True
        and time_target_met is True
    )
    return {
        "eligible": eligible,
        "passed": passed,
        "source_mode": golden.source_mode,
        "output_sha256": output_sha,
        "golden_sha256": golden_sha,
        "completeness": complete / len(golden.facts) if eligible else None,
        "critical_facts_passed": critical_ok if eligible else None,
        "readiness": readiness if eligible else None,
        "cited_supported_urls": len(supported),
        "unsupported_urls": sorted(all_links - evidence.keys()),
        "source_target_met": len(supported) >= 12
        and bool(valid_review and review.get("distinct_sources_verified")),
        "recent_dated_sources": len(dated),
        "news_freshness_passed": review.get("news_freshness_passed")
        if valid_review
        else None,
        "elapsed_seconds": run.get("elapsed_seconds"),
        "timing_basis": report.get("quality", {}).get("timing_basis"),
        "prd_elapsed_seconds": measured,
        "prd_timing_basis": "received_to_markdown_excluding_identity_wait",
        "identity_wait_seconds": identity_wait,
        "target_seconds": target,
        "time_target_met": time_target_met,
        "note": "URL count, provider dates and string structure alone do not establish factual accuracy, independent sources or news freshness. Active processing time cannot establish PRD latency.",
    }
