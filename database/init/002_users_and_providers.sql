-- =============================================================================
-- 002_users_and_providers.sql — Users, Providers, Notes, Settings
-- =============================================================================

-- User role enum
DO $$ BEGIN CREATE TYPE user_role AS ENUM ('administrator', 'coordinator', 'specialist'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE user_status AS ENUM ('active', 'inactive', 'pending'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role user_role NOT NULL DEFAULT 'coordinator',
    status user_status NOT NULL DEFAULT 'pending',
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

CREATE OR REPLACE FUNCTION update_users_updated_at() RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_users_updated_at();

-- User preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE PRIMARY KEY,
    notify_new_lead BOOLEAN NOT NULL DEFAULT TRUE,
    notify_hot_lead BOOLEAN NOT NULL DEFAULT TRUE,
    notify_daily_summary BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Clinic settings
CREATE TABLE IF NOT EXISTS clinic_settings (
    key VARCHAR(100) NOT NULL PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO clinic_settings (key, value) VALUES
    ('clinic_name',    'The Insomnia and Sleep Institute of Arizona'),
    ('clinic_address', '8330 E Hartford Drive, Suite 100, Scottsdale, Arizona 85255'),
    ('clinic_phone',   '(480) 745-3547'),
    ('clinic_email',   'info@sleeplessinarizona.com')
ON CONFLICT (key) DO NOTHING;

-- Seed Default Admin
INSERT INTO users (id, email, password_hash, first_name, last_name, role, status, must_change_password)
VALUES (
    gen_random_uuid(), 'admin@clinic.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.BWSP4e.m7M0yAi',
    'Clinic', 'Administrator', 'administrator', 'active', TRUE
) ON CONFLICT (email) DO NOTHING;

-- Provider enums
DO $$ BEGIN CREATE TYPE provider_specialty AS ENUM ('sleep_medicine', 'pulmonology', 'neurology', 'ent', 'psychiatry', 'primary_care', 'cardiology', 'pediatrics', 'other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE provider_status AS ENUM ('active', 'inactive', 'pending', 'archived'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE provider_contact_method AS ENUM ('email', 'phone', 'fax', 'portal'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Referring providers table
CREATE TABLE IF NOT EXISTS referring_providers (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    practice_name VARCHAR(255),
    specialty provider_specialty NOT NULL DEFAULT 'primary_care',
    specialty_other TEXT,
    email VARCHAR(255),
    phone VARCHAR(20),
    fax VARCHAR(20),
    address TEXT,
    preferred_contact provider_contact_method DEFAULT 'email',
    status provider_status NOT NULL DEFAULT 'active',
    notes TEXT,
    referral_count INTEGER NOT NULL DEFAULT 0,
    last_referral_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_providers_name ON referring_providers(name);
CREATE INDEX IF NOT EXISTS idx_providers_status ON referring_providers(status);
CREATE INDEX IF NOT EXISTS idx_providers_specialty ON referring_providers(specialty);

-- Add FK from leads to referring_providers
DO $$ BEGIN
    ALTER TABLE leads ADD CONSTRAINT fk_leads_referring_provider FOREIGN KEY (referring_provider_id) REFERENCES referring_providers(id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Lead notes table
CREATE TABLE IF NOT EXISTS lead_notes (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_name VARCHAR(200),
    content TEXT NOT NULL,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_notes_lead_id ON lead_notes(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_notes_created_at ON lead_notes(created_at DESC);

-- Provider notes history
CREATE TABLE IF NOT EXISTS provider_notes_history (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    provider_id UUID NOT NULL REFERENCES referring_providers(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_name VARCHAR(200),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_provider_notes_provider_id ON provider_notes_history(provider_id);

-- Password reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reset_tokens_token_hash ON password_reset_tokens(token_hash);

-- Invitation requests
CREATE TABLE IF NOT EXISTS invitation_requests (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invitation_requests_email ON invitation_requests(email);
CREATE INDEX IF NOT EXISTS idx_invitation_requests_status ON invitation_requests(status);

-- Add primary_admin to user_role if missing
DO $$ BEGIN ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'primary_admin' BEFORE 'administrator'; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
