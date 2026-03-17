-- SleepReach — Initial Database Schema
-- HIPAA-compliant schema for sleep clinic patient intake and lead management

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =============================================================================
-- ENUM Types
-- =============================================================================

CREATE TYPE condition_type AS ENUM (
    'INSOMNIA',
    'SLEEP_APNEA',
    'RESTLESS_LEG',
    'NARCOLEPSY',
    'OTHER'
);

CREATE TYPE duration_type AS ENUM (
    'LESS_THAN_6_MONTHS',
    'SIX_TO_TWELVE_MONTHS',
    'MORE_THAN_12_MONTHS'
);

CREATE TYPE treatment_type AS ENUM (
    'CPAP_BIPAP',
    'MEDICATION',
    'SLEEP_STUDY',
    'THERAPY_CBT',
    'NONE',
    'OTHER'
);

CREATE TYPE urgency_type AS ENUM (
    'ASAP',
    'WITHIN_30_DAYS',
    'EXPLORING'
);

CREATE TYPE priority_type AS ENUM (
    'HOT',
    'MEDIUM',
    'LOW',
    'DISQUALIFIED'
);

CREATE TYPE lead_status AS ENUM (
    'NEW',
    'CONTACTED',
    'SCHEDULED',
    'CONSULTATION_COMPLETE',
    'TREATMENT_STARTED',
    'LOST',
    'DISQUALIFIED'
);

CREATE TYPE audit_action AS ENUM (
    'CREATE',
    'READ',
    'UPDATE',
    'DELETE',
    'EXPORT',
    'LOGIN',
    'LOGOUT'
);

CREATE TYPE contact_outcome_type AS ENUM (
    'NEW',
    'ANSWERED',
    'NO_ANSWER',
    'UNREACHABLE',
    'CALLBACK_REQUESTED',
    'SCHEDULED',
    'COMPLETED',
    'NOT_INTERESTED'
);

CREATE TYPE contact_method AS ENUM (
    'PHONE',
    'EMAIL',
    'SMS',
    'VIDEO_CALL'
);

CREATE TYPE lead_source AS ENUM (
    'widget',
    'jotform',
    'referral',
    'manual',
    'api',
    'import'
);

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_number VARCHAR(20) NOT NULL UNIQUE,

    -- Contact Information (PHI - encrypted)
    first_name_encrypted BYTEA NOT NULL,
    last_name_encrypted BYTEA,
    email_encrypted BYTEA NOT NULL,
    phone_encrypted BYTEA NOT NULL,

    date_of_birth DATE,

    -- Clinical Information
    condition condition_type NOT NULL,
    condition_other TEXT,
    conditions TEXT[] DEFAULT '{}',
    other_condition_text TEXT,

    -- Sleep Treatment Interest
    sleep_treatment_interest TEXT,

    -- Preferred Contact Method
    preferred_contact_method TEXT,

    symptom_duration duration_type NOT NULL,
    prior_treatments treatment_type[] NOT NULL DEFAULT '{}',

    -- Insurance
    has_insurance BOOLEAN NOT NULL,
    insurance_provider TEXT,
    other_insurance_provider TEXT,

    -- Location
    zip_code VARCHAR(10) NOT NULL,
    in_service_area BOOLEAN NOT NULL DEFAULT false,

    -- Urgency & Consent
    urgency urgency_type NOT NULL,
    hipaa_consent BOOLEAN NOT NULL DEFAULT false,
    hipaa_consent_timestamp TIMESTAMP WITH TIME ZONE,
    privacy_consent_timestamp TIMESTAMP WITH TIME ZONE,
    sms_consent BOOLEAN NOT NULL DEFAULT false,
    sms_consent_timestamp TIMESTAMP WITH TIME ZONE,

    -- Scoring & Priority
    score INTEGER NOT NULL DEFAULT 0,
    lead_score INTEGER DEFAULT 0,
    priority priority_type NOT NULL DEFAULT 'LOW',

    -- Score Breakdown
    condition_score INTEGER DEFAULT 0,
    therapy_interest_score INTEGER DEFAULT 0,
    severity_score INTEGER DEFAULT 0,
    insurance_score INTEGER DEFAULT 0,
    duration_score INTEGER DEFAULT 0,
    treatment_score INTEGER DEFAULT 0,
    location_score INTEGER DEFAULT 0,
    urgency_score INTEGER DEFAULT 0,

    -- Lead Management
    status lead_status NOT NULL DEFAULT 'NEW',
    assigned_to UUID,
    notes TEXT,

    -- Lead Source
    source lead_source NOT NULL DEFAULT 'widget',

    -- UTM Tracking
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    utm_term VARCHAR(255),
    utm_content VARCHAR(255),

    -- Metadata
    ip_address_hash VARCHAR(64),
    user_agent TEXT,
    referrer_url TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    contacted_at TIMESTAMP WITH TIME ZONE,
    converted_at TIMESTAMP WITH TIME ZONE,
    last_updated_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Scheduling
    scheduled_callback_at TIMESTAMP WITH TIME ZONE,
    scheduled_notes TEXT,
    contact_method contact_method DEFAULT 'PHONE',
    last_contact_attempt TIMESTAMP WITH TIME ZONE,
    contact_attempts INTEGER DEFAULT 0,
    next_follow_up_at TIMESTAMP WITH TIME ZONE,

    -- Contact Outcome
    contact_outcome contact_outcome_type NOT NULL DEFAULT 'NEW',
    follow_up_reason VARCHAR(100),
    follow_up_date TIMESTAMP WITH TIME ZONE,
    last_follow_up_sent_at TIMESTAMP WITH TIME ZONE,

    -- Referral
    is_referral BOOLEAN NOT NULL DEFAULT false,
    referring_provider_id UUID,
    referring_provider_raw JSONB
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    action audit_action NOT NULL,
    user_id UUID,
    user_email VARCHAR(255),
    user_ip_hash VARCHAR(64),
    endpoint VARCHAR(255),
    request_method VARCHAR(10),
    user_agent TEXT,
    old_values JSONB,
    new_values JSONB,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX idx_leads_lead_number ON leads(lead_number);
CREATE INDEX idx_leads_priority ON leads(priority);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_created_at ON leads(created_at DESC);
CREATE INDEX idx_leads_zip_code ON leads(zip_code);
CREATE INDEX idx_leads_in_service_area ON leads(in_service_area);
CREATE INDEX idx_leads_condition ON leads(condition);
CREATE INDEX idx_leads_score ON leads(score DESC);
CREATE INDEX idx_leads_deleted_at ON leads(deleted_at);
CREATE INDEX idx_leads_last_updated_at ON leads(last_updated_at);
CREATE INDEX idx_leads_is_referral ON leads(is_referral);
CREATE INDEX idx_leads_source ON leads(source);
CREATE INDEX idx_leads_contact_outcome ON leads(contact_outcome);
CREATE INDEX idx_leads_priority_status ON leads(priority, status);
CREATE INDEX idx_leads_service_area_priority ON leads(in_service_area, priority);
CREATE INDEX idx_audit_logs_table_record ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY leads_all_access ON leads FOR ALL USING (true);
CREATE POLICY audit_logs_all_access ON audit_logs FOR ALL USING (true);

COMMENT ON TABLE leads IS 'Sleep clinic patient intake leads with PHI encrypted at rest';
COMMENT ON TABLE audit_logs IS 'HIPAA-compliant audit trail for all PHI access';
