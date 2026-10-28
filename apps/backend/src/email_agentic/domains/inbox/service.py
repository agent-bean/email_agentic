import uuid
from psycopg.types.json import Jsonb


class Inbox:
    def __init__(self, db):
        self.db = db

    async def save(self, owner, provider, source_id, kind, content):
        await self.db.execute(
            """INSERT INTO inputs(id,owner,provider,source_id,kind,content)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(owner,provider,source_id,kind)
            DO UPDATE SET content=excluded.content""",
            (uuid.uuid4(), owner, provider, source_id, kind, Jsonb(content)),
        )
