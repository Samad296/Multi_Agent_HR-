from sqlalchemy import text

from app.db.session import admin_engine

SQL = text("""
select r.rolname, c.relname,
       has_table_privilege(r.rolname, c.oid, 'SELECT') as sel,
       has_table_privilege(r.rolname, c.oid, 'INSERT') as ins,
       has_table_privilege(r.rolname, c.oid, 'UPDATE') as upd,
       has_table_privilege(r.rolname, c.oid, 'DELETE') as del
from pg_class c
cross join pg_roles r
where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
  and r.rolname in ('anon', 'authenticated', 'service_role', 'app_user')
order by r.rolname, c.relname
""")

with admin_engine.connect() as c:
    rows = c.execute(SQL).all()

api_open = 0
for role, table, sel, ins, upd, dele in rows:
    flags = "".join(f for f, on in (("S", sel), ("I", ins), ("U", upd), ("D", dele)) if on) or "-"
    print(f"{role:14} {table:18} {flags}")
    if role != "app_user" and flags != "-":
        api_open += 1
print("\nAPI roles with access to our tables:", api_open)