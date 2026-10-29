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

    async def sync_inbox(self, cursor, known=(), retry_ids=()):
        """Read one page; the caller persists its cursor with inputs and follow-up jobs."""
        profile = await self.call("gmail", "GET", "gmail/v1/users/me/profile")
        if profile.get("emailAddress", "").casefold() != self.settings.owner_email.casefold():
            raise ProviderFailure("gmail", category="mailbox_mismatch")
        if not cursor:
            cursor = {"mode": "full", "history_id": profile["historyId"]}
        page = cursor.get("page_token")
        if cursor["mode"] == "history":
            params = {"startHistoryId": cursor["history_id"], "maxResults": 50}
            if page:
                params["pageToken"] = page
            try:
                response = await self.call("gmail", "GET", "gmail/v1/users/me/history", params=params)
            except ProviderFailure as exc:
                if exc.category != "http_404":
                    raise
                return await self.sync_inbox(None, known, retry_ids)
            ids = []
            for event in response.get("history", []):
                for change in event.get("messagesAdded", []):
                    message = change.get("message", {})
                    if not message.get("labelIds") or "INBOX" in message["labelIds"]:
                        ids.append(message["id"])
                for change in event.get("labelsAdded", []):
                    if "INBOX" in change.get("labelIds", []):
                        ids.append(change["message"]["id"])
        else:
            params = {"labelIds": "INBOX", "maxResults": 50}
            if page:
                params["pageToken"] = page
            response = await self.call("gmail", "GET", "gmail/v1/users/me/messages", params=params)
            ids = [item["id"] for item in response.get("messages", [])]
        messages = []
        for message_id in dict.fromkeys([*ids, *retry_ids]):
            if message_id in known:
                continue
            try:
                item = await self.call("gmail", "GET", f"gmail/v1/users/me/messages/{message_id}",
                                       params={"format": "raw"})
            except ProviderFailure as exc:
                if exc.category == "http_404":
                    continue  # Deleted during synchronization; it is no longer actionable.
                if exc.category == "http_403" and not exc.transient:
                    messages.append({"id": message_id, "status": "read_failed", "error_code": "gmail:http_403"})
                    continue
                raise
            if "INBOX" not in item.get("labelIds", ["INBOX"]):
                continue
            if item.get("sizeEstimate", 0) > 25 * 1024 * 1024:
                messages.append({"id": message_id, "status": "too_large"})
                continue
            try:
                raw = base64.urlsafe_b64decode(item["raw"] + "===")
                source = await decode_message(raw, message_id, item["threadId"])
            except (KeyError, ValueError, TypeError):
                raise ProviderFailure("gmail", category="invalid_message") from None
            messages.append({**source, "mailbox": self.settings.owner_email,
                             "received_at": datetime.fromtimestamp(int(item.get("internalDate", "0")) / 1000, UTC).isoformat()})
        next_page = response.get("nextPageToken")
        next_cursor = ({**cursor, "page_token": next_page} if next_page else
                       {"mode": "history", "history_id": response.get("historyId", cursor["history_id"])})
        return messages, next_cursor, bool(next_page)

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
        for attachment in report.get('attachments', []):
            import hashlib
            if hashlib.sha256(attachment['data']).hexdigest() != attachment['sha256']:
                raise ProviderFailure('gmail', category='attachment_changed')
            maintype, subtype = attachment['mime_type'].split(';')[0].split('/', 1)
            message.add_attachment(attachment['data'], maintype=maintype, subtype=subtype,
                                   filename=attachment['filename'])
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": raw, **({"threadId": source["thread_id"]} if source else {})}

    def draft_matches(self, report, draft):
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                base64.urlsafe_b64decode(draft["message"]["raw"] + "==="))
            parts = list(message.iter_attachments()) if message.is_multipart() else []
            body = message.get_body(preferencelist=('plain',)) if message.is_multipart() else message
            if not body or body.get_content_type() != 'text/plain':
                return False
            import hashlib
            expected = report.get('attachments', [])
            if len(parts) != len(expected):
                return False
            for part, attachment in zip(parts, expected):
                if (part.get_filename() != attachment['filename'] or
                    part.get_content_type() != attachment['mime_type'].split(';')[0] or
                    hashlib.sha256(part.get_payload(decode=True) or b'').hexdigest() != attachment['sha256']):
                    return False
            # Any extra HTML/related part is a change to the approved plain-text email.
            if message.is_multipart() and len(list(message.walk())) != 2 + len(expected):
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
                and normalize(body.get_content()) == normalize(report["email_body"])
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

    async def review_sent(self, report):
        """Read actual Gmail state without sending or changing a stored receipt."""
        profile = await self.call("gmail", "GET", "gmail/v1/users/me/profile")
        if profile.get("emailAddress", "").casefold() != report["owner"].casefold():
            raise ProviderFailure("gmail", category="mailbox_mismatch")
        result = await self.call("gmail", "GET", "gmail/v1/users/me/messages", params={
            "q": f"in:sent rfc822msgid:{report['correlation_id'].strip('<>')}", "maxResults": 2})
        matches = list({item["id"]: item for item in result.get("messages", [])}.values())
        if len(matches) != 1 or result.get("nextPageToken"):
            return {"verification": "multiple_matches" if matches else "not_found", "provider_id": None}
        message = await self.call("gmail", "GET", f"gmail/v1/users/me/messages/{matches[0]['id']}",
                                  params={"format": "raw"})
        provider_id = message.get("id", matches[0]["id"])
        if message.get("sizeEstimate", 0) > 25 * 1024 * 1024:
            return {"verification": "too_large", "provider_id": provider_id}
        try:
            raw = base64.urlsafe_b64decode(message["raw"] + "===")
            mime = BytesParser(policy=policy.default).parsebytes(raw)
            verified = ("SENT" in message.get("labelIds", [])
                        and str(mime.get("Message-ID", "")) == report["correlation_id"]
                        and (not report.get("provider_id") or report["provider_id"] == provider_id)
                        and self.draft_matches(report, {"message": message if report.get("source_message") else
                                                {**message, "threadId": None}}))
        except (KeyError, ValueError, TypeError):
            verified = False
        return {"verification": "matched" if verified else "mismatch", "provider_id": provider_id}
