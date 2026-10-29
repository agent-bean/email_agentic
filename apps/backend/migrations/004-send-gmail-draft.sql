ALTER TABLE publication_actions ADD COLUMN gmail_draft_id uuid REFERENCES gmail_drafts(id);
CREATE UNIQUE INDEX publication_gmail_draft ON publication_actions(gmail_draft_id)
 WHERE gmail_draft_id IS NOT NULL;
