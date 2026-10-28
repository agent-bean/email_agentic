import uuid
from psycopg.types.json import Jsonb


class Companies:
    def __init__(self, db):
        self.db = db

    async def lookup(self, owner, domain):
        return await self.db.one("SELECT * FROM companies WHERE owner=%s AND domain=%s", (owner, domain))

    async def confirm(self, connection, run):
        await connection.execute(
            """INSERT INTO companies(id,owner,legal_name,domain,profile)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(owner,domain) DO NOTHING""",
            (
                uuid.uuid4(),
                run["owner"],
                run["company_name"],
                run["domain"],
                Jsonb({"identity_confirmed_by_owner": True}),
            ),
        )
