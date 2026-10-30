import type { endpoints } from './api';

export type SourceInput = Awaited<ReturnType<typeof endpoints.input>>;
export type SourceMessage = Extract<SourceInput, { kind: 'email' }>['content'];
export type MeetingEvent = Extract<SourceInput, { kind: 'meeting' }>['content'];
