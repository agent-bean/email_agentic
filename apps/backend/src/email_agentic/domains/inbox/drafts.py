import uuid

from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.runtime.jobs import enqueue


class GmailDrafts:
    def __init__(self, db):
        self.db = db

    async def request(self, owner, run_id, version):
        async with self.db.transaction() as connection:
            run = await (await connection.execute(
                "SELECT * FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE", (run_id, owner)
            )).fetchone()
            if not run:
                raise NotFound()
            if not run.get("source_message"):
                raise Conflict("A Gmail source is required to create a reply draft")
            report = await (await connection.execute(
                "SELECT * FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (run_id,)
            )).fetchone()
            if not report or report["version"] != version:
                raise Conflict("Report version changed")
            if not any(report["recipients"].values()):
                raise Conflict("Choose at least one recipient before creating a Gmail draft")
            existing = await (await connection.execute(
                "SELECT * FROM gmail_drafts WHERE report_id=%s", (report["id"],)
            )).fetchone()
            if existing:
                if existing["status"] in {"unknown", "failed"}:
                    job = await (await connection.execute(
                        "SELECT attempt,status FROM jobs WHERE kind='gmail_draft' AND entity_id=%s",
                        (existing["id"],),
                    )).fetchone()
                    if job and job["attempt"] >= 3 and job["status"] not in {"pending", "running"}:
                        raise Conflict("Đã thử ba lần; cần kiểm tra draft trực tiếp trong Gmail trước khi xử lý tiếp")
                    await connection.execute(
                        """UPDATE jobs SET status='pending',available_at=now(),error_code=NULL
                        WHERE kind='gmail_draft' AND entity_id=%s AND status IN ('failed','done') AND attempt<3""",
                        (existing["id"],),
                    )
                return existing["id"]
            draft_id = uuid.uuid4()
            await connection.execute(
                """INSERT INTO gmail_drafts(id,run_id,report_id,owner,correlation_id)
                VALUES(%s,%s,%s,%s,%s)""",
                (draft_id, run_id, report["id"], owner, f"<{draft_id}@email-assistant.local>"),
            )
            await enqueue(connection, owner, "gmail_draft", draft_id, f"gmail-draft:{draft_id}")
            return draft_id

    async def authorized(self, owner, draft_id):
        return bool(await self.db.one(
            "SELECT id FROM gmail_drafts WHERE id=%s AND owner=%s", (draft_id, owner)))

    async def package(self, owner, draft_id):
        async with self.db.transaction() as connection:
            row = await (await connection.execute(
                """SELECT d.*,r.email_subject,r.email_body,r.recipients,r.version,runs.source_message
                FROM gmail_drafts d JOIN reports r ON r.id=d.report_id
                JOIN research_runs runs ON runs.id=d.run_id WHERE d.id=%s AND d.owner=%s""",
                (draft_id, owner),
            )).fetchone()
            if not row:
                raise NotFound()
            await connection.execute("SELECT id FROM research_runs WHERE id=%s FOR UPDATE", (row["run_id"],))
            current = await (await connection.execute(
                "SELECT status FROM gmail_drafts WHERE id=%s FOR UPDATE", (draft_id,)
            )).fetchone()
            if current["status"] in {"succeeded", "blocked"}:
                return None
            row["reconcile_only"] = current["status"] in {"running", "unknown"}
            latest = await (await connection.execute(
                "SELECT id FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (row["run_id"],)
            )).fetchone()
            if not row["reconcile_only"] and latest["id"] != row["report_id"]:
                await connection.execute("UPDATE gmail_drafts SET status='blocked' WHERE id=%s", (draft_id,))
                return None
            await connection.execute("UPDATE gmail_drafts SET status='running',updated_at=now() WHERE id=%s",
                                     (draft_id,))
            return row

    async def complete(self, draft_id, status, provider_id=None, thread_id=None, error=None):
        await self.db.execute(
            """UPDATE gmail_drafts SET status=%s,provider_id=%s,thread_id=%s,error_code=%s,
            updated_at=now() WHERE id=%s""", (status, provider_id, thread_id, error, draft_id))
