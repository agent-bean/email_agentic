"""Stable meeting identity and scheduling rules; never rewrite the source event."""
import hashlib
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def revision(event):
    fields = {key: event.get(key) for key in
              ('summary', 'description', 'location', 'start', 'end', 'organizer', 'status', 'eventType')}
    fields['attendees'] = sorted(
        ({'email': a.get('email', ''), 'responseStatus': a.get('responseStatus', '')}
         for a in event.get('attendees', [])), key=lambda a: a['email'])
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def starts_at(event, timezone):
    start = event.get('start', {})
    try:
        if start.get('dateTime'):
            value = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            return value if value.tzinfo else value.replace(tzinfo=ZoneInfo(start.get('timeZone', timezone)))
        return datetime.combine(datetime.fromisoformat(start['date']).date(), time(), ZoneInfo(timezone))
    except (KeyError, TypeError, ValueError):
        return None


def eligible(event, owner, now, timezone):
    start = starts_at(event, timezone)
    return bool(start and now < start <= now + timedelta(hours=24)
                and event.get('status') != 'cancelled'
                and event.get('eventType', 'default') == 'default'
                and not any(a.get('email', '').casefold() == owner.casefold()
                            and a.get('responseStatus') == 'declined' for a in event.get('attendees', [])))
