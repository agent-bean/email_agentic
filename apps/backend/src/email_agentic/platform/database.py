from contextlib import asynccontextmanager
from contextvars import ContextVar

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

active_claim = ContextVar("active_claim", default=None)


class Database:
    def __init__(self, dsn: str):
        self.pool = AsyncConnectionPool(
            dsn, min_size=1, max_size=6, open=False, kwargs={"row_factory": dict_row}
        )

    async def open(self):
        await self.pool.open(wait=True)

    async def close(self):
        await self.pool.close()

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.connection() as connection:
            async with connection.transaction():
                claim = active_claim.get()
                if claim is not None:
                    current = await (
                        await connection.execute(
                            """SELECT id FROM jobs WHERE id=%s
                        AND claim_token=%s AND status='running' AND lease_until>now() FOR SHARE""",
                            (claim["id"], claim["claim_token"]),
                        )
                    ).fetchone()
                    if current is None:
                        raise RuntimeError("Job lease lost")
                yield connection

    async def one(self, sql, params=()):
        async with self.transaction() as connection:
            return await (await connection.execute(sql, params)).fetchone()

    async def all(self, sql, params=()):
        async with self.transaction() as connection:
            return await (await connection.execute(sql, params)).fetchall()

    async def execute(self, sql, params=()):
        async with self.transaction() as connection:
            return await connection.execute(sql, params)
