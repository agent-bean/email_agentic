import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from evals.golden import canonical


def normalize(value):
    parts = urlsplit(value)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            parts.query,
            "",
        )
    )


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
            "reason": "Frozen provider replay is not implemented; live output cannot count as regression evidence",
            "output_sha256": output_sha,
        }
    report = reports[0]
    citations = {
        normalize(url)
        for url in re.findall(r"\]\((https?://[^)\s]+)\)", report["markdown"])
    }
    evidence = {normalize(item["url"]): item for item in output.get("evidence", [])}
    supported = citations & evidence.keys()
    run = output["run"]
    measured = run.get("elapsed_seconds")
    target = run["config"]["target_seconds"]
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
        and not citations - evidence.keys()
        and review.get("distinct_sources_verified") is True
        and review.get("news_freshness_passed") is True
        and measured is not None
        and measured <= target
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
        "unsupported_urls": sorted(citations - evidence.keys()),
        "source_target_met": len(supported) >= 12
        and bool(valid_review and review.get("distinct_sources_verified")),
        "recent_dated_sources": len(dated),
        "news_freshness_passed": review.get("news_freshness_passed")
        if valid_review
        else None,
        "elapsed_seconds": measured,
        "target_seconds": target,
        "time_target_met": measured is not None and measured <= target,
        "note": "URL count and string structure alone do not establish factual accuracy or independent sources.",
    }
