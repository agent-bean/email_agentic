"""Resolve a case email from the reviewed assignment input, independently of Gmail."""

import hashlib


def bind_source_email(case, bundle):
    if bundle.get("dataset_version") != case["dataset_version"]:
        raise ValueError("Case source dataset version does not match")
    source = bundle.get("cases", {}).get(case["case_id"])
    if not source or source.get("research_identity") != {
        "company_name": case["input"]["company_name"], "domain": case["input"]["domain"]
    }:
        raise ValueError("Case source is missing or belongs to another company")
    email = source.get("email", {})
    fields = [email.get(name) for name in ("sender", "company", "website", "body")]
    if any(not isinstance(value, str) or not value.strip() for value in fields):
        raise ValueError("Case source requires sender, company, website and original body")
    sender, company, website, body = fields
    text = f"Từ: {sender} – {company}\nWebsite: {website}\n\n{body}"
    if len(text) > 30000:
        raise ValueError("Case email exceeds the source-email limit")
    effective = {**case, "fixture_status": "case_source_bound",
                 "input": {**case["input"], "source_email": text}}
    provenance = {
        "case_id": case["case_id"], "dataset_version": case["dataset_version"],
        "authority": "assignment_slide", "source_document": bundle["source_document"],
        "source_email": text, "source_email_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "email": email, "supplements": source.get("supplements", {}),
    }
    return effective, provenance
