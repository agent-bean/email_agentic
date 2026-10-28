"""Create explicitly labelled demo mail and one event in a test account.

Uses the runtime token for mail; calendar writes require the separate seed token.
No delete or reset operations. A local ledger prevents blind retries of sends.
"""
import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email import policy
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / '.runtime/google-demo'
MANIFEST = DATA / 'manifest.json'
VERSION = 'email-agentic-demo-v1-20261028'
CASES = [
    ('TC-01', 'FPT Software', 'Chúng tôi muốn trao đổi giải pháp AI cho doanh nghiệp. Vui lòng chuẩn bị hồ sơ công ty, sản phẩm và tin tức gần đây.', 'https://fptsoftware.com/about-us'),
    ('TC-02', 'Vinamilk', 'Chúng tôi quan tâm ứng dụng AI trong quản lý tài liệu. Cần briefing về doanh nghiệp và các dự án AI có nguồn kiểm chứng.', 'https://www.vinamilk.com.vn/'),
    ('TC-03', 'Samsung Electronics Việt Nam — SEV Bắc Ninh', 'Đề nghị trao đổi giới thiệu giải pháp vào tuần tới, theo cuộc hẹn có cùng mã dữ liệu mẫu trong lịch. Chỉ nghiên cứu SEV Bắc Ninh; không gộp SEVT hoặc Samsung Vina.', 'https://news.samsung.com/vn/overview'),
    ('TC-04', 'Shopee Vietnam', 'Chúng tôi quan tâm OCR để xử lý tài liệu. Vui lòng nghiên cứu công ty và đề xuất nhu cầu tiềm năng từ nội dung này; phân biệt suy luận với dữ kiện.', 'https://www.sea.com/products/shopee'),
    ('TC-05', 'Viettel Solutions', 'Gửi kèm PDF hồ sơ năng lực giả lập để kiểm thử đọc attachment. Nội dung PDF không phải hồ sơ chính thức. Hãy kết hợp với website và ghi rõ nguồn.', 'https://solutions.viettel.vn/vi'),
    ('TC-06', 'Bosch Global Software Technologies Vietnam', 'Mong trao đổi AI Automation. Vui lòng tổng hợp thông tin công ty, sản phẩm, đối tác; chỉ lưu báo cáo chính thức vào KB sau duyệt.', 'https://www.bosch-softwaretechnologies.com/en/locations/vietnam/about-us/'),
]


def save(data):
    temporary = MANIFEST.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temporary.replace(MANIFEST)


