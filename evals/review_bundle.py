"""Create a private, offline factual-review reader without reviewing or locking golden files."""

import argparse
import hashlib
import io
import json
import os
from html import escape
from pathlib import Path

from evals.golden import Golden


def build(paths):
    sections = []
    for path in paths:
        raw = path.read_bytes()
        golden = Golden.model_validate(json.loads(raw)["golden"])
        facts = []
        for fact in golden.facts:
            source = (path.parent / fact.source_file).resolve()
            if not source.is_relative_to(path.parent.resolve()) or not source.is_file():
                raise ValueError("Source must remain inside its golden directory")
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != fact.source_sha256:
                raise ValueError(
                    f"Source checksum mismatch: {golden.case_id}/{fact.id}"
                )
            if source.suffix.lower() == ".pdf":
                from pypdf import PdfReader

                excerpt = "\n".join(
                    page.extract_text() for page in PdfReader(io.BytesIO(data)).pages
                )
            else:
                excerpt = data.decode("utf-8", errors="replace")
            facts.append(
                f"<article><p><strong>{escape(fact.id)}</strong> {escape(fact.statement)}</p>"
                f"<details><summary>Nguồn: {escape(fact.source_file)} · {escape(fact.locator)}</summary>"
                f"<pre>{escape(excerpt)}</pre></details></article>"
            )
        sections.append(
            f"<section><h2>{escape(golden.case_id)} — {escape(golden.company_name)}</h2>"
            f"<p>Version {escape(golden.version)} · {escape(golden.status)} · "
            f"Mốc nguồn: {escape(golden.reference_time.isoformat())}</p>"
            + "".join(facts)
            + "<details><summary>Checklist khi review báo cáo</summary><ul>"
            + "".join(f"<li>{escape(item)}</li>" for item in golden.readiness_checklist)
            + f"</ul></details><small>Golden SHA-256: {hashlib.sha256(raw).hexdigest()}</small></section>"
        )
    return (
        '<!doctype html><html lang="vi"><meta charset="utf-8">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>Golden factual review</title><style>body{max-width:1000px;margin:40px auto;padding:0 24px;font:16px/1.6 sans-serif;color:#17202a}section{margin:40px 0;border-top:2px solid #ddd}article{padding:8px 0;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer;color:#155e75}small{overflow-wrap:anywhere}</style>"
        "<h1>Đối chiếu dữ kiện — 6 ca nghiên cứu</h1><p>Đọc từng dữ kiện, mở nguồn nếu cần. "
        "Đây là bản chờ review, chưa khóa và chưa phải kết quả accuracy. Các ghi chú nguồn cũ cần mở lại URL để xác nhận; "
        "nguồn thiếu hoặc mâu thuẫn phải sửa trước khi khóa. Email dùng dataset version 2.</p>"
        + "".join(sections)
        + "</html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = build(args.golden)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation preserves the reviewed artifact and its hashes across later runs.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print(
        f"Created factual-review reader for {len(args.golden)} cases; no review or lock performed."
    )


if __name__ == "__main__":
    main()
