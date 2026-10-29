"""Create identity proposals without approving research or sending mail."""
from datetime import datetime
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from email_agentic.agents.email_intake import EmailIntakeAgent, EmailIntakeDecision
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.integrations.email_message import safe_addresses
from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.runtime.jobs import enqueue


def eligible(source, owner, start):
    if source.get('status') != 'succeeded' or not source.get('source_text'):
        return False
    try:
        received = datetime.fromisoformat(source['received_at'])
        return received.tzinfo is not None and received >= start
    except (KeyError, ValueError, TypeError):
        return False


def automated(source, owner):
    headers = source.get('headers', {})
    addresses = [a.casefold() for a in safe_addresses(headers.get('From', ''))]
    return (
        owner.casefold() in addresses
        or headers.get('Auto-Submitted', '').casefold() not in {'', 'no'}
        or headers.get('Precedence', '').casefold() in {'bulk', 'list', 'junk'}
        or bool(headers.get('List-Id'))
        or any(a.split('@')[0] in {'noreply', 'no-reply', 'notifications'} for a in addresses)
    )


async def queue_intake(connection, owner, input_id):
    inserted = await (await connection.execute(
        'INSERT INTO email_triage(input_id,owner) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING input_id',
        (input_id, owner),
    )).fetchone()
    if inserted:
        await enqueue(connection, owner, 'email_intake', input_id, f'email-intake:{owner}:{input_id}')


class EmailAutomation:
    def __init__(self, db, research, llm, settings):
        self.db, self.research, self.settings = db, research, settings
        self.agent = EmailIntakeAgent(llm)

    async def complete(self, input_id, status, decision=None, run_id=None):
        await self.db.execute(
            '''UPDATE email_triage SET status=%s,decision=COALESCE(%s,decision),run_id=%s,
               error_code=NULL,updated_at=now() WHERE input_id=%s''',
            (status, Jsonb(decision) if decision else None, run_id, input_id),
        )

    async def run(self, owner, input_id):
        if not self.settings.email_automation_enabled:
            return
        row = await self.db.one('''SELECT i.content,t.status,t.decision FROM inputs i
            JOIN email_triage t ON t.input_id=i.id AND t.owner=i.owner
            WHERE i.id=%s AND i.owner=%s AND i.kind='email' AND i.provider='google' ''', (input_id, owner))
        if not row:
            raise NotFound()
        if row['status'] not in {'queued', 'failed'}:
            return
        existing = await self.db.one('SELECT id FROM research_runs WHERE owner=%s AND source_input_id=%s',
                                     (owner, input_id))
        if existing:
            await self.complete(input_id, 'research_created', run_id=existing['id'])
            return
        source = row['content']
        if not eligible(source, owner, self.settings.email_automation_start_at) or automated(source, owner):
            await self.complete(input_id, 'skipped')
            return
        if len(source['source_text']) > 30000:
            await self.complete(input_id, 'needs_review')
            return
        if row['decision']:
            decision = EmailIntakeDecision.model_validate(row['decision'])
        else:
            decision = await self.agent.run(input_id, source)
        data = decision.model_dump()
        await self.complete(input_id, 'queued', data)
        if decision.disposition != 'business':
            await self.complete(input_id, 'skipped' if decision.disposition == 'ignore' else 'needs_review', data)
            return
        try:
            request = ResearchRequest(company_name=decision.company_name, domain=decision.domain,
                                      source_input_id=input_id)
        except ValidationError:
            await self.complete(input_id, 'needs_review', data)
            return
        try:
            run_id = await self.research.create(owner, request, f'email-intake:{input_id}')
        except Conflict:
            # A manual import may win while classification is in flight.
            previous = await self.db.one('SELECT id FROM research_runs WHERE owner=%s AND source_input_id=%s',
                                         (owner, input_id))
            if not previous:
                raise
            run_id = previous['id']
        await self.complete(input_id, 'research_created', data, run_id)
