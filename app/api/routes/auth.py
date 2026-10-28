from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.db.models import Tenant, User
from app.core.security import hash_password, verify_password, create_token
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignupRequest):
    with SessionLocal() as db:
        try:
            tenant = Tenant(name=body.company_name)
            db.add(tenant)
            db.flush()  # get tenant.id
            user = User(
                tenant_id=tenant.id,
                email=body.email.lower(),
                password_hash=hash_password(body.password),
                role="hr_admin",
            )
            db.add(user)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Company or email already registered")
        return TokenResponse(access_token=create_token(user))

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")
        return TokenResponse(access_token=create_token(user))