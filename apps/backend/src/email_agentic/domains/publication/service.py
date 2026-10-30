from psycopg.types.json import Jsonb

from email_agentic.platform.errors import Conflict, NotFound


class Publication:
    def __init__(self, db, knowledge):
        self.db, self.knowledge = db, knowledge

    @staticmethod
    async def recover(connection):
        await connection.execute("""UPDATE publication_actions SET status='unknown',error_code='worker_interrupted'
            WHERE kind='email' AND status='running' AND id IN
            (SELECT entity_id FROM jobs WHERE kind='publish' AND ((status='running' AND lease_until<now()) OR status IN ('failed','done')))""")
        await connection.execute("""UPDATE publication_actions p SET status=CASE WHEN EXISTS(SELECT 1 FROM jobs j WHERE j.entity_id=p.id AND j.kind='publish' AND j.status IN ('failed','done')) THEN 'failed' ELSE 'pending' END
            WHERE kind='kb' AND status='running' AND id IN
            (SELECT entity_id FROM jobs WHERE kind='publish' AND ((status='running' AND lease_until<now()) OR status IN ('failed','done')))""")

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
            if action["status"] not in {"pending", "failed"}:
                raise Conflict("Invalid publication state")
            if approval["status"] != "approved":
                raise Conflict("Approval is no longer valid")
            latest = await (
                await connection.execute(
                    "SELECT id FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (row["run_id"],)
                )
            ).fetchone()
            if latest["id"] != row["id"]:
                raise Conflict("Publication version changed")
            if row["action_kind"] == "email":
                if action["gmail_draft_id"]:
                    draft = await (await connection.execute(
                        "SELECT * FROM gmail_drafts WHERE id=%s FOR UPDATE", (action["gmail_draft_id"],)
                    )).fetchone()
                else:
                    # Enabling send creates a new report version without changing the approved email.
                    draft = await (await connection.execute(
                        """SELECT d.* FROM gmail_drafts d JOIN reports r ON r.id=d.report_id
                        WHERE d.run_id=%s AND d.owner=%s AND r.email_subject=%s AND r.email_body=%s
                        AND r.recipients=%s::jsonb AND r.artifacts=%s::jsonb ORDER BY r.version DESC LIMIT 1 FOR UPDATE OF d""",
                        (row["run_id"], owner, row["email_subject"], row["email_body"],
                         Jsonb(row["recipients"]), Jsonb(row.get("artifacts", []))),
                    )).fetchone()
                if draft:
                    used = await (await connection.execute(
                        "SELECT id FROM publication_actions WHERE gmail_draft_id=%s AND id<>%s",
                        (draft["id"], action_id),
                    )).fetchone()
                    if used or draft["status"] != "succeeded" or not draft["provider_id"]:
                        await connection.execute(
                            "UPDATE publication_actions SET status='blocked',error_code='draft_unavailable' WHERE id=%s",
                            (action_id,),
                        )
                        return None
                    await connection.execute("UPDATE publication_actions SET gmail_draft_id=%s WHERE id=%s",
                                             (draft["id"], action_id))
                    row["gmail_draft_provider_id"] = draft["provider_id"]
            await connection.execute(
                "UPDATE publication_actions SET status='running',started_at=now() WHERE id=%s", (action_id,)
            )
            from email_agentic.domains.reports.files import ReportFiles
            row['attachments'] = await ReportFiles(self.db).selected(connection, row)
            return row

    async def complete(self, action_id, status, provider_id=None, error=None):
        if status not in {"succeeded", "failed", "unknown"}:
            raise Conflict("Invalid publication completion state")
        async with self.db.transaction() as connection:
            action = await (await connection.execute(
                "SELECT status,provider_id,error_code FROM publication_actions WHERE id=%s FOR UPDATE",
                (action_id,),
            )).fetchone()
            if not action:
                raise NotFound()
            if (action["status"], action["provider_id"], action["error_code"]) == (status, provider_id, error):
                return
            # An uncertain send can acquire a late receipt, but cannot become safe to retry.
            if action["status"] != "running" and not (action["status"] == "unknown" and status == "succeeded"):
                raise Conflict("Publication is not awaiting this completion")
            await connection.execute(
                """UPDATE publication_actions SET status=%s,provider_id=%s,error_code=%s,
                updated_at=now() WHERE id=%s""", (status, provider_id, error, action_id))
            if status == "succeeded":
                await connection.execute(
                    """UPDATE gmail_drafts SET status='sent',error_code=NULL,updated_at=now()
                    WHERE id=(SELECT gmail_draft_id FROM publication_actions WHERE id=%s)""", (action_id,))

    async def save_kb(self, report):
        async with self.db.transaction() as connection:
            action = await (await connection.execute(
                "SELECT status,kind FROM publication_actions WHERE id=%s FOR UPDATE", (report["action_id"],),
            )).fetchone()
            if not action or action["kind"] != "kb":
                raise Conflict("Knowledge publication action is unavailable")
            if action["status"] == "succeeded":
                return
            if action["status"] != "running":
                raise Conflict("Knowledge publication has not started")
            await self.knowledge.store(connection, report, "approved")
            await connection.execute(
                "UPDATE publication_actions SET status='succeeded',updated_at=now() WHERE id=%s",
                (report["action_id"],),
            )

    async def sent_review(self, owner, action_id, google):
        from email_agentic.domains.reports.files import ReportFiles

        async with self.db.transaction() as connection:
            report = await (await connection.execute(
                """SELECT r.*,runs.source_message,runs.source_input_id,runs.history_purged_at,p.correlation_id,p.provider_id
                FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
                JOIN reports r ON r.id=a.report_id JOIN research_runs runs ON runs.id=r.run_id
                WHERE p.id=%s AND r.owner=%s AND p.kind='email'""", (action_id, owner))).fetchone()
            if not report:
                raise NotFound()
            if report['history_purged_at'] is not None or (report['source_input_id'] and not report['source_message']):
                return {'verification': 'content_expired', 'provider_id': report['provider_id']}
            report['attachments'] = await ReportFiles(self.db).selected(connection, report)
        return await google.review_sent(report)