def request(url, token=None, data=None, form=False):
    headers = {'User-Agent': 'email-agentic-setup/0.1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=encoded, headers=headers), timeout=40) as response:
        return json.load(response)


def access_token(filename):
    client = json.loads((ROOT / '.secrets/google/oauth-client.json').read_text())['web']
    credential = json.loads(filename.read_text())
    result = request('https://oauth2.googleapis.com/token', data={
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'refresh_token': credential['refresh_token'], 'grant_type': 'refresh_token'}, form=True)
    return result['access_token']


def pdf_bytes():
    # Deterministic one-page PDF; all content is synthetic, with no corporate claims.
    lines = ['DU LIEU GIA LAP - KHONG PHAI HO SO CHINH THUC',
             'Email Agentic / TC-05 / Viettel Solutions',
             'Purpose: test PDF attachment parsing with synthetic input.',
             'Demo contact: Nguoi lien he mau TC-05 (fictional).',
             'Demo capabilities: OCR, document classification, workflow integration.',
             'These are test assumptions, not verified company capabilities.',
             'Demo need: classify 1000 sample documents per day (fictional).',
             'Official source for independent research: https://solutions.viettel.vn/vi',
             'No real contract, employee identity, financial or customer data.']
    content = 'BT /F1 12 Tf 40 790 Td 18 TL\n'
    for line in lines:
        content += '(' + line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ') Tj T*\n'
    content = (content + 'ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    result = b'%PDF-1.4\n'; offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(result)
    result += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    result += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True, help='Exact owner of the dedicated test mailbox/calendar.')
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {'version': VERSION, 'mail': {}}
    assert ledger['version'] == VERSION, 'Different dataset preserved.'
    mail_token = access_token(ROOT / '.secrets/google/token.json')
    profile = request('https://gmail.googleapis.com/gmail/v1/users/me/profile', mail_token)
    assert profile['emailAddress'].lower() == args.account.lower(), 'Wrong mailbox; no data created.'
    seed_token = access_token(ROOT / '.secrets/google/seed-token.json')
    seed_profile = request('https://gmail.googleapis.com/gmail/v1/users/me/profile', seed_token)
    assert seed_profile['emailAddress'].lower() == args.account.lower(), 'Wrong calendar identity.'
    attachment = pdf_bytes()
    (DATA / 'viettel-solutions-demo.pdf').write_bytes(attachment)
    for case, company, text, source in CASES:
        message_id = f'{VERSION}.{case}@email-agentic.invalid'
        previous = ledger['mail'].get(case, {})
        if previous.get('id'):
            # Search indexing can lag after send. A saved provider ID is authoritative.
            existing = request('https://gmail.googleapis.com/gmail/v1/users/me/messages/' + previous['id'] + '?format=metadata', mail_token)
            found = [{'id': existing['id']}]
        else:
            query = urllib.parse.urlencode({'q': 'rfc822msgid:' + message_id, 'includeSpamTrash': 'true'})
            found = request('https://gmail.googleapis.com/gmail/v1/users/me/messages?' + query, mail_token).get('messages', [])
        if found:
            ledger['mail'][case] = {'state': 'sent', 'id': found[0]['id'], 'message_id': message_id}
            save(ledger)
        elif case in ledger['mail']:
            raise RuntimeError('Existing send ledger needs reconciliation; refusing duplicate send.')
        else:
            message = EmailMessage()
            message['From'] = args.account
            message['To'] = args.account
            message['Subject'] = f'[DỮ LIỆU MẪU][{case}] {company}'
            message['Message-ID'] = '<' + message_id + '>'
            message['X-Email-Agentic-Dataset'] = VERSION
            message.set_content(f'DỮ LIỆU GIẢ LẬP — KHÔNG PHẢI EMAIL CỦA DOANH NGHIỆP.\nNgười liên hệ giả lập: Demo Contact {case}.\n\n{text}\n\nNguồn khởi đầu nghiên cứu: {source}\nMã bộ mẫu: {VERSION}. Không tự phát hành báo cáo hoặc gửi tới doanh nghiệp thật.\n')
            if case == 'TC-05':
                message.add_attachment(attachment, maintype='application', subtype='pdf', filename='viettel-solutions-demo.pdf')
            ledger['mail'][case] = {'state': 'sending', 'message_id': message_id}
            save(ledger)  # Persist intent before an external send; unknown results are never blindly retried.
            sent = request('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', mail_token,
                           {'raw': base64.urlsafe_b64encode(message.as_bytes(policy=policy.SMTP)).decode()})
            ledger['mail'][case].update(state='sent', id=sent['id'])
            save(ledger)
        detail = request('https://gmail.googleapis.com/gmail/v1/users/me/messages/' + ledger['mail'][case]['id'] + '?format=full', mail_token)
        assert 'INBOX' in detail.get('labelIds', []), 'Message sent but not verified in inbox.'
        ledger['mail'][case]['inbox_verified'] = True
        if case == 'TC-05':
            part = next(p for p in detail['payload'].get('parts', []) if p.get('filename') == 'viettel-solutions-demo.pdf')
            body = part['body']
            if body.get('attachmentId'):
                body = request('https://gmail.googleapis.com/gmail/v1/users/me/messages/' + detail['id'] + '/attachments/' + body['attachmentId'], mail_token)
            raw = base64.urlsafe_b64decode(body['data'] + '===')
            assert hashlib.sha256(raw).digest() == hashlib.sha256(attachment).digest(), 'Attachment mismatch.'
            ledger['mail'][case]['attachment_verified'] = True
        save(ledger)
        print(case + ': inbox verified', flush=True)
    event_id = hashlib.sha256(VERSION.encode()).hexdigest()[:32]
    endpoint = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
    try:
        event = request(endpoint + '/' + event_id, seed_token)
        assert event.get('extendedProperties', {}).get('private', {}).get('dataset') == VERSION
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        start = (datetime.now(ZoneInfo('Asia/Bangkok')) + timedelta(days=6)).replace(hour=10, minute=0, second=0, microsecond=0)
        event = request(endpoint + '?sendUpdates=none', seed_token, {
            'id': event_id, 'summary': '[DỮ LIỆU MẪU][TC-03] Samsung SEV Bắc Ninh — giới thiệu giải pháp',
            'description': 'Cuộc họp giả lập. Không có khách mời bên ngoài. ' + VERSION,
            'start': {'dateTime': start.isoformat(), 'timeZone': 'Asia/Bangkok'},
            'end': {'dateTime': (start + timedelta(hours=1)).isoformat(), 'timeZone': 'Asia/Bangkok'},
            'reminders': {'useDefault': False}, 'extendedProperties': {'private': {'dataset': VERSION}}})
    ledger['event'] = {'id': event['id'], 'start': event['start'], 'calendar': 'primary'}
    save(ledger)
    print('Calendar: demo event verified; no guests invited', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Setup stopped safely: ' + type(error).__name__ + (f' HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else ''))
        raise SystemExit(1)
