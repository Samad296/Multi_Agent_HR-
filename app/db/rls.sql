-- Run as the postgres owner, connected to the eka database.
-- Before running, replace CHANGE_ME_STRONG_PASSWORD with the password
-- you put in APP_DATABASE_URL in .env.

-- 1. Restricted runtime role (not a superuser, so RLS applies to it)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user LOGIN;
  END IF;
END $$;

ALTER ROLE app_user WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'CHANGE_ME_STRONG_PASSWORD';

-- 2. Base privileges
GRANT CONNECT ON DATABASE eka TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;

-- 3. Audit log is append-only for the app
REVOKE UPDATE, DELETE ON audit_log FROM app_user;

-- 4. Leftover table from another project: not reachable by the app
DO $$ BEGIN
  IF to_regclass('public.documents') IS NOT NULL THEN
    EXECUTE 'REVOKE ALL ON documents FROM app_user';
  END IF;
END $$;

-- 5. Tenant isolation on every tenant-scoped table
--    (add new tenant tables to this list, e.g. policy_documents later)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leave_types','leave_balances','leave_requests','audit_log'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I
         USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)
         WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)', t);
  END LOOP;
END $$;