import uuid
from datetime import datetime, UTC, timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from email_agentic.agents.email_intake import EmailIntakeDecision
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.integrations.calendar_event import eligible, revision
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import Conflict
from email_agentic.workflows.research import make_graph


def event(hours=2, **changes):
    return {'id': 'instance-1', 'summary': 'Discussion with Example', 'description': 'https://example.com',
            'start': {'dateTime': (datetime.now(UTC) + timedelta(hours=hours)).isoformat()},
            'end': {'dateTime': (datetime.now(UTC) + timedelta(hours=hours + 1)).isoformat()}, **changes}


class Intake:
    calls = 0

    async def run(self, input_id, source):
        self.calls += 1
        return EmailIntakeDecision(disposition='business', company_name='Example', domain='example.com', reason='business_request')


@pytest.mark.parametrize('hours,status,declined,expected', [
    (2, 'confirmed', False, True), (25, 'confirmed', False, False),
    (-1, 'confirmed', False, False), (2, 'cancelled', False, False), (2, 'confirmed', True, False),
])
def test_calendar_preparation_window(hours, status, declined, expected):
    meeting = event(hours, status=status, attendees=[{'email': 'owner@example.invalid',
                    'responseStatus': 'declined' if declined else 'accepted'}])
    assert eligible(meeting, 'owner@example.invalid', datetime.now(UTC), 'Asia/Bangkok') is expected


def test_revision_ignores_provider_metadata_but_detects_business_changes():
    original = event()
    assert revision(original) == revision({**original, 'etag': 'new', 'reminders': {'useDefault': True}})
    assert revision(original) != revision({**original, 'summary': 'New agenda'})


async def test_calendar_creates_one_unconfirmed_run_per_instance_revision_and_preserves_source(db):
    owner = f'{uuid.uuid4()}@example.invalid'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, CALENDAR_AUTOMATION_ENABLED=True, _env_file=None)
    async with build_container(settings) as c:
        c.calendar_automation.agent = agent = Intake()
        original = event()
        await c.calendar_automation.save(owner, [original])
        await c.calendar_automation.save(owner, [original])
        triage = await db.one('SELECT * FROM calendar_triage WHERE owner=%s', (owner,))
        await c.calendar_automation.run(owner, triage['id'])
        await c.calendar_automation.run(owner, triage['id'])
        run = await db.one('SELECT * FROM research_runs WHERE owner=%s', (owner,))
        assert agent.calls == 1 and not run['identity_confirmed']
        assert run['source_meeting'] == original and run['source_email'] is None and run['source_message'] is None
        assert await c.research.create(owner, ResearchRequest(company_name='Example', domain='example.com',
            source_meeting_id=triage['input_id']), str(uuid.uuid4())) == run['id']
        await make_graph(c, InMemorySaver()).ainvoke({'run_id': str(run['id'])}, {'configurable': {'thread_id': str(run['id'])}})
        for changed in ({**original, 'summary': 'Changed agenda'}, {**original, 'status': 'cancelled'}):
            await c.calendar_automation.save(owner, [changed])
            with pytest.raises(Conflict, match='Meeting changed'):
                await c.approvals.confirm_identity(owner, run['id'], run['version'])
        assert (await db.one('SELECT count(*) AS n FROM reports WHERE run_id=%s', (run['id'],)))['n'] == 0


async def test_late_added_window_recurring_instances_and_missing_events(db):
    owner = f'{uuid.uuid4()}@example.invalid'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, CALENDAR_AUTOMATION_ENABLED=True, _env_file=None)
    async with build_container(settings) as c:
        now = datetime.now(UTC)
        first = event(25, recurringEventId='series')
        await c.calendar_automation.save(owner, [first], now)
        assert await db.one('SELECT id FROM calendar_triage WHERE owner=%s', (owner,)) is None
        await c.calendar_automation.save(owner, [first, {**first, 'id': 'instance-2'}], now + timedelta(hours=2))
        assert (await db.one('SELECT count(*) AS n FROM calendar_triage WHERE owner=%s', (owner,)))['n'] == 2
        await c.calendar_automation.save(owner, [])
        rows = await db.all('SELECT calendar_available FROM inputs WHERE owner=%s', (owner,))
        assert len(rows) == 2 and all(r['calendar_available'] is False for r in rows)
        for row in await db.all('SELECT id FROM inputs WHERE owner=%s', (owner,)):
            with pytest.raises(Conflict):
                await c.research.create(owner, ResearchRequest(company_name='Example', domain='example.com',
                    source_meeting_id=row['id']), str(uuid.uuid4()))


async def test_calendar_page_persistence_rolls_back_and_disabled_automation_only_saves(db):
    owner = f'{uuid.uuid4()}@example.invalid'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        with pytest.raises(KeyError):
            await c.calendar_automation.save(owner, [event(), {'summary': 'missing id'}])
        assert await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,)) is None
        await c.calendar_automation.save(owner, [event()])
        assert await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,))
        assert await db.one('SELECT id FROM calendar_triage WHERE owner=%s', (owner,)) is None
        source = await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,))
        with pytest.raises(Conflict):
            await c.research.create('other@example.invalid', ResearchRequest(company_name='Example', domain='example.com',
                source_meeting_id=source['id']), str(uuid.uuid4()))


async def test_unchanged_upcoming_meeting_can_be_confirmed_without_sending(db):
    owner = f'{uuid.uuid4()}@example.invalid'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        original = event()
        await c.calendar_automation.save(owner, [original])
        source = await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,))
        rid = await c.research.create(owner, ResearchRequest(company_name='Example', domain='example.com',
            source_meeting_id=source['id']), str(uuid.uuid4()))
        await make_graph(c, InMemorySaver()).ainvoke({'run_id': str(rid)}, {'configurable': {'thread_id': str(rid)}})
        run = await c.research.get(owner, rid)
        await c.approvals.confirm_identity(owner, rid, run['version'])
        assert (await c.research.get(owner, rid))['identity_confirmed']
        assert await db.one('SELECT id FROM reports WHERE run_id=%s', (rid,)) is None
        assert (await c.research.get(owner, rid))['source_meeting'] == original
