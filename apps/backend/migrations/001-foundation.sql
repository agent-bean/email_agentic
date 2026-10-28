CREATE TABLE companies (
 id uuid PRIMARY KEY, owner text NOT NULL, legal_name text NOT NULL, domain text NOT NULL,
 profile jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner,domain)
);
CREATE TABLE inputs (
 id uuid PRIMARY KEY, owner text NOT NULL, provider text NOT NULL, source_id text NOT NULL,
 kind text NOT NULL, content jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(owner,provider,source_id,kind)
);
CREATE TABLE sync_cursors (owner text NOT NULL, provider text NOT NULL, cursor text NOT NULL, PRIMARY KEY(owner,provider));
CREATE TABLE research_runs (
 id uuid PRIMARY KEY, owner text NOT NULL, company_name text NOT NULL, domain text NOT NULL,
 context text NOT NULL, status text NOT NULL DEFAULT 'queued', config jsonb NOT NULL,
 company_id uuid REFERENCES companies(id), created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), error_code text, elapsed_seconds double precision,
 identity_confirmed boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1
);
CREATE TABLE branch_results (
 run_id uuid REFERENCES research_runs(id), branch text NOT NULL, result jsonb NOT NULL,
 PRIMARY KEY(run_id,branch)
);
CREATE TABLE evidence (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES research_runs(id), url text NOT NULL,
 title text NOT NULL, content text NOT NULL, published_at timestamptz,
 collected_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id,url)
);
CREATE TABLE reports (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES research_runs(id), owner text NOT NULL,
 version integer NOT NULL, markdown text NOT NULL, email_subject text NOT NULL, email_body text NOT NULL,
 recipients jsonb NOT NULL, artifacts jsonb NOT NULL DEFAULT '[]', quality jsonb NOT NULL,
 save_kb boolean NOT NULL DEFAULT false, send_email boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id,version)
);
CREATE TABLE approvals (
 id uuid PRIMARY KEY, report_id uuid NOT NULL REFERENCES reports(id), owner text NOT NULL,
 status text NOT NULL DEFAULT 'pending', expires_at timestamptz NOT NULL DEFAULT now()+interval '24 hours',
 decided_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(report_id)
);
CREATE TABLE publication_actions (
 id uuid PRIMARY KEY, approval_id uuid NOT NULL REFERENCES approvals(id), kind text NOT NULL,
 status text NOT NULL DEFAULT 'pending', provider_id text, error_code text,
 correlation_id text NOT NULL, started_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(approval_id,kind)
);
CREATE TABLE knowledge (
 id uuid PRIMARY KEY, owner text NOT NULL, run_id uuid NOT NULL REFERENCES research_runs(id),
 report_id uuid REFERENCES reports(id), status text NOT NULL CHECK(status IN ('draft','approved')),
 content text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(report_id,status)
);
CREATE TABLE jobs (
 id uuid PRIMARY KEY, owner text NOT NULL, kind text NOT NULL, entity_id uuid,
 dedupe_key text NOT NULL UNIQUE, status text NOT NULL DEFAULT 'pending', attempt integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz, claim_token uuid,
 error_code text, created_at timestamptz NOT NULL DEFAULT now(), trace_parent text
);
CREATE INDEX jobs_claim ON jobs(available_at,created_at) WHERE status='pending';
CREATE TABLE schedule_ticks (name text NOT NULL, tick text NOT NULL, PRIMARY KEY(name,tick));
CREATE TABLE audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, owner text NOT NULL, actor_role text NOT NULL,
 tool text NOT NULL, run_id uuid, outcome text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tool_limits (owner text NOT NULL, tool text NOT NULL, bucket bigint NOT NULL, calls integer NOT NULL,
 PRIMARY KEY(owner,tool,bucket));
CREATE TABLE model_usage (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES research_runs(id), model text NOT NULL,
 input_tokens integer, output_tokens integer, cost numeric, created_at timestamptz NOT NULL DEFAULT now()
);
