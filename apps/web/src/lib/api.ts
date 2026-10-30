import type { components } from './api-schema';
export type Run = components['schemas']['RunSummary'];
export type Detail = components['schemas']['RunDetail'];
export type Report = components['schemas']['ReportRow'];
export type ReportEdit = components['schemas']['ReportEdit'];
export type ResearchInput = components['schemas']['ResearchRequest'];

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, detail: string | null = null) {
    super(detail ?? `Yêu cầu không thành công (${status}).`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api/v1' + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      typeof body?.detail === 'string' ? body.detail : null,
    );
  }
  return response.json();
}
export function post<T>(
  path: string,
  body: unknown = {},
  key: string = crypto.randomUUID(),
): Promise<T> {
  return api<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'Idempotency-Key': key },
  });
}
