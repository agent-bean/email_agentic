import uuid


class Knowledge:
    def __init__(self, db):
        self.db = db

    async def retrieve(self, owner, domain):
        return await self.db.all(
            """SELECT k.id,k.status,k.content FROM knowledge k
            JOIN research_runs r ON r.id=k.run_id WHERE k.owner=%s AND r.domain=%s
            ORDER BY k.created_at DESC LIMIT 5""",
            (owner, domain),
        )

    async def store(self, connection, report, status):
        await connection.execute(
            """INSERT INTO knowledge(id,owner,run_id,report_id,status,content)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(report_id,status) DO NOTHING""",
            (uuid.uuid4(), report["owner"], report["run_id"], report["id"], status, report["markdown"]),
        )
