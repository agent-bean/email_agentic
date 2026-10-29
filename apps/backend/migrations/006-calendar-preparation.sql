ALTER TABLE inputs ADD COLUMN calendar_available boolean;
ALTER TABLE research_runs ADD COLUMN source_meeting_id uuid REFERENCES inputs(id);
ALTER TABLE research_runs ADD COLUMN source_meeting jsonb;
ALTER TABLE research_runs ADD COLUMN source_meeting_revision text;
CREATE UNIQUE INDEX research_meeting_revision ON research_runs(owner,source_meeting_id,source_meeting_revision)
 WHERE source_meeting_id IS NOT NULL;
CREATE TABLE calendar_triage (
 id uuid PRIMARY KEY, input_id uuid NOT NULL REFERENCES inputs(id), owner text NOT NULL,
 revision text NOT NULL, status text NOT NULL DEFAULT 'queued', decision jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 run_id uuid REFERENCES research_runs(id), error_code text, updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(owner,input_id,revision)
);
