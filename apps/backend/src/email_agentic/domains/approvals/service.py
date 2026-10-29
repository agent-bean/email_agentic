import uuid
from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.runtime.jobs import enqueue
from email_agentic.integrations.calendar_event import eligible, revision
from datetime import datetime, UTC


class Approvals:
    def __init__(self, db, companies, timezone="Asia/Bangkok"):
        self.db, self.companies, self.timezone = db, companies, timezone

    async def confirm_identity(self, owner, run_id, version, company_name=None, domain=None):
        async with self.db.transaction() as connection:
            run = await (
                await connection.execute(
                    "SELECT * FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE", (run_id, owner)
                )
            ).fetchone()
            if not run:
                raise NotFound()
            if run.get("raw_purged_at") or run["status"] != "awaiting_identity" or run["version"] != version:
                raise Conflict("Identity request changed")
            if run.get('source_meeting_id'):
                source = await (await connection.execute(
                    "SELECT content,calendar_available FROM inputs WHERE id=%s AND owner=%s FOR SHARE",
                    (run['source_meeting_id'], owner),
                )).fetchone()
                if not source or source['calendar_available'] is False or revision(source['content']) != run['source_meeting_revision'] or not eligible(
                        source['content'], owner, datetime.now(UTC), self.timezone):
                    raise Conflict("Meeting changed or is no longer upcoming; synchronize Calendar and review its current proposal")
            if company_name is not None:
                from email_agentic.domains.research.service import ResearchRequest
                identity = ResearchRequest(company_name=company_name, domain=domain)
                run = {**run, "company_name": identity.company_name, "domain": identity.domain}
                await connection.execute(
                    "UPDATE research_runs SET company_name=%s,domain=%s WHERE id=%s",
                    (run["company_name"], run["domain"], run_id),
                )
            await self.companies.confirm(connection, run)
            await connection.execute(
                """UPDATE research_runs SET identity_confirmed=true,status='queued',version=version+1,
                config=CASE WHEN config->'timing'->>'version'='1'
                    AND config->'timing' ? 'identity_wait_started_at'
                    AND NOT (config->'timing' ? 'identity_confirmed_at')
                    THEN jsonb_set(config,'{timing,identity_confirmed_at}',to_jsonb(clock_timestamp()))
                    ELSE config END WHERE id=%s""",
                (run_id,),
            )
            await enqueue(connection, owner, "resume", run_id, f"identity:{run_id}:{version}")

    async def decide(self, owner, approval_id, approve):
        async with self.db.transaction() as connection:
            reference = await (
                await connection.execute(
                    """SELECT r.run_id FROM approvals a JOIN reports r ON r.id=a.report_id
                WHERE a.id=%s AND a.owner=%s""",
                    (approval_id, owner),
                )
            ).fetchone()
            if not reference:
                raise NotFound()
            await connection.execute(
                "SELECT id FROM research_runs WHERE id=%s FOR UPDATE", (reference["run_id"],)
            )
            row = await (
                await connection.execute(
                    """SELECT a.*, r.send_email,r.save_kb,r.run_id,r.artifacts,r.id AS selected_report_id FROM approvals a
                JOIN reports r ON r.id=a.report_id WHERE a.id=%s AND a.owner=%s FOR UPDATE OF a""",
                    (approval_id, owner),
                )
            ).fetchone()
            if row["status"] != "pending":
                raise Conflict("Approval already decided or superseded")
            valid = await (
                await connection.execute("SELECT now()<%s AS valid", (row["expires_at"],))
            ).fetchone()
            if not valid["valid"]:
                raise Conflict("Approval expired")
            latest = await (
                await connection.execute(
                    "SELECT id FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (row["run_id"],)
                )
            ).fetchone()
            if latest["id"] != row["report_id"]:
                raise Conflict("Report version changed")
            await connection.execute(
                "UPDATE approvals SET status=%s,decided_at=now() WHERE id=%s",
                ("approved" if approve else "rejected", approval_id),
            )
            if approve:
                from email_agentic.domains.reports.files import ReportFiles
                await ReportFiles(self.db).selected(connection, {'id': row['selected_report_id'],
                    'owner': owner, 'artifacts': row['artifacts']})
                for kind, enabled in [("email", row["send_email"]), ("kb", row["save_kb"])]:
                    if enabled:
                        action_id = uuid.uuid4()
                        await connection.execute(
                            """INSERT INTO publication_actions(id,approval_id,kind,correlation_id)
                            VALUES(%s,%s,%s,%s)""",
                            (action_id, approval_id, kind, f"<{action_id}@email-agentic.invalid>"),
                        )
                        await enqueue(connection, owner, "publish", action_id, f"action:{action_id}")
            await enqueue(connection, owner, "approval_resume", row["run_id"], f"approval:{approval_id}")
