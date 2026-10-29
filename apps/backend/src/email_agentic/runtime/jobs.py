import uuid
from datetime import timedelta
from psycopg.types.json import Jsonb


async def enqueue(connection, owner, kind, entity_id, key):
    await connection.execute(
        """INSERT INTO jobs(id,owner,kind,entity_id,dedupe_key)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING""",
        (uuid.uuid4(), owner, kind, entity_id, key),
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
        await self.db.execute(
            """UPDATE jobs SET status=%s,error_code=%s,lease_until=NULL,
            available_at=now()+%s WHERE id=%s AND claim_token=%s AND lease_until>now()""",
            (
                "pending" if retry else status,
                error,
                timedelta(seconds=2 ** job["attempt"]),
                job["id"],
                job["claim_token"],
            ),
        )

    async def recover(self):
        async with self.db.transaction() as connection:
            await connection.execute("""UPDATE gmail_drafts SET status='unknown',error_code='worker_interrupted'
                WHERE status='running' AND id IN (SELECT entity_id FROM jobs WHERE kind='gmail_draft'
                AND ((status='running' AND lease_until<now()) OR status IN ('failed','done')))""")
            await connection.execute("""UPDATE publication_actions SET status='unknown',error_code='worker_interrupted'
                WHERE kind='email' AND status='running' AND id IN
                (SELECT entity_id FROM jobs WHERE kind='publish' AND ((status='running' AND lease_until<now()) OR status IN ('failed','done')))""")
            await connection.execute("""UPDATE publication_actions p SET status=CASE WHEN EXISTS(SELECT 1 FROM jobs j WHERE j.entity_id=p.id AND j.kind='publish' AND j.status IN ('failed','done')) THEN 'failed' ELSE 'pending' END
                WHERE kind='kb' AND status='running' AND id IN
                (SELECT entity_id FROM jobs WHERE kind='publish' AND ((status='running' AND lease_until<now()) OR status IN ('failed','done')))""")
            await connection.execute("""UPDATE jobs SET status=CASE WHEN attempt<3 THEN 'pending' ELSE 'failed' END,
                claim_token=NULL,lease_until=NULL,error_code='lease_expired'
                WHERE status='running' AND lease_until<now()""")

    async def save_branch(self, run_id, branch, result):
        await self.db.execute(
            """INSERT INTO branch_results VALUES(%s,%s,%s)
            ON CONFLICT(run_id,branch) DO UPDATE SET result=excluded.result""",
            (run_id, branch, Jsonb(result)),
        )
