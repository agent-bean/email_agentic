import asyncio
import base64
import json
from datetime import datetime, UTC
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from email_agentic.integrations.email_message import decode_message
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

    @property
    def drafts_available(self):
        try:
            scopes = set(json.loads(self.settings.google_token_path.read_text()).get("scopes", []))
            return bool(scopes & {"https://www.googleapis.com/auth/gmail.compose",
                                  "https://www.googleapis.com/auth/gmail.modify", "https://mail.google.com/"})
        except (OSError, ValueError, TypeError):
            return False

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

    async def inbox(self, known=()):
        messages = []
        # A bounded recent window avoids an unbounded full-mailbox scan on every click.
        result = await self.call("gmail", "GET", "gmail/v1/users/me/messages",
                                 params={"labelIds": "INBOX", "maxResults": 50})
        for item in result.get("messages", []):
            if item["id"] in known:
                continue
            try:
                result_message = await self.call(
                    "gmail", "GET", f"gmail/v1/users/me/messages/{item['id']}", params={"format": "raw"}
                )
                if result_message.get("sizeEstimate", 0) > 25 * 1024 * 1024:
                    messages.append({"id": item["id"], "status": "too_large"})
                    continue
                raw = base64.urlsafe_b64decode(result_message["raw"] + "===")
                messages.append({**await decode_message(raw, item["id"], result_message["threadId"]),
                                 "mailbox": self.settings.owner_email,
                                 "received_at": datetime.fromtimestamp(int(result_message.get("internalDate", "0")) / 1000, UTC).isoformat()})
            except ProviderFailure as exc:
                messages.append({"id": item["id"], "status": "read_failed",
                                 "error_code": f"{exc.provider}:{exc.category}"})
                if exc.transient:
                    break
        return messages

    def outgoing(self, report):
        message = EmailMessage()
        message["From"] = self.settings.owner_email
        for header, key in [("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")]:
            if report["recipients"].get(key):
                message[header] = ",".join(report["recipients"][key])
        message["Subject"] = report["email_subject"]
        message["Message-ID"] = report["correlation_id"]
        source = report.get("source_message") or {}
        if source:
            headers = source["headers"]
            message["In-Reply-To"] = headers["Message-ID"]
            message["References"] = " ".join(filter(None, [headers.get("References"), headers["Message-ID"]]))
        message.set_content(report["email_body"])
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw, **({"threadId": source["thread_id"]} if source else {})}

    def draft_matches(self, report, draft):
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                base64.urlsafe_b64decode(draft["message"]["raw"] + "==="))
            if message.is_multipart() or message.get_content_type() != "text/plain":
                return False
            def addresses(header):
                return sorted(a for _, a in getaddresses(message.get_all(header, [])))
            def normalize(text):
                return text.replace("\r\n", "\n").rstrip("\n")
            source = report.get("source_message") or {}
            return (
                draft["message"].get("threadId") == source.get("thread_id")
                and str(message.get("Subject", "")) == report["email_subject"]
                and str(message.get("In-Reply-To", "")) == source.get("headers", {}).get("Message-ID", "")
                and addresses("From") == [self.settings.owner_email]
                and not message.get("Reply-To")
                and all(addresses(header) == sorted(report["recipients"].get(key, []))
                        for header, key in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")))
                and normalize(message.get_content()) == normalize(report["email_body"])
            )
        except (KeyError, ValueError, TypeError, LookupError):
            return False

    async def send(self, report):
        draft_id = report.get("gmail_draft_provider_id")
        if draft_id:
            draft = await self.call("gmail", "GET", f"gmail/v1/users/me/drafts/{draft_id}",
                                    params={"format": "raw"})
            if not self.draft_matches(report, draft):
                raise ProviderFailure("gmail", category="draft_changed")
            # Supply the approved MIME in the send itself: a concurrent Gmail edit cannot alter recipients/body.
            return await self.call("gmail", "POST", "gmail/v1/users/me/drafts/send",
                                   json={"id": draft_id, "message": self.outgoing(report)})
        return await self.call("gmail", "POST", "gmail/v1/users/me/messages/send", json=self.outgoing(report))

    async def create_draft(self, report):
        return await self.call("gmail", "POST", "gmail/v1/users/me/drafts",
                               json={"message": self.outgoing(report)})

    async def find_draft(self, correlation_id):
        result = await self.call("gmail", "GET", "gmail/v1/users/me/drafts", params={
            "q": f"rfc822msgid:{correlation_id.strip('<>')}", "maxResults": 10})
        items = result.get("drafts", [])
        if len(items) != 1:
            return None
        # Read the receipt rather than relying on fields omitted by the listing response.
        return await self.call("gmail", "GET", f"gmail/v1/users/me/drafts/{items[0]['id']}",
                               params={"format": "minimal"})

    async def reconcile(self, message_id):
        result = await self.call(
            "gmail",
            "GET",
            "gmail/v1/users/me/messages",
            params={"q": f"in:sent rfc822msgid:{message_id.strip('<>')}", "maxResults": 5},
        )
        matches = result.get("messages", [])
        return matches[0]["id"] if len(matches) == 1 else None
