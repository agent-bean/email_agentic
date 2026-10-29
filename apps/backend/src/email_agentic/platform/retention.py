"""Retire expired payloads while preserving dedupe tombstones and unresolved sends."""

import argparse
import asyncio
import json
from datetime import datetime, UTC, timedelta
from pathlib import Path
from email_agentic.platform.backup import backup_database
from email_agentic.platform.config import get_settings
from email_agentic.platform.database import Database

# Pending review, queued/running work and ambiguous sends keep all recovery material.
PROTECTED = """NOT EXISTS(SELECT 1 FROM jobs j WHERE j.status IN ('pending','running') AND
 (j.entity_id=r.id OR j.entity_id IN (SELECT id FROM gmail_drafts WHERE run_id=r.id)
 OR j.entity_id IN (SELECT p.id FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
 JOIN reports rp ON rp.id=a.report_id WHERE rp.run_id=r.id)))
 AND NOT EXISTS(SELECT 1 FROM approvals a JOIN reports rp ON rp.id=a.report_id
 WHERE rp.run_id=r.id AND a.status='pending')
 AND NOT EXISTS(SELECT 1 FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
 JOIN reports rp ON rp.id=a.report_id WHERE rp.run_id=r.id AND p.status IN ('pending','running','unknown'))
 AND NOT EXISTS(SELECT 1 FROM gmail_drafts d WHERE d.run_id=r.id AND d.status IN ('pending','running','unknown'))"""


async def cleanup(db, owner, apply=False, now=None):
    now = now or datetime.now(UTC)
    async with db.transaction() as conn:
        await conn.execute("SELECT pg_advisory_xact_lock(4782042)")
        runs = await (
            await conn.execute(
                f"""SELECT r.id FROM research_runs r WHERE r.owner=%s
            AND r.created_at<%s AND r.raw_purged_at IS NULL AND {PROTECTED} FOR UPDATE OF r SKIP LOCKED""",
                (owner, now - timedelta(days=30)),
            )
        ).fetchall()
        # A selected run can be purged at a second boundary even if its raw data was already retired.
        history = await (
            await conn.execute(
                f"""SELECT r.id FROM research_runs r WHERE r.owner=%s
            AND r.created_at<%s AND r.history_purged_at IS NULL AND {PROTECTED} FOR UPDATE OF r SKIP LOCKED""",
                (owner, now - timedelta(days=90)),
            )
        ).fetchall()
        run_ids = [r["id"] for r in runs]
        history_ids = [r["id"] for r in history]
        inputs = await (
            await conn.execute(
                """SELECT i.id FROM inputs i WHERE i.owner=%s AND i.created_at<%s
            AND i.purged_at IS NULL AND NOT (i.kind='meeting' AND i.calendar_available IS TRUE) AND NOT EXISTS(SELECT 1 FROM research_runs r
            WHERE (r.source_input_id=i.id OR r.source_meeting_id=i.id) AND r.raw_purged_at IS NULL AND NOT(r.id=ANY(%s::uuid[])))
            AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.entity_id=i.id AND j.status IN ('pending','running'))
            AND NOT EXISTS(SELECT 1 FROM calendar_triage ct JOIN jobs j ON j.entity_id=ct.id
                WHERE ct.input_id=i.id AND j.status IN ('pending','running'))
            FOR UPDATE OF i SKIP LOCKED""",
                (owner, now - timedelta(days=30), run_ids),
            )
        ).fetchall()
        result = {
            "raw_runs": len(runs),
            "report_histories": len(history),
            "inputs": len(inputs),
            "applied": apply,
        }
        if not apply:
            return result
        for rid in run_ids:
            await conn.execute("DELETE FROM evidence WHERE run_id=%s", (rid,))
            await conn.execute("DELETE FROM branch_results WHERE run_id=%s", (rid,))
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await conn.execute(f"DELETE FROM {table} WHERE thread_id=%s", (str(rid),))
            await conn.execute(
                """UPDATE research_runs SET context='',source_email=NULL,source_message=NULL,
                source_meeting=NULL,raw_purged_at=%s WHERE id=%s""",
                (now, rid),
            )
        for rid in history_ids:
            await conn.execute(
                "DELETE FROM report_files WHERE report_id IN(SELECT id FROM reports WHERE run_id=%s)", (rid,)
            )
            await conn.execute("DELETE FROM knowledge WHERE run_id=%s AND status='draft'", (rid,))
            await conn.execute(
                """UPDATE reports SET markdown='[Content expired under retention policy]',email_body='',
                email_subject='',recipients='{}',artifacts='[]' WHERE run_id=%s""",
                (rid,),
            )
            await conn.execute("UPDATE research_runs SET history_purged_at=%s WHERE id=%s", (now, rid))
        for row in inputs:
            await conn.execute(
                """UPDATE inputs SET content='{"status":"expired"}',purged_at=%s,
                calendar_available=false WHERE id=%s""",
                (now, row["id"]),
            )
            await conn.execute("UPDATE email_triage SET decision=NULL WHERE input_id=%s", (row["id"],))
            await conn.execute("UPDATE calendar_triage SET decision=NULL WHERE input_id=%s", (row["id"],))
        await conn.execute(
            "DELETE FROM audit_events WHERE owner=%s AND created_at<%s", (owner, now - timedelta(days=30))
        )
        await conn.execute(
            "DELETE FROM tool_limits WHERE owner=%s AND bucket<%s",
            (owner, int(now.timestamp() // 60) - 43200),
        )
        return result


def prune_local_dumps(directory, now=None):
    cutoff = (now or datetime.now(UTC)).timestamp() - 7 * 86400
    for path in Path(directory).glob("before-*.sql"):
        if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
            path.unlink()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    settings = get_settings()
    if args.apply:
        if not args.backup_dir:
            parser.error("--apply requires --backup-dir; a fresh backup is mandatory")
        await asyncio.to_thread(backup_database, settings.dsn, args.backup_dir, "retention")
    db = Database(settings.dsn)
    await db.open()
    try:
        result = await cleanup(db, settings.owner_email.casefold(), args.apply)
        if args.apply:
            prune_local_dumps(args.backup_dir)
        print(json.dumps(result))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
