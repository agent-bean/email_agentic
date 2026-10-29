"""Decode MIME without rewriting business wording or treating attachment text as email body."""
import hashlib
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser

from email_agentic.integrations.pdf import read_pdf


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li", "tr"} and not self.hidden:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def safe_addresses(value):
    return [address for _, address in getaddresses([value])
            if "@" in address and not any(c in address for c in "\r\n")]


async def decode_message(raw, message_id, thread_id):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = message.get_body(preferencelist=("plain", "html")) if message.is_multipart() else message
    decode_error = None
    try:
        body = part.get_content() if part and part.get_content_type() in {"text/plain", "text/html"} else ""
    except (LookupError, UnicodeError, ValueError):
        body = ""
        decode_error = "body_decode_failed"
    html = body if part and part.get_content_type() == "text/html" else None
    if html is not None:
        parser = TextHTML()
        parser.feed(html)
        body = "".join(parser.text)
    headers = {key: str(message.get(key, "")) for key in
               ("From", "To", "Cc", "Date", "Subject", "Message-ID", "Reply-To", "References")}
    attachments = []
    total_bytes = 0
    # Walk all MIME levels, including attachments nested in multipart/mixed/related.
    for item in message.walk():
        if item.is_multipart() or not (item.get_filename() or item.get_content_disposition() == "attachment"):
            continue
        data = item.get_payload(decode=True) or b""
        total_bytes += len(data)
        entry = {"filename": item.get_filename() or "attachment", "mime_type": item.get_content_type(),
                 "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if len(attachments) >= 5 or total_bytes > 20 * 1024 * 1024:
            entry["extraction"] = {"status": "limit_reached"}
        elif item.get_content_type() == "application/pdf" or entry["filename"].lower().endswith(".pdf"):
            entry["extraction"] = await read_pdf(data)
        else:
            entry["extraction"] = {"status": "unsupported_type"}
        attachments.append(entry)
    source = "\n".join(f"{key}: {headers[key]}" for key in ("From", "To", "Date", "Subject")) + "\n\n" + body
    return {"id": message_id, "thread_id": thread_id, "headers": headers,
            "subject": headers["Subject"], "body": body, "body_format": "html" if html else "plain",
            "html": html, "source_text": source, "attachments": attachments,
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "status": decode_error or "succeeded"}
