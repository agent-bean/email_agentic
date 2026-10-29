"""Extract bounded PDF text in an isolated process; never execute embedded content."""
import asyncio
import io
import json
import sys

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT = 20000


def extract(data):
    from pypdf import PdfReader

    if len(data) > MAX_BYTES:
        return {"status": "too_large"}
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {"status": "encrypted"}
        texts = []
        truncated = False
        for page in reader.pages[:MAX_PAGES]:
            page_text = page.extract_text() or ""
            truncated |= len(page_text) > MAX_TEXT
            texts.append(page_text[:MAX_TEXT])
            if sum(map(len, texts)) >= MAX_TEXT:
                break
        text = "\n\n".join(texts)
        return {"status": "succeeded" if text.strip() else "no_text", "text": text[:MAX_TEXT],
                "pages": len(reader.pages), "pages_read": len(texts),
                "truncated": truncated or len(reader.pages) > len(texts) or len(text) > MAX_TEXT}
    except Exception:
        return {"status": "invalid_pdf"}


async def read_pdf(data):
    if len(data) > MAX_BYTES:
        return {"status": "too_large"}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "email_agentic.integrations.pdf",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(20):
            output, _ = await process.communicate(data)
        if process.returncode:
            return {"status": "extraction_failed"}
        return json.loads(output)
    except TimeoutError:
        return {"status": "timeout"}
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


if __name__ == "__main__":
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    print(json.dumps(extract(sys.stdin.buffer.read(MAX_BYTES + 1)), ensure_ascii=False))
