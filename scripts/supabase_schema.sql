-- ============================================================
-- Fix script: drop old policies + recreate with correct vector type
-- Run this in: Supabase Dashboard → SQL Editor
-- ============================================================

-- Drop old policies first
DROP POLICY IF EXISTS "service_role_only" ON admin_users;
DROP POLICY IF EXISTS "service_role_only" ON employees;
DROP POLICY IF EXISTS "service_role_only" ON embeddings;
DROP POLICY IF EXISTS "service_role_only" ON attendance;
DROP POLICY IF EXISTS "service_role_only" ON unknown_faces;

-- Fix embeddings vector column from TEXT to FLOAT[]
-- (only runs if column is still TEXT type)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'embeddings'
    AND column_name = 'vector'
    AND data_type = 'text'
  ) THEN
    ALTER TABLE embeddings ALTER COLUMN vector TYPE FLOAT[] USING vector::FLOAT[];
  END IF;
END $$;

-- Recreate all tables that may be missing
CREATE TABLE IF NOT EXISTS admin_users (
    id              SERIAL PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'viewer',
    department      TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employees (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    department  TEXT NOT NULL DEFAULT 'General',
    role        TEXT NOT NULL DEFAULT 'employee',
    shift_start TEXT NOT NULL DEFAULT '09:00',
    shift_end   TEXT NOT NULL DEFAULT '17:00',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS embeddings (
    id          SERIAL PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    vector      FLOAT[] NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attendance (
    id              SERIAL PRIMARY KEY,
    employee_id     TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    check_in_time   TIMESTAMPTZ,
    check_out_time  TIMESTAMPTZ,
    total_hours     FLOAT,
    status          TEXT NOT NULL DEFAULT 'Present',
    confidence      FLOAT,
    UNIQUE (employee_id, date)
);

CREATE TABLE IF NOT EXISTS unknown_faces (
    id                SERIAL PRIMARY KEY,
    timestamp         TIMESTAMPTZ DEFAULT NOW(),
    snapshot_url      TEXT,
    imagekit_file_id  TEXT,
    resolved          BOOLEAN NOT NULL DEFAULT FALSE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_embeddings_employee   ON embeddings(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date       ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_attendance_employee   ON attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_status     ON attendance(status);
CREATE INDEX IF NOT EXISTS idx_unknown_faces_resolved ON unknown_faces(resolved);

-- Re-enable RLS
ALTER TABLE admin_users   ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees     ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeddings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance    ENABLE ROW LEVEL SECURITY;
ALTER TABLE unknown_faces ENABLE ROW LEVEL SECURITY;

-- Recreate policies
CREATE POLICY "service_role_only" ON admin_users   USING (auth.role() = 'service_role');
CREATE POLICY "service_role_only" ON employees     USING (auth.role() = 'service_role');
CREATE POLICY "service_role_only" ON embeddings    USING (auth.role() = 'service_role');
CREATE POLICY "service_role_only" ON attendance    USING (auth.role() = 'service_role');
CREATE POLICY "service_role_only" ON unknown_faces USING (auth.role() = 'service_role');