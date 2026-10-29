"""Bounded, offline PDF text/OCR extraction in an isolated process."""
import asyncio
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MAX_OCR_PAGES = 5
MAX_TEXT = 20000


def ocr_page(source, number, directory, remaining):
    image = Path(directory) / 'page'
    environment = {**os.environ, 'OMP_THREAD_LIMIT': '1'}
    deadline = time.monotonic() + remaining
    subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-singlefile',
                    '-scale-to', '2000', str(source), str(image)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=min(5, remaining), env=environment)
    try:
        output = subprocess.run(['tesseract', str(image) + '.ppm', 'stdout', '-l', 'eng+vie'],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=min(5, max(.01, deadline - time.monotonic())), env=environment)
        return output.stdout.decode('utf-8', errors='replace')
    finally:
        Path(str(image) + '.ppm').unlink(missing_ok=True)


def extract(data):
    from pypdf import PdfReader

    if len(data) > MAX_BYTES:
        return {'status': 'too_large'}
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {'status': 'encrypted'}
        pages, texts, truncated, attempted = [], [], False, 0
        deadline = time.monotonic() + 17
        with tempfile.TemporaryDirectory(prefix='email-pdf-') as directory:
            source = Path(directory) / 'source.pdf'
            source.write_bytes(data)
            for number, page in enumerate(reader.pages[:MAX_PAGES], 1):
                text = page.extract_text() or ''
                method, status = 'text', 'succeeded' if text.strip() else 'no_text'
                # Includes inline BI/EI images and images nested in XObject forms.
                # Blank pages need no OCR; text-bearing pages keep their text layer.
                if not text.strip() and len(page.images):
                    method = 'ocr'
                    if attempted >= MAX_OCR_PAGES or time.monotonic() >= deadline:
                        status = 'ocr_limit_reached'
                    else:
                        attempted += 1
                        try:
                            text = ocr_page(source, number, directory, deadline - time.monotonic())
                            status = 'succeeded' if text.strip() else 'no_text'
                        except FileNotFoundError:
                            status = 'ocr_unavailable'
                        except subprocess.TimeoutExpired:
                            status = 'ocr_timeout'
                        except (OSError, subprocess.CalledProcessError):
                            status = 'ocr_failed'
                available = max(0, MAX_TEXT - sum(map(len, texts)) - 2 * len(texts))
                truncated |= len(text) > available or status.startswith('ocr_')
                text = text[:available]
                pages.append({'page': number, 'method': method, 'status': status, 'text': text})
                texts.append(text)
                if len(text) >= available:
                    break
        text = '\n\n'.join(texts)[:MAX_TEXT]
        failed = any(p['status'].startswith('ocr_') for p in pages)
        status = 'succeeded' if text.strip() else 'no_text'
        if failed:
            status = 'partial' if text.strip() else next(p['status'] for p in pages if p['status'].startswith('ocr_'))
        return {'status': status, 'text': text, 'pages': len(reader.pages), 'pages_read': len(pages),
                'page_results': pages, 'truncated': truncated or len(reader.pages) > len(pages)}
    except Exception:
        return {'status': 'invalid_pdf'}


async def read_pdf(data):
    if len(data) > MAX_BYTES:
        return {'status': 'too_large'}
    # Parent owns the root so even SIGKILL cannot strand a private source/image.
    with tempfile.TemporaryDirectory(prefix='email-pdf-root-') as directory:
        return await _read_pdf(data, directory)


async def _read_pdf(data, directory):
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'email_agentic.integrations.pdf', start_new_session=True,
        env={**os.environ, 'TMPDIR': directory},
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(20):
            output, _ = await process.communicate(data)
        if process.returncode:
            return {'status': 'extraction_failed'}
        return json.loads(output)
    except TimeoutError:
        return {'status': 'timeout'}
    finally:
        # Also kill renderer/OCR descendants on cancellation, timeout or child crash.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


if __name__ == '__main__':
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    print(json.dumps(extract(sys.stdin.buffer.read(MAX_BYTES + 1)), ensure_ascii=False))
