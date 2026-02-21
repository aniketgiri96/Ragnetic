"""Auth routes: register, login."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.api.deps import get_db_session
from app.models.document import KnowledgeBaseMembership
from app.services.access import bootstrap_user_kb
from app.services.rate_limit import enforce_rate_limit
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


def _hash(password: str) -> str:
    return pwd_context.hash(password)


def _verify(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/register")
def register(body: RegisterBody, request: Request, db: Session = Depends(get_db_session)):
    ip = request.client.host if request.client else "unknown"
    enforce_rate_limit("auth:register", key=f"ip:{ip}:email:{body.email.lower()}")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = User(email=body.email, password_hash=_hash(body.password))
    db.add(user)
    db.flush()
    bootstrap_user_kb(db, user)
    db.commit()
    return {"message": "Registered"}


@router.post("/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db_session)):
    ip = request.client.host if request.client else "unknown"
    enforce_rate_limit("auth:login", key=f"ip:{ip}:email:{body.email.lower()}")
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not _verify(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not db.query(KnowledgeBaseMembership).filter(KnowledgeBaseMembership.user_id == user.id).first():
        bootstrap_user_kb(db, user)
        db.commit()
    return {"access_token": _create_token(user.email), "token_type": "bearer"}
