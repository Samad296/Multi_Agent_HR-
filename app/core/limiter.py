from slowapi import Limiter
from starlette.requests import Request

from app.core.security import decode_token


def ip_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def user_key(request: Request) -> str:
    """Limit per signed-in user; falls back to IP if the token is missing or invalid."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            c = decode_token(auth[7:])
            return f"{c['tid']}:{c['sub']}"
        except Exception:
            pass
    return ip_key(request)


limiter = Limiter(key_func=ip_key)