-- Life Admin — Initial Schema
-- Run once on fresh database. Alembic manages subsequent changes.
-- ─────────────────────────────────────────────────────────────────────────────

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Enums ───────────────────────────────────────────────────────────────────

CREATE TYPE bill_status AS ENUM (
    'detected',
    'extracted',
    'review_required',
    'confirmed',
    'reminded',
    'paid',
    'cancelled',
    'failed'
);

CREATE TYPE action_type AS ENUM (
    'reminder_email',
    'reminder_sms',
    'reminder_whatsapp',
    'calendar_event',
    'payment_initiated',
    'subscription_cancelled',
    'optimize_suggestion'
);

CREATE TYPE action_status AS ENUM ('pending', 'success', 'failed', 'skipped');

-- ─── Users ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

-- ─── OAuth Tokens (encrypted at rest) ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,
    access_token    BYTEA NOT NULL,
    refresh_token   BYTEA NOT NULL,
    token_expiry    TIMESTAMPTZ NOT NULL,
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- ─── Raw Emails ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_emails (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id  TEXT NOT NULL,
    thread_id   TEXT,
    subject     TEXT,
    sender      TEXT,
    received_at TIMESTAMPTZ,
    s3_key      TEXT NOT NULL,
    processed   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_emails_user_processed ON raw_emails(user_id, processed);

-- ─── Bills ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bills (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    raw_email_id         UUID REFERENCES raw_emails(id),
    provider             TEXT NOT NULL,
    bill_type            TEXT NOT NULL,
    amount               NUMERIC(12, 2),
    currency             TEXT NOT NULL DEFAULT 'INR',
    due_date             DATE,
    billing_period_start DATE,
    billing_period_end   DATE,
    account_number       TEXT,
    status               bill_status NOT NULL DEFAULT 'detected',
    extraction_confidence NUMERIC(4, 3),
    extraction_model     TEXT,
    extraction_raw       JSONB,
    is_overdue           BOOLEAN NOT NULL DEFAULT FALSE,
    is_recurring         BOOLEAN NOT NULL DEFAULT FALSE,
    needs_review         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bills_user_status ON bills(user_id, status);
CREATE INDEX IF NOT EXISTS idx_bills_due_date ON bills(due_date)
    WHERE status NOT IN ('paid', 'cancelled');

-- ─── Bill State Transitions (audit log) ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS bill_transitions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bill_id     UUID NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    from_status bill_status,
    to_status   bill_status NOT NULL,
    reason      TEXT,
    actor       TEXT NOT NULL DEFAULT 'system',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bill_transitions_bill ON bill_transitions(bill_id);

-- ─── Actions ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bill_id         UUID REFERENCES bills(id),
    action_type     action_type NOT NULL,
    status          action_status NOT NULL DEFAULT 'pending',
    idempotency_key TEXT NOT NULL UNIQUE,
    payload         JSONB NOT NULL DEFAULT '{}',
    result          JSONB,
    error_message   TEXT,
    attempted_at    TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actions_idempotency ON actions(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_actions_bill ON actions(bill_id);
CREATE INDEX IF NOT EXISTS idx_actions_user_status ON actions(user_id, status);

-- ─── Auto-update updated_at trigger ──────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_oauth_tokens_updated_at
    BEFORE UPDATE ON oauth_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_bills_updated_at
    BEFORE UPDATE ON bills
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─── Row-Level Security ───────────────────────────────────────────────────────

ALTER TABLE raw_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills ENABLE ROW LEVEL SECURITY;
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_tokens ENABLE ROW LEVEL SECURITY;

-- Policy: app sets app.current_user_id; RLS enforces isolation
CREATE POLICY IF NOT EXISTS user_isolation_raw_emails ON raw_emails
    USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);

CREATE POLICY IF NOT EXISTS user_isolation_bills ON bills
    USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);

CREATE POLICY IF NOT EXISTS user_isolation_actions ON actions
    USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);

CREATE POLICY IF NOT EXISTS user_isolation_oauth ON oauth_tokens
    USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);

-- ─── Transactions ────────────────────────────────────────────────────────────

CREATE TYPE transaction_type AS ENUM ('debit', 'credit');

CREATE TYPE transaction_category AS ENUM (
    'food', 'transport', 'shopping', 'entertainment',
    'utilities', 'healthcare', 'education', 'travel',
    'subscriptions', 'other'
);

CREATE TABLE IF NOT EXISTS transactions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_id             TEXT,
    amount               NUMERIC(12, 2) NOT NULL,
    type                 transaction_type NOT NULL DEFAULT 'debit',
    merchant             TEXT,
    category             transaction_category NOT NULL DEFAULT 'other',
    date                 DATE NOT NULL,
    source               TEXT,
    raw_text             TEXT,
    extraction_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, email_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions(user_id, category);

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS user_isolation_transactions ON transactions
    USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);

-- ─── Default dev user ─────────────────────────────────────────────────────────
-- Remove this in production! For local dev only.
INSERT INTO users (id, email, full_name, timezone)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'dev@lifeadmin.local',
    'Dev User',
    'Asia/Kolkata'
) ON CONFLICT (email) DO NOTHING;
