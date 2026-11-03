"""rls policies, grants and audit index

Revision ID: 31e72c4c5dfe
Revises: c7ac02d686d8
Create Date: 2026-11-03 14:49:36.533462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31e72c4c5dfe'
down_revision: Union[str, Sequence[str], None] = 'c7ac02d686d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = ["leave_types", "leave_balances", "leave_requests", "audit_log"]


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
            RAISE EXCEPTION 'Role app_user does not exist. Create it first (see README).';
          END IF;
        END $$;
    """)

    # the app's runtime role: data access only, never a superuser
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user")
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM app_user")   # audit log is append-only
    op.execute("REVOKE ALL ON alembic_version FROM app_user")
    op.execute("""
        DO $$ BEGIN
          IF to_regclass('public.documents') IS NOT NULL THEN
            REVOKE ALL ON public.documents FROM app_user;   -- leftover table, not part of this app
          END IF;
        END $$;
    """)

    # tenant isolation on every tenant table
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {t}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)

    # Supabase only: keep its public REST API away from our tables
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated, service_role;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              REVOKE ALL ON TABLES FROM anon, authenticated, service_role;
          END IF;
        END $$;
    """)

    op.create_index("ix_audit_log_tenant_action_created", "audit_log",
                    ["tenant_id", "action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_tenant_action_created", table_name="audit_log")
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_user")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user")
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_user")
