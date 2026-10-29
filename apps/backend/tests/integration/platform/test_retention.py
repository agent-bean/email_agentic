import uuid
import pytest
from email_agentic.platform.errors import Conflict
from email_agentic.domains.reports.service import ReportEdit
from datetime import datetime, UTC, timedelta

from email_agentic.bootstrap import build_container
from email_agentic.platform.config import Settings
from email_agentic.platform.retention import cleanup
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.agents.contracts import Draft


async def test_retention_dry_run_protects_pending_work_and_preserves_approved_kb(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    async with build_container(Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)) as c:
        ids = []
        for _ in range(3):
            rid = await c.research.create(
                owner,
                ResearchRequest(company_name="Example", domain="example.com", source_email="Original email"),
                str(uuid.uuid4()),
            )
            run = await c.research.get(owner, rid)
            await c.reports.initial(
                run,
                Draft(markdown="Report kept in KB", email_subject="Subject", email_body="Private reply"),
                {},
            )
            await db.execute(
                "UPDATE research_runs SET created_at=now()-interval '100 days' WHERE id=%s", (rid,)
            )
            await db.execute("UPDATE jobs SET status='done' WHERE entity_id=%s", (rid,))
            ids.append(rid)
        # First pending approval protects everything. Second has ambiguous publication. Third can expire.
        for rid in ids[1:]:
            await db.execute(
                "UPDATE approvals SET status='approved' WHERE report_id IN(SELECT id FROM reports WHERE run_id=%s)",
                (rid,),
            )
        report = await c.reports.latest(owner, ids[1])
        a = await db.one("SELECT id FROM approvals WHERE report_id=%s", (report["id"],))
        await db.execute(
            "INSERT INTO publication_actions(id,approval_id,kind,status,correlation_id) VALUES(%s,%s,'email','unknown',%s)",
            (uuid.uuid4(), a["id"], str(uuid.uuid4())),
        )
        report = await c.reports.latest(owner, ids[2])
        exported = await c.reports.files.export(owner, ids[2], report["id"], "md")
        async with db.transaction() as conn:
            await c.knowledge.store(conn, report, "approved")
        dry = await cleanup(db, owner)
        assert dry["raw_runs"] == dry["report_histories"] == 1 and not dry["applied"]
        assert (await c.research.get(owner, ids[2]))["source_email"] == "Original email"
        result = await cleanup(db, owner, True)
        assert result["applied"]
        assert await db.one("SELECT id FROM report_files WHERE id=%s", (uuid.UUID(exported["id"]),)) is None
        for rid in ids[:2]:
            assert (await c.research.get(owner, rid))["source_email"] == "Original email"
        assert (await c.research.get(owner, ids[2]))["source_email"] is None
        assert (await c.reports.latest(owner, ids[2]))["email_body"] == ""
        knowledge = await c.knowledge.retrieve(owner, "example.com")
        assert any(k["status"] == "approved" and k["content"] == "Report kept in KB" for k in knowledge)
        assert (await cleanup(db, owner, True))["raw_runs"] == 0


async def test_raw_retention_keeps_report_until_ninety_days_and_input_tombstone(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    async with build_container(Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)) as c:
        rid = await c.research.create(
            owner,
            ResearchRequest(company_name="Example", domain="example.com", source_email="Original"),
            str(uuid.uuid4()),
        )
        run = await c.research.get(owner, rid)
        await c.reports.initial(
            run, Draft(markdown="Report", email_subject="Subject", email_body="Reply"), {}
        )
        await db.execute("UPDATE jobs SET status='done' WHERE entity_id=%s", (rid,))
        await db.execute(
            "UPDATE approvals SET status='rejected' WHERE report_id IN(SELECT id FROM reports WHERE run_id=%s)",
            (rid,),
        )
        await c.inbox.save(
            owner,
            "google",
            str(uuid.uuid4()),
            "email",
            {"status": "succeeded", "source_text": "Unlinked old email"},
        )
        future = datetime.now(UTC) + timedelta(days=31)
        result = await cleanup(db, owner, True, future)
        assert result["raw_runs"] == result["inputs"] == 1 and result["report_histories"] == 0
        report = await c.reports.latest(owner, rid)
        assert report["email_body"] == "Reply"
        assert await c.reports.files.export(owner, rid, report["id"], "md")
        with pytest.raises(Conflict, match="read-only"):
            await c.reports.edit(
                owner,
                rid,
                ReportEdit(version=1, markdown="Report", email_subject="Subject", email_body="Reply"),
            )
        await db.execute("UPDATE research_runs SET status='awaiting_identity' WHERE id=%s", (rid,))
        with pytest.raises(Conflict):
            await c.approvals.confirm_identity(owner, rid, run["version"])
        source = await db.one("SELECT * FROM inputs WHERE owner=%s", (owner,))
        assert source["content"] == {"status": "expired"} and source["purged_at"]
