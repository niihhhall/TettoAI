-- CodeVerity Neon Postgres schema (PRD §4)
-- Idempotent: safe to run repeatedly. Enhancements over the PRD are marked [DE-RISK].

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- provides gen_random_uuid()

-- 1. Contractor Company Accounts
CREATE TABLE IF NOT EXISTS companies (
    company_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name    VARCHAR(255) NOT NULL,
    invite_code     VARCHAR(50) UNIQUE NOT NULL,          -- e.g. '4821' or 'APEX'
    crm_type        VARCHAR(50) DEFAULT 'JobNimbus',
    crm_webhook_url TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Crew Members (Foremen / Subcontractors)
CREATE TABLE IF NOT EXISTS crew_members (
    crew_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    phone_number          VARCHAR(20) UNIQUE NOT NULL,      -- E.164 (+12145550199)
    full_name             VARCHAR(255) NOT NULL,
    preferred_language    VARCHAR(5) DEFAULT 'en',
    role                  VARCHAR(50) DEFAULT 'Foreman',
    total_bounties_earned DECIMAL(10,2) DEFAULT 0.00,
    last_inbound_at       TIMESTAMP WITH TIME ZONE,         -- [DE-RISK] 24h WhatsApp session window
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Instant phone-number authentication lookup (<5ms)
CREATE INDEX IF NOT EXISTS idx_crew_members_phone ON crew_members(phone_number);

-- 3. Jobsites
CREATE TABLE IF NOT EXISTS jobsites (
    job_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id            UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    claim_number          VARCHAR(100),
    property_address      TEXT NOT NULL,
    zip_code              VARCHAR(10) NOT NULL,
    city                  VARCHAR(100) NOT NULL,
    state                 VARCHAR(2) NOT NULL,
    county                VARCHAR(100),                     -- [DE-RISK] dual-layer geofence (§3.5)
    municipal_code_summary TEXT,                            -- pre-fetched city building codes
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Foreman-created jobsites (auto-created from a GPS pin) may not carry every field, so the
-- claim-time NOT NULLs are relaxed. property_address is always present (the geocoded address).
ALTER TABLE jobsites ALTER COLUMN zip_code DROP NOT NULL;
ALTER TABLE jobsites ALTER COLUMN city DROP NOT NULL;
ALTER TABLE jobsites ALTER COLUMN state DROP NOT NULL;

-- 4. Inspection Sessions (state machine)
CREATE TABLE IF NOT EXISTS inspection_sessions (
    session_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crew_id               UUID REFERENCES crew_members(crew_id) ON DELETE CASCADE,
    job_id                UUID REFERENCES jobsites(job_id) ON DELETE SET NULL,
    current_state         VARCHAR(50) DEFAULT 'STATE_0_AUTH',
    approved_photos       JSONB DEFAULT '[]'::jsonb,        -- array of R2 public URLs
    photo_evidence        JSONB DEFAULT '[]'::jsonb,        -- per-photo evidence records (caption/damage/codes/voice)
    voice_note_url        TEXT,
    transcription_text    TEXT,
    structured_line_items JSONB DEFAULT '[]'::jsonb,        -- Xactimate line items
    pdf_url               TEXT,
    bounty_status         VARCHAR(20) DEFAULT 'PENDING',    -- PENDING, APPROVED, PAID
    crm_status            VARCHAR(20),                      -- delivered / failed / skipped
    crm_response_at       TIMESTAMP WITH TIME ZONE,
    supplement_value      DECIMAL(12,2),                    -- $ value once priced
    created_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Forward-compatible columns for databases created before these were added.
ALTER TABLE inspection_sessions ADD COLUMN IF NOT EXISTS photo_evidence JSONB DEFAULT '[]'::jsonb;
ALTER TABLE inspection_sessions ADD COLUMN IF NOT EXISTS crm_status VARCHAR(20);
ALTER TABLE inspection_sessions ADD COLUMN IF NOT EXISTS crm_response_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE inspection_sessions ADD COLUMN IF NOT EXISTS supplement_value DECIMAL(12,2);

-- Fast lookup of a crew member's active session
CREATE INDEX IF NOT EXISTS idx_sessions_crew ON inspection_sessions(crew_id);

-- Auto-maintain updated_at on inspection_sessions
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sessions_updated_at ON inspection_sessions;
CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON inspection_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 5. Operators (office console users). Company-scoped; auth via password hash + JWT.
CREATE TABLE IF NOT EXISTS operators (
    operator_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(company_id) ON DELETE CASCADE,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          VARCHAR(50) DEFAULT 'operator',
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operators_email ON operators(email);
