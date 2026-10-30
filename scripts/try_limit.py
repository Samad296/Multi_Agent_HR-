from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
codes = [
    c.post("/auth/login", json={"email": "nobody@example.com", "password": "wrongpass1"}).status_code
    for _ in range(12)
]
print(codes)