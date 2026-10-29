"""Persist calendar revisions and queue owner-confirmed meeting preparation."""
import uuid
import json
from datetime import datetime, UTC
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from email_agentic.agents.email_intake import EmailIntakeDecision
from email_agentic.agents.meeting_intake import MeetingIntakeAgent
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.integrations.calendar_event import eligible, revision
from email_agentic.platform.errors import NotFound
from email_agentic.runtime.jobs import enqueue


class CalendarAutomation:
    def __init__(self, db, research, llm, settings):
        self.db, self.research, self.settings = db, research, settings
        self.agent = MeetingIntakeAgent(llm)

    async def save(self, owner, events, now=None):
        now = now or datetime.now(UTC)
        async with self.db.transaction() as conn:
            await conn.execute("UPDATE inputs SET calendar_available=false WHERE owner=%s AND provider='google' AND kind='meeting' AND source_id LIKE %s",
                               (owner, self.settings.google_calendar_id + ':%'))
            for event in events:
                # Calendar ID namespaces event IDs, including recurring instances.
                source_id = self.settings.google_calendar_id + ':' + event['id']
                await conn.execute("""UPDATE inputs SET source_id=%s WHERE owner=%s AND provider='google'
                    AND kind='meeting' AND source_id=%s AND NOT EXISTS (SELECT 1 FROM inputs WHERE owner=%s
                    AND provider='google' AND kind='meeting' AND source_id=%s)""",
                    (source_id, owner, event['id'], owner, source_id))
                source = await (await conn.execute('''INSERT INTO inputs(id,owner,provider,source_id,kind,content,calendar_available)
                    VALUES(%s,%s,'google',%s,'meeting',%s,true) ON CONFLICT(owner,provider,source_id,kind)
                    DO UPDATE SET content=excluded.content,calendar_available=true RETURNING id''',
                    (uuid.uuid4(), owner, source_id, Jsonb(event)))).fetchone()
                if not self.settings.calendar_automation_enabled or not eligible(event, owner, now, self.settings.app_timezone):
                    continue
                key = revision(event)
                triage = await (await conn.execute('''INSERT INTO calendar_triage(id,input_id,owner,revision)
                    VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id''',
                    (uuid.uuid4(), source['id'], owner, key))).fetchone()
                if triage:
                    await enqueue(conn, owner, 'calendar_intake', triage['id'],
                                  f"calendar-intake:{owner}:{source['id']}:{key}")

    async def complete(self, triage_id, status, decision=None, run_id=None):
        await self.db.execute('''UPDATE calendar_triage SET status=%s,decision=COALESCE(%s,decision),
            run_id=%s,error_code=NULL,updated_at=now() WHERE id=%s''',
            (status, Jsonb(decision) if decision else None, run_id, triage_id))

    async def run(self, owner, triage_id):
        if not self.settings.calendar_automation_enabled:
            return
        row = await self.db.one('''SELECT t.*,i.content,i.calendar_available FROM calendar_triage t JOIN inputs i
            ON i.id=t.input_id AND i.owner=t.owner WHERE t.id=%s AND t.owner=%s''', (triage_id, owner))
        if not row:
            raise NotFound()
        if row['status'] not in {'queued', 'failed'}:
            return
        if row['calendar_available'] is False or revision(row['content']) != row['revision'] or not eligible(
                row['content'], owner, datetime.now(UTC), self.settings.app_timezone):
            await self.complete(triage_id, 'superseded')
            return
        if len(json.dumps(row['content'])) > 30000:
            await self.complete(triage_id, 'needs_review')
            return
        decision = (EmailIntakeDecision.model_validate(row['decision']) if row['decision']
                    else await self.agent.run(row['input_id'], row['content']))
        data = decision.model_dump()
        await self.complete(triage_id, 'queued', data)
        if decision.disposition != 'business':
            await self.complete(triage_id, 'skipped' if decision.disposition == 'ignore' else 'needs_review', data)
            return
        try:
            request = ResearchRequest(company_name=decision.company_name, domain=decision.domain,
                                      source_meeting_id=row['input_id'])
        except ValidationError:
            await self.complete(triage_id, 'needs_review', data)
            return
        run_id = await self.research.create(owner, request, f"calendar-intake:{triage_id}")
        await self.complete(triage_id, 'research_created', data, run_id)
