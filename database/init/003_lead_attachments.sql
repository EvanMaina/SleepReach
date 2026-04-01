-- =============================================================================
-- 003_lead_attachments.sql — Lead document attachments
-- =============================================================================

CREATE TABLE IF NOT EXISTS lead_attachments (
    id UUID NOT NULL DEFAULT uuid_generate_v4() PRIMARY KEY,
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    stored_filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    uploaded_by VARCHAR(255),
    uploaded_by_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_attachments_lead_id ON lead_attachments(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_attachments_created_at ON lead_attachments(created_at DESC);
