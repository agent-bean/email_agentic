"""Commit each Gmail page and its work before advancing the durable cursor."""
import uuid
import json
import hashlib
from psycopg.types.json import Jsonb

from email_agentic.domains.inbox.automation import eligible, queue_intake
from email_agentic.platform.errors import Conflict
from email_agentic.runtime.jobs import enqueue


class GmailSync:
    def __init__(self, db, google, settings):
        self.db, self.google, self.settings = db, google, settings

    async def run(self, owner, retry_failed=False):
        row = await self.db.one("SELECT cursor FROM sync_cursors WHERE owner=%s AND provider='gmail'", (owner,))
        old = row['cursor'] if row else None
        cursor = json.loads(old) if old else None
        known = {row['source_id'] for row in await self.db.all('''SELECT source_id FROM inputs
            WHERE owner=%s AND provider='google' AND kind='email' AND (content->>'status'='succeeded' OR purged_at IS NOT NULL) ''', (owner,))}
        retry_ids = [row['source_id'] for row in await self.db.all('''SELECT source_id FROM inputs
            WHERE owner=%s AND provider='google' AND kind='email' AND content->>'status'='read_failed'
            ORDER BY created_at LIMIT 50''', (owner,))] if retry_failed else []
        messages, next_cursor, more = await self.google.sync_inbox(cursor, known, retry_ids)
        encoded = json.dumps(next_cursor, sort_keys=True)
        async with self.db.transaction() as connection:
            await connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (f'gmail-sync:{owner}',))
            current = await (await connection.execute(
                "SELECT cursor FROM sync_cursors WHERE owner=%s AND provider='gmail'", (owner,),
            )).fetchone()
            if (current['cursor'] if current else None) != old:
                raise Conflict('Gmail cursor changed; a concurrent scan already committed')
            for message in messages:
                source = await (await connection.execute('''INSERT INTO inputs(id,owner,provider,source_id,kind,content)
                    VALUES(%s,%s,'google',%s,'email',%s) ON CONFLICT(owner,provider,source_id,kind)
                    DO UPDATE SET content=excluded.content WHERE inputs.purged_at IS NULL RETURNING id''',
                    (uuid.uuid4(), owner, message['id'], Jsonb(message)),
                )).fetchone()
                if source and self.settings.email_automation_enabled and eligible(message, owner, self.settings.email_automation_start_at):
                    await queue_intake(connection, owner, source['id'])
            await connection.execute('''INSERT INTO sync_cursors VALUES(%s,'gmail',%s)
                ON CONFLICT(owner,provider) DO UPDATE SET cursor=excluded.cursor''', (owner, encoded))
            if more:
                digest = hashlib.sha256(encoded.encode()).hexdigest()
                await enqueue(connection, owner, 'scan_email', None, f'gmail-page:{owner}:{digest}')
        return messages
