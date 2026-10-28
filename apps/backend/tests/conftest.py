import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from email_agentic.platform.database import Database


@pytest.fixture
async def db():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Run app-control.py test after starting the isolated PostgreSQL stack")
    database = Database(dsn)
    await database.open()
    try:
        yield database
    finally:
        await database.close()
