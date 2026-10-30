import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import chat as chat_route
from app.core.config import settings
from app.core.limiter import limiter
from app.core.security import create_token
from app.db.models import Tenant, User
from app.db.session import admin_engine
from app.main import app


class FakeGraph:
    """Stands in for the AI flow, so these tests never call Groq."""
    def invoke(self, state, config):
        return {"answer": "ok", "intent": "policy", "citations": []}


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter.reset()       # the counters live in memory and are shared between tests
    yield
    limiter.reset()


def make_user_token() -> str:
    with Session(admin_engine) as db:
        t = Tenant(name=f"RateTest {uuid.uuid4().hex[:8]}")
        db.add(t)
        db.flush()
        u = User(tenant_id=t.id, email=f"{uuid.uuid4().hex[:8]}@rate.test",
                 password_hash="x", role="employee")
        db.add(u)
        db.flush()
        token = create_token(u)
        db.commit()
    return token


def test_login_is_rate_limited():
    c = TestClient(app)
    codes = [
        c.post("/auth/login", json={"email": "nobody@example.com", "password": "wrongpass1"}).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


def test_chat_per_user_limit(monkeypatch):
    monkeypatch.setattr(chat_route, "get_graph", lambda: FakeGraph())
    monkeypatch.setattr(settings, "CHAT_DAILY_LIMIT", 1000)
    c = TestClient(app)
    h = {"Authorization": f"Bearer {make_user_token()}"}
    codes = [c.post("/chat", json={"message": "hello"}, headers=h).status_code for _ in range(22)]
    assert codes[:20] == [200] * 20
    assert 429 in codes[20:]


def test_company_daily_cap(monkeypatch):
    monkeypatch.setattr(chat_route, "get_graph", lambda: FakeGraph())
    monkeypatch.setattr(settings, "CHAT_DAILY_LIMIT", 1)
    c = TestClient(app)
    h = {"Authorization": f"Bearer {make_user_token()}"}
    assert c.post("/chat", json={"message": "first"}, headers=h).status_code == 200
    assert c.post("/chat", json={"message": "second"}, headers=h).status_code == 429