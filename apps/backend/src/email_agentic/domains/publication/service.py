from email_agentic.platform.errors import Conflict, NotFound


class Publication:
    def __init__(self, db, knowledge):
        self.db, self.knowledge = db, knowledge

    async def authorized(self, owner, action_id, kind):
        row = await self.db.one(
            """SELECT p.id FROM publication_actions p
            JOIN approvals a ON a.id=p.approval_id JOIN reports r ON r.id=a.report_id
            WHERE p.id=%s AND r.owner=%s AND p.kind=%s AND a.status='approved'
            AND r.version=(SELECT max(version) FROM reports WHERE run_id=r.run_id)""",
            (action_id, owner, kind),
        )
        return row is not None

    async def package(self, owner, action_id):
        async with self.db.transaction() as connection:
            row = await (
                await connection.execute(
                    """SELECT r.*,runs.source_message,a.status AS approval_status,
                p.id AS action_id,p.status AS action_status,p.kind AS action_kind,p.correlation_id
                FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
                JOIN reports r ON r.id=a.report_id JOIN research_runs runs ON runs.id=r.run_id
                WHERE p.id=%s AND r.owner=%s""",
                    (action_id, owner),
                )
            ).fetchone()
            if not row:
                raise NotFound()
            await connection.execute("SELECT id FROM research_runs WHERE id=%s FOR UPDATE", (row["run_id"],))
            action = await (
                await connection.execute(
                    "SELECT * FROM publication_actions WHERE id=%s FOR UPDATE", (action_id,)
                )
            ).fetchone()
            approval = await (
                await connection.execute("SELECT status FROM approvals WHERE id=%s", (action["approval_id"],))
            ).fetchone()
            if action["status"] in {"succeeded", "unknown", "running", "blocked"}:
                return None
            if approval["status"] != "approved":
                raise Conflict("Approval is no longer valid")
            latest = await (
                await connection.execute(
                    "SELECT id FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (row["run_id"],)
                )
            ).fetchone()
            if latest["id"] != row["id"]:
                raise Conflict("Publication version changed")
            await connection.execute(
                "UPDATE publication_actions SET status='running',started_at=now() WHERE id=%s", (action_id,)
            )
            return row

    async def complete(self, action_id, status, provider_id=None, error=None):
        await self.db.execute(
            """UPDATE publication_actions SET status=%s,provider_id=%s,error_code=%s,
            updated_at=now() WHERE id=%s""",
            (status, provider_id, error, action_id),
        )

    async def save_kb(self, report):
        async with self.db.transaction() as connection:
            await self.knowledge.store(connection, report, "approved")
            await connection.execute(
                "UPDATE publication_actions SET status='succeeded',updated_at=now() WHERE id=%s",
                (report["action_id"],),
            )
