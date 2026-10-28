import asyncio
import base64
from email.message import EmailMessage
from threading import Lock

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from email_agentic.integrations.http import json_request
from email_agentic.platform.errors import ProviderFailure


class Google:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings
        self.lock = Lock()
        self.credentials = None

    def token(self):
        with self.lock:
            try:
                if self.credentials is None:
                    self.credentials = Credentials.from_authorized_user_file(
                        str(self.settings.google_token_path)
                    )
                credentials = self.credentials
                if not credentials.valid:
                    credentials.refresh(lambda **kwargs: Request()(**{**kwargs, "timeout": 20}))
                return credentials.token
            except Exception:
                raise ProviderFailure("google_auth") from None

    async def call(self, provider, method, path, **kwargs):
        token = await asyncio.to_thread(self.token)
        return await json_request(
            self.client,
            provider,
            method,
            "https://www.googleapis.com/" + path,
            headers={"Authorization": f"Bearer {token}"},
            **kwargs,
        )

    async def calendar(self, start, end):
        events = []
        page = None
        while True:
            params = {
                "timeMin": start,
                "timeMax": end,
                "singleEvents": "true",
                "showDeleted": "true",
                "maxResults": 250,
            }
            if page:
                params["pageToken"] = page
            result = await self.call(
                "calendar",
                "GET",
                f"calendar/v3/calendars/{self.settings.google_calendar_id}/events",
                params=params,
            )
            events.extend(result.get("items", []))
            page = result.get("nextPageToken")
            if not page:
                return events

    async def inbox(self):
        messages = []
        page = None
        while True:
            params = {"labelIds": "INBOX", "maxResults": 100}
            if page:
                params["pageToken"] = page
            result = await self.call("gmail", "GET", "gmail/v1/users/me/messages", params=params)
            for item in result.get("messages", []):
                messages.append(
                    await self.call(
                        "gmail", "GET", f"gmail/v1/users/me/messages/{item['id']}", params={"format": "full"}
                    )
                )
            page = result.get("nextPageToken")
            if not page:
                return messages

    async def send(self, report):
        message = EmailMessage()
        for header, key in [("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")]:
            if report["recipients"].get(key):
                message[header] = ",".join(report["recipients"][key])
        message["Subject"] = report["email_subject"]
        message["Message-ID"] = report["correlation_id"]
        message.set_content(report["email_body"])
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return await self.call("gmail", "POST", "gmail/v1/users/me/messages/send", json={"raw": raw})

    async def reconcile(self, message_id):
        result = await self.call(
            "gmail",
            "GET",
            "gmail/v1/users/me/messages",
            params={"q": f"in:sent rfc822msgid:{message_id.strip('<>')}", "maxResults": 5},
        )
        matches = result.get("messages", [])
        return matches[0]["id"] if len(matches) == 1 else None
