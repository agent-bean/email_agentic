from datetime import datetime, UTC, timedelta

import pytest

from email_agentic.integrations.calendar_event import eligible, revision


def event(hours=2, **changes):
    return {'id': 'instance-1', 'summary': 'Discussion with Example', 'description': 'https://example.com',
            'start': {'dateTime': (datetime.now(UTC) + timedelta(hours=hours)).isoformat()},
            'end': {'dateTime': (datetime.now(UTC) + timedelta(hours=hours + 1)).isoformat()}, **changes}


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
