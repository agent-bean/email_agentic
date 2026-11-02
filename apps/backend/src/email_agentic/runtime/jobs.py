import uuid
from datetime import timedelta
from psycopg.types.json import Jsonb
from email_agentic.platform.telemetry import current_trace_parent
from email_agentic.domains.inbox.job_state import fail_intake
from email_agentic.domains.research.execution import fail_processing, settle_processing
from email_agentic.runtime.execution import settle_intake


async def enqueue(connection, owner, kind, entity_id, key):
    await connection.execute(
        """INSERT INTO jobs(id,owner,kind,entity_id,dedupe_key,trace_parent)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING""",
        (uuid.uuid4(), owner, kind, entity_id, key, current_trace_parent()),
    )


class Jobs:
    def __init__(self, db):
        self.db = db

    async def claim(self, kinds=None, excluded=()):
        token = uuid.uuid4()
        return await self.db.one(
            """UPDATE jobs SET status='running', attempt=attempt+1,
            claim_token=%s,lease_until=now()+interval '60 seconds'
            WHERE id=(SELECT id FROM jobs WHERE status='pending' AND available_at<=now() AND (%s::text[] IS NULL OR kind=ANY(%s))
              AND NOT (kind=ANY(%s::text[]))
              ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *""",
            (token, kinds, kinds, list(excluded)),
        )

    async def heartbeat(self, job):
        row = await self.db.one(
            """UPDATE jobs SET lease_until=now()+interval '60 seconds'
            WHERE id=%s AND claim_token=%s AND status='running' AND lease_until>now() RETURNING id""",
            (job["id"], job["claim_token"]),
        )
        return row is not None

    async def finish(self, job, status="done", error=None, retry=False):
        async with self.db.transaction() as connection:
            current = await (await connection.execute(
                """SELECT * FROM jobs WHERE id=%s AND claim_token=%s
                AND status='running' AND lease_until>now() FOR UPDATE""",
                (job["id"], job["claim_token"]),
            )).fetchone()
            if current is None:
                return False
            await settle_processing(connection, current)
            await settle_intake(connection, current)
            if status == "failed":
                await fail_intake(connection, current, error, retry)
                if not retry:
                    await fail_processing(connection, current, error)
            await connection.execute(
                """UPDATE jobs SET status=%s,error_code=%s,lease_until=NULL,
                available_at=now()+%s WHERE id=%s""",
                ("pending" if retry else status, error,
                 timedelta(seconds=2 ** current["attempt"]), current["id"]),
            )
            return True

    async def recover(self):
        from email_agentic.domains.inbox.drafts import GmailDrafts
        from email_agentic.domains.publication.service import Publication

        async with self.db.transaction() as connection:
            expired = await (await connection.execute(
                "SELECT * FROM jobs WHERE status='running' AND lease_until<now() ORDER BY id FOR UPDATE",
            )).fetchall()
            await GmailDrafts.recover(connection)
            await Publication.recover(connection)
            for job in expired:
                await settle_processing(connection, job, recovered=True)
                await settle_intake(connection, job, recovered=True)
                if job["attempt"] >= 3:
                    await fail_processing(connection, job, "lease_expired")
                    await fail_intake(connection, job, "lease_expired")
            await connection.execute("""UPDATE jobs SET status=CASE WHEN attempt<3 THEN 'pending' ELSE 'failed' END,
                claim_token=NULL,lease_until=NULL,error_code='lease_expired'
                WHERE status='running' AND lease_until<now()""")

    async def save_branch(self, run_id, branch, result):
        await self.db.execute(
            """INSERT INTO branch_results VALUES(%s,%s,%s)
            ON CONFLICT(run_id,branch) DO UPDATE SET result=excluded.result""",
            (run_id, branch, Jsonb(result)),
        )
