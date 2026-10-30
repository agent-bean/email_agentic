"""Owner-scoped read projections, independent of HTTP and command services."""

from email_agentic.integrations.calendar_event import revision
from email_agentic.platform.errors import NotFound


class WorkspaceQueries:
    def __init__(self, db):
        self.db = db

    async def runs(self, owner):
        return await self.db.all(
            "SELECT * FROM research_runs WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (owner,)
        )

    async def run_detail(self, owner, run_id, drafts_available):
        async with self.db.transaction() as connection:
            # All panels describe the same committed version, without holding row locks.
            await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")

            async def one(sql, params=()):
                return await (await connection.execute(sql, params)).fetchone()

            async def all_rows(sql, params=()):
                return await (await connection.execute(sql, params)).fetchall()

            run = await one("SELECT * FROM research_runs WHERE id=%s AND owner=%s", (run_id, owner))
            if not run:
                raise NotFound()
            reports = await all_rows("SELECT * FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (run_id,))
            approvals = await all_rows(
                "SELECT * FROM approvals WHERE report_id IN(SELECT id FROM reports WHERE run_id=%s) ORDER BY created_at DESC",
                (run_id,),
            )
            actions = await all_rows(
                "SELECT * FROM publication_actions WHERE approval_id IN(SELECT a.id FROM approvals a JOIN reports r ON r.id=a.report_id WHERE r.run_id=%s)",
                (run_id,),
            )
            return {
                "run": run,
                "reports": reports,
                "approvals": approvals,
                "actions": actions,
                "branches": await all_rows("SELECT * FROM branch_results WHERE run_id=%s", (run_id,)),
                "evidence": await all_rows(
                    "SELECT id,url,title,published_at FROM evidence WHERE run_id=%s", (run_id,)
                ),
                "usage": await all_rows(
                    "SELECT model,input_tokens,output_tokens,cost FROM model_usage WHERE run_id=%s", (run_id,)
                ),
                "gmail_drafts": await all_rows(
                    """SELECT d.id,d.report_id,d.status,d.provider_id,d.thread_id,d.error_code,
                    (r.email_subject=latest.email_subject AND r.email_body=latest.email_body
                     AND r.recipients=latest.recipients AND r.artifacts=latest.artifacts) AS matches_current
                    FROM gmail_drafts d JOIN reports r ON r.id=d.report_id
                    JOIN reports latest ON latest.run_id=d.run_id
                     AND latest.version=(SELECT max(version) FROM reports WHERE run_id=d.run_id)
                    WHERE d.run_id=%s ORDER BY d.created_at DESC""",
                    (run_id,),
                ),
                "gmail_drafts_available": drafts_available,
            }

    async def inputs(self, owner):
        rows = await self.db.all(
            """SELECT i.*,COALESCE(t.status,ct.status) AS intake_status,COALESCE(t.run_id,r.id,ct.run_id) AS research_run_id,ct.revision AS meeting_revision FROM inputs i
            LEFT JOIN email_triage t ON t.input_id=i.id AND t.owner=i.owner
            LEFT JOIN research_runs r ON r.source_input_id=i.id AND r.owner=i.owner
            LEFT JOIN LATERAL (SELECT status,run_id,revision FROM calendar_triage WHERE input_id=i.id AND owner=i.owner
             ORDER BY created_at DESC LIMIT 1) ct ON true
            WHERE i.owner=%s ORDER BY COALESCE((i.content->>'received_at')::timestamptz,i.created_at) DESC LIMIT 100""", (owner,)
        )

        for row in rows:
            if row["kind"] != "meeting":
                continue
            if row["calendar_available"] is False or row["meeting_revision"] != revision(row["content"]):
                row["research_run_id"] = None
                row["intake_status"] = "superseded"
        return rows

    async def input_detail(self, owner, input_id):
        row = await self.db.one(
            "SELECT * FROM inputs WHERE id=%s AND owner=%s", (input_id, owner)
        )
        if not row:
            raise NotFound()
        return row

    async def knowledge(self, owner):
        return await self.db.all(
            "SELECT * FROM knowledge WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (owner,)
        )

    async def companies(self, owner):
        return await self.db.all(
            "SELECT * FROM companies WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (owner,)
        )

    async def sent_review(self, owner):
        return await self.db.all(
            """SELECT p.id,r.run_id,r.version,r.email_subject,r.email_body,r.recipients,p.status,p.provider_id,
            p.error_code,a.created_at FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
            JOIN reports r ON r.id=a.report_id WHERE r.owner=%s AND p.kind='email'
            ORDER BY a.created_at DESC LIMIT 100""", (owner,))
