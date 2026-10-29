CREATE TABLE email_triage (
 input_id uuid PRIMARY KEY REFERENCES inputs(id), owner text NOT NULL,
 status text NOT NULL DEFAULT 'queued', decision jsonb, run_id uuid REFERENCES research_runs(id),
 error_code text, updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE model_usage ALTER COLUMN run_id DROP NOT NULL;
ALTER TABLE model_usage ADD COLUMN input_id uuid REFERENCES inputs(id);
ALTER TABLE model_usage ADD CONSTRAINT model_usage_subject CHECK (run_id IS NOT NULL OR input_id IS NOT NULL);
