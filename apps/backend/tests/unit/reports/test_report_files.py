import base64
import hashlib
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest

from email_agentic.integrations.google import Google
from email_agentic.integrations.report_export import render_export

MARKDOWN = "# Hồ sơ doanh nghiệp\n\nNghiên cứu và đối tác. **Thông tin** [Nguồn](https://example.com/source).\n\n| Mục | Nội dung |\n|---|---|\n| Sản phẩm | Phân tích tài liệu |\n"


@pytest.mark.parametrize(
    "format,mime",
    [
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("md", "text/markdown; charset=utf-8"),
    ],
)
async def test_gmail_mime_uses_selected_bytes_and_rejects_changes(format, mime):
    data = await render_export(MARKDOWN, format, "Báo cáo")
    file = {
        "filename": f"briefing.{format}",
        "mime_type": mime,
        "data": data,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    report = {
        "email_subject": "Trao đổi",
        "email_body": "Cảm ơn anh/chị.",
        "correlation_id": "<report@example.invalid>",
        "recipients": {"to": ["partner@example.invalid"]},
        "attachments": [file],
    }
    async with httpx.AsyncClient() as client:
        google = Google(client, SimpleNamespace(owner_email="owner@example.invalid"))
        outgoing = google.outgoing(report)
        draft = {"message": {"raw": outgoing["raw"]}}
        assert google.draft_matches(report, draft)
        mime = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(outgoing["raw"]))
        attachment = list(mime.iter_attachments())[0]
        assert attachment.get_payload(decode=True) == data
        attachment.set_payload(base64.b64encode(b"altered").decode())
        draft["message"]["raw"] = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        assert not google.draft_matches(report, draft)
        assert not google.draft_matches({**report, "attachments": []}, draft)
