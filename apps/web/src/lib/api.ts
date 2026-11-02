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

// Paths, payloads and responses are tied together at the transport boundary.
type Paths = import('./api-schema').paths;
type Method = 'get' | 'post' | 'put';
type Operation<P extends keyof Paths, M extends Method> = NonNullable<Paths[P][M]>;
type Json<T> = T extends { content: { 'application/json': infer Value } } ? Value : never;
type ResponseBody<P extends keyof Paths, M extends Method> = Operation<P, M> extends { responses: infer R }
  ? Json<R[Extract<keyof R, 200 | 201 | 202>]> : never;
type RequestBody<P extends keyof Paths, M extends Method> = Operation<P, M> extends { requestBody: infer B } ? Json<B> : never;
type PathParams<P extends keyof Paths, M extends Method> = Operation<P, M> extends { parameters: { path: infer Params } } ? Params : never;
type RequestOptions<P extends keyof Paths, M extends Method> =
  ([PathParams<P, M>] extends [never] ? { path?: never } : { path: PathParams<P, M> }) &
  ([RequestBody<P, M>] extends [never] ? { body?: never } : { body: RequestBody<P, M> }) &
  { key?: string; signal?: AbortSignal };

async function request<P extends keyof Paths, M extends Method>(template: P, method: M, options: RequestOptions<P, M>): Promise<ResponseBody<P, M>> {
  let url: string = template;
  for (const [name, value] of Object.entries(options.path ?? {})) {
    url = url.replace(`{${name}}`, encodeURIComponent(String(value)));
  }
  return api<ResponseBody<P, M>>(url.replace(/^\/api\/v1/, ''), {
    method: method.toUpperCase(),
    signal: options.signal,
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
    ...(method === 'post' ? { headers: { 'Idempotency-Key': options.key ?? crypto.randomUUID() } } : {}),
  });
}

export const endpoints = {
  runs: (signal?: AbortSignal) => request('/api/v1/runs', 'get', { signal }),
  run: (id: string, signal?: AbortSignal) => request('/api/v1/runs/{run_id}', 'get', { path: { run_id: id }, signal }),
  createRun: (body: RequestBody<'/api/v1/runs', 'post'>, key: string) => request('/api/v1/runs', 'post', { body, key }),
  confirmIdentity: (id: string, body: RequestBody<'/api/v1/runs/{run_id}/identity', 'post'>) => request('/api/v1/runs/{run_id}/identity', 'post', { path: { run_id: id }, body }),
  editReport: (id: string, body: RequestBody<'/api/v1/runs/{run_id}/report', 'put'>) => request('/api/v1/runs/{run_id}/report', 'put', { path: { run_id: id }, body }),
  decide: (id: string, approve: boolean) => request('/api/v1/approvals/{approval_id}/decision', 'post', { path: { approval_id: id }, body: { approve } }),
  exportDraft: (id: string, version: number) => request('/api/v1/runs/{run_id}/gmail-draft', 'post', { path: { run_id: id }, body: { version } }),
  exportReport: (runId: string, reportId: string, format: 'pdf' | 'docx' | 'md') => request('/api/v1/runs/{run_id}/reports/{report_id}/exports/{format}', 'post', { path: { run_id: runId, report_id: reportId, format } }),
  inputs: (signal?: AbortSignal) => request('/api/v1/inputs', 'get', { signal }),
  input: (id: string, signal?: AbortSignal) => request('/api/v1/inputs/{input_id}', 'get', { path: { input_id: id }, signal }),
  sync: (provider: 'email' | 'calendar') => request('/api/v1/sync/{provider}', 'post', { path: { provider } }),
  knowledge: (signal?: AbortSignal) => request('/api/v1/knowledge', 'get', { signal }),
  companies: (signal?: AbortSignal) => request('/api/v1/companies', 'get', { signal }),
  system: (signal?: AbortSignal) => request('/api/v1/system', 'get', { signal }),
  sentReview: (signal?: AbortSignal) => request('/api/v1/sent-review', 'get', { signal }),
  verifySent: (id: string) => request('/api/v1/sent-review/{action_id}', 'get', { path: { action_id: id } }),
};
