-- Migration 002: Add transactions table for AI Expense Intelligence

DO $$ BEGIN
    CREATE TYPE transaction_type AS ENUM ('debit', 'credit');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE transaction_category AS ENUM (
        'food', 'transport', 'shopping', 'entertainment',
        'utilities', 'healthcare', 'education', 'travel',
        'subscriptions', 'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS transactions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_id              TEXT,
    amount                NUMERIC(12, 2) NOT NULL,
    type                  transaction_type NOT NULL DEFAULT 'debit',
    merchant              TEXT,
    category              transaction_category NOT NULL DEFAULT 'other',
    date                  DATE NOT NULL,
    source                TEXT,
    raw_text              TEXT,
    extraction_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, email_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions(user_id, category);

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'transactions' AND policyname = 'user_isolation_transactions'
    ) THEN
        CREATE POLICY user_isolation_transactions ON transactions
            USING (user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID);
    END IF;
END $$;
