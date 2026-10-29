ALTER TABLE research_runs ADD COLUMN source_input_id uuid REFERENCES inputs(id);
ALTER TABLE research_runs ADD COLUMN source_message jsonb;
CREATE UNIQUE INDEX research_email_source ON research_runs(owner, source_input_id)
 WHERE source_input_id IS NOT NULL;

CREATE TABLE gmail_drafts (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES research_runs(id),
 report_id uuid NOT NULL UNIQUE REFERENCES reports(id), owner text NOT NULL,
 status text NOT NULL DEFAULT 'pending', provider_id text, thread_id text,
 correlation_id text NOT NULL UNIQUE, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
