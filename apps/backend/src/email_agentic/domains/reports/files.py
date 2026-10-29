"""Immutable export bytes; selected attachments are part of the report version."""

import hashlib
import uuid

from email_agentic.integrations.report_export import MIME, render_export
from email_agentic.platform.errors import NotFound, Conflict


def descriptor(row):
    return {
        "id": str(row["id"]),
        "filename": row["filename"],
        "mime_type": row["mime_type"],
        "sha256": row["sha256"],
        "format": row["format"],
    }


class ReportFiles:
    def __init__(self, db):
        self.db = db

    async def create(self, connection, report, format):
        row = await (
            await connection.execute(
                "SELECT * FROM report_files WHERE report_id=%s AND format=%s", (report["id"], format)
            )
        ).fetchone()
        if row:
            return descriptor(row)
        try:
            data = await render_export(report["markdown"], format, f"Company briefing v{report['version']}")
        except (ValueError, TimeoutError) as exc:
            raise Conflict("Document could not be rendered within limits") from exc
        row = {
            "id": uuid.uuid4(),
            "filename": f"briefing-v{report['version']}.{format}",
            "mime_type": MIME[format],
            "sha256": hashlib.sha256(data).hexdigest(),
            "format": format,
        }
        saved = await (
            await connection.execute(
                """INSERT INTO report_files(id,report_id,owner,format,filename,mime_type,sha256,data)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(report_id,format) DO NOTHING RETURNING *""",
                (
                    row["id"],
                    report["id"],
                    report["owner"],
                    format,
                    row["filename"],
                    row["mime_type"],
                    row["sha256"],
                    data,
                ),
            )
        ).fetchone()
        if not saved:
            saved = await (
                await connection.execute(
                    "SELECT * FROM report_files WHERE report_id=%s AND format=%s", (report["id"], format)
                )
            ).fetchone()
        return descriptor(saved)

    async def export(self, owner, run_id, report_id, format):
        if format not in MIME:
            raise NotFound()
        async with self.db.transaction() as connection:
            run = await (
                await connection.execute(
                    "SELECT id FROM research_runs WHERE id=%s AND owner=%s AND history_purged_at IS NULL FOR SHARE",
                    (run_id, owner),
                )
            ).fetchone()
            if not run:
                raise NotFound()
            report = await (
                await connection.execute(
                    """SELECT r.* FROM reports r JOIN research_runs run ON run.id=r.run_id
                WHERE r.id=%s AND r.run_id=%s AND r.owner=%s AND run.history_purged_at IS NULL FOR SHARE OF r""",
                    (report_id, run_id, owner),
                )
            ).fetchone()
            if not report:
                raise NotFound()
            return await self.create(connection, report, format)

    async def get(self, owner, file_id):
        row = await self.db.one("SELECT * FROM report_files WHERE id=%s AND owner=%s", (file_id, owner))
        if not row:
            raise NotFound()
        if hashlib.sha256(bytes(row["data"])).hexdigest() != row["sha256"]:
            raise Conflict("Attachment checksum mismatch")
        return row

    async def selected(self, connection, report):
        files = []
        for item in report.get("artifacts", []):
            row = await (
                await connection.execute(
                    """SELECT f.* FROM report_files f JOIN reports original ON original.id=f.report_id
                    JOIN reports current ON current.id=%s WHERE f.id=%s AND f.owner=%s
                    AND original.run_id=current.run_id AND original.markdown=current.markdown""",
                    (report["id"], uuid.UUID(item["id"]), report["owner"]),
                )
            ).fetchone()
            if not row or descriptor(row) != item:
                raise Conflict("Selected attachment changed or is unavailable")
            data = bytes(row["data"])
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise Conflict("Selected attachment changed or is unavailable")
            files.append({**item, "data": data})
        return files
