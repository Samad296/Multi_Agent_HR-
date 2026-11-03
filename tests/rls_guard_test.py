from sqlalchemy import text

from app.db.session import admin_engine

NO_RLS_BY_DESIGN = {"users"}   # login looks users up before a tenant is known


def test_tenant_tables_force_rls_and_have_policy():
    with admin_engine.connect() as c:
        tables = set(c.execute(text(
            "select table_name from information_schema.columns "
            "where table_schema = 'public' and column_name = 'tenant_id'"
        )).scalars()) - NO_RLS_BY_DESIGN
        assert tables, "no tenant tables found"
        flags = {r[0]: (r[1], r[2]) for r in c.execute(text(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class "
            "where relnamespace = 'public'::regnamespace and relkind = 'r'"))}
        policies = set(c.execute(text(
            "select tablename from pg_policies "
            "where schemaname = 'public' and policyname = 'tenant_isolation'"
        )).scalars())
    for t in tables:
        assert flags[t] == (True, True), f"{t}: RLS is not enabled and forced"
        assert t in policies, f"{t}: missing tenant_isolation policy"


def test_app_role_cannot_bypass_rls():
    with admin_engine.connect() as c:
        row = c.execute(text(
            "select rolsuper, rolbypassrls from pg_roles where rolname = 'app_user'"
        )).one()
    assert row == (False, False)