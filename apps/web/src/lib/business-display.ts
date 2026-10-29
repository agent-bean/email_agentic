// Keep stored inputs and provenance intact; omit test labels only when displaying them.
export function businessDisplayText(text: string): string {
  return text
    .replace(/\[DỮ LIỆU MẪU\]\s*/giu, '')
    .replace(/\[(?:TC-0[1-6]|TCX)\]\s*/giu, '')
    .replace(/^[ \t]*DỮ LIỆU GIẢ LẬP\s*[—–-]\s*KHÔNG PHẢI EMAIL CỦA DOANH NGHIỆP\.?[ \t]*(?:\r?\n|$)/gimu, '')
    .replace(/^[ \t]*Người liên hệ giả lập:\s*Demo Contact TC-0[1-6]\.?[ \t]*(?:\r?\n|$)/gimu, '')
    .replace(/^[ \t]*Đầu mối trao đổi:\s*TC-0[1-6]\.?[ \t]*(?:\r?\n|$)/gimu, '')
    .replace(/^[ \t]*Mã bộ mẫu:\s*email-agentic-demo-[^\r\n]*(?:\r?\n|$)/gimu, '')
    .replace(/^[ \t]*Cuộc họp giả lập\. Không có khách mời bên ngoài\. email-agentic-demo-[^\r\n]*(?:\r?\n|$)/gimu, '')
    .replace(/^\s*TC-0[1-6]\.\s*Dữ liệu demo giả lập\.\s*/iu, '')
    .replace(/^(\s*)(?:TC-0[1-6]|TCX)[ \t]+[—–:-][ \t]+/gmu, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function businessDisplayValue(value: unknown): unknown {
  if (typeof value === 'string') return businessDisplayText(value);
  if (Array.isArray(value)) return value.map(businessDisplayValue);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, businessDisplayValue(item)]));
  }
  return value;
}
