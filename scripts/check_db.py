from sqlalchemy import text

from app.db.session import admin_engine, engine

with admin_engine.connect() as a, engine.connect() as b:
    print(a.execute(text("select current_user")).scalar(), b.execute(text("select current_user")).scalar())