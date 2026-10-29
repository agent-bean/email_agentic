CREATE TABLE report_files (
 id uuid PRIMARY KEY, report_id uuid NOT NULL REFERENCES reports(id), owner text NOT NULL,
 format text NOT NULL CHECK(format IN ('pdf','docx','md')), filename text NOT NULL,
 mime_type text NOT NULL, sha256 text NOT NULL, data bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(report_id,format),
 CHECK(octet_length(data)<=10485760)
);
ALTER TABLE research_runs ADD COLUMN raw_purged_at timestamptz;
ALTER TABLE research_runs ADD COLUMN history_purged_at timestamptz;
ALTER TABLE inputs ADD COLUMN purged_at timestamptz;
