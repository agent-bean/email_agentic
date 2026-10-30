import uuid
from email_agentic.models.reports import (
    Recipients as Recipients,
    ReportEdit as ReportEdit,
)

from email_agentic.domains.reports.files import ReportFiles
from psycopg.types.json import Jsonb

from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.integrations.email_message import safe_addresses


class Reports:
    def __init__(self, db, knowledge):
        self.db, self.knowledge = db, knowledge
        self.files = ReportFiles(db)

    async def latest(self, owner, run_id):
        row = await self.db.one(
            "SELECT * FROM reports WHERE run_id=%s AND owner=%s ORDER BY version DESC LIMIT 1",
            (run_id, owner),
        )
        if not row:
            raise NotFound()
        return row

    async def insert(
        self,
        connection,
        run,
        version,
        markdown,
        subject,
        body,
        recipients,
        send,
        kb,
        quality,
        formats=(),
        previous=None,
        rendered=None,
    ):
        report = {"id": uuid.uuid4(), "owner": run["owner"], "run_id": run["id"], "markdown": markdown}
        await connection.execute(
            """INSERT INTO reports(id,run_id,owner,version,markdown,email_subject,email_body,
            recipients,send_email,save_kb,quality) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                report["id"],
                run["id"],
                run["owner"],
                version,
                markdown,
                subject,
                body,
                Jsonb(recipients),
                send,
                kb,
                Jsonb(quality),
            ),
        )
        artifacts = []
        reusable = (
            {item["format"]: item for item in previous["artifacts"]}
            if previous and previous["markdown"] == markdown
            else {}
        )
        for format in dict.fromkeys(formats):
            artifacts.append(
                reusable.get(format)
                or await self.files.create(connection, {**report, "version": version}, format, rendered[format])
            )
        if artifacts:
            await connection.execute(
                "UPDATE reports SET artifacts=%s WHERE id=%s", (Jsonb(artifacts), report["id"])
            )
        await connection.execute(
            "INSERT INTO approvals(id,report_id,owner) VALUES(%s,%s,%s)",
            (uuid.uuid4(), report["id"], run["owner"]),
        )
        await self.knowledge.store(connection, report, "draft")
        return report["id"]

    async def initial(self, run, draft, quality):
        async with self.db.transaction() as connection:
            await connection.execute("SELECT id FROM research_runs WHERE id=%s FOR UPDATE", (run["id"],))
            existing = await (
                await connection.execute("SELECT id FROM reports WHERE run_id=%s LIMIT 1", (run["id"],))
            ).fetchone()
            if existing:
                return existing["id"]
            source = run.get("source_message") or {}
            headers = source.get("headers", {})
            recipients = safe_addresses(headers.get("Reply-To") or headers.get("From", ""))
            subject = "Re: " + headers["Subject"] if headers.get("Subject") else draft.email_subject
            if subject.lower().startswith("re: re:"):
                subject = subject[4:]
            return await self.insert(
                connection,
                run,
                1,
                draft.markdown,
                subject,
                draft.email_body,
                {"to": recipients, "cc": [], "bcc": []},
                False,
                False,
                quality,
            )

    async def editable(self, connection, owner, run_id, request, lock=False):
        run = await (
            await connection.execute(
                "SELECT * FROM research_runs WHERE id=%s AND owner=%s" + (" FOR UPDATE" if lock else ""),
                (run_id, owner),
            )
        ).fetchone()
        if not run or run.get("history_purged_at"):
            raise NotFound()
        if run.get("raw_purged_at"):
            raise Conflict("Source data expired; this report is read-only")
        old = await (
            await connection.execute(
                "SELECT * FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (run_id,)
            )
        ).fetchone()
        if not old or old["version"] != request.version:
            raise Conflict("Report version changed")
        if run.get("source_message") and request.email_subject != old["email_subject"]:
            raise Conflict("Keep the reply subject unchanged to preserve the Gmail thread")
        if request.send_email and not any(request.recipients.model_dump().values()):
            raise Conflict("Choose at least one recipient before enabling send")
        return run, old

    async def edit(self, owner, run_id, request):
        # Rendering may wait on CPU capacity. Keep all connections and run locks free while it does.
        async with self.db.transaction() as connection:
            _, snapshot = await self.editable(connection, owner, run_id, request)
        reusable = {item["format"] for item in snapshot["artifacts"]} if snapshot["markdown"] == request.markdown else set()
        rendered = {
            format: await self.files.render(request.markdown, request.version + 1, format)
            for format in dict.fromkeys(request.attachment_formats) if format not in reusable
        }
        async with self.db.transaction() as connection:
            run, old = await self.editable(connection, owner, run_id, request, lock=True)
            await connection.execute(
                "UPDATE approvals SET status='superseded' WHERE report_id=%s AND status IN ('pending','approved')",
                (old["id"],),
            )
            await connection.execute(
                """UPDATE publication_actions SET status='blocked' WHERE status='pending'
                AND approval_id IN(SELECT id FROM approvals WHERE report_id=%s)""",
                (old["id"],),
            )
            quality = dict(old["quality"], human_edited=True, content_review="required")
            return await self.insert(
                connection,
                run,
                old["version"] + 1,
                request.markdown,
                request.email_subject,
                request.email_body,
                request.recipients.model_dump(),
                request.send_email,
                request.save_kb,
                quality,
                request.attachment_formats,
                old,
                rendered,
            )
