import random
import string
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio

from ..database import get_session
from ..models import User, Session
from ..config import settings
from ..services.comms.email import send_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str

class VerifyRequest(BaseModel):
    email: str
    otp: str

async def send_otp_email(to_email: str, otp: str):
    try:
        result = await send_email(to_email, "Login to Rael", f"Your login OTP for Rael is: {otp}")
    except Exception as e:
        result = {"sent": False, "error": str(e)}
    if not result.get("sent") or result.get("provider") == "mock":
        # No provider could deliver it — surface the OTP in the server logs
        # so the operator can still log in.
        configured = [
            name for name, key in [
                ("brevo", settings.brevo_api_key),
                ("resend", settings.resend_api_key),
                ("sendgrid", settings.sendgrid_api_key),
                ("smtp", settings.smtp_username),
            ] if key
        ]
        print(f"OTP email not delivered. configured={configured or 'none'} result={result}. OTP for {to_email} is {otp}")

@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_session)):
    email = req.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar()
    
    if not user:
        user = User(email=email)
        db.add(user)
        
    otp = "".join(random.choices(string.digits, k=6))
    user.otp = otp
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await db.commit()

    asyncio.create_task(send_otp_email(email, otp))


    return {"ok": True, "message": "OTP sent"}

@router.post("/verify")
async def verify(req: VerifyRequest, db: AsyncSession = Depends(get_session)):
    email = req.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar()
    
    if not user or user.otp != req.otp or not user.otp_expires_at:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    if user.otp_expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")
        
    user.is_verified = True
    user.otp = None
    user.otp_expires_at = None
    
    token = secrets.token_hex(32)
    session = Session(
        token=token,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)
    )
    db.add(session)
    await db.commit()
    
    return {"ok": True, "token": token, "onboarding_completed": user.onboarding_completed}

async def get_current_user(authorization: str = Header(None), db: AsyncSession = Depends(get_session)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    token = authorization.split(" ")[1]
    session = (await db.execute(select(Session).where(Session.token == token))).scalar()
    
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
        
    user = (await db.execute(select(User).where(User.id == session.user_id))).scalar()
    return user

@router.post("/logout")
async def logout(authorization: str = Header(None), db: AsyncSession = Depends(get_session)):
    """Invalidate the current session token server-side."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        session = (await db.execute(select(Session).where(Session.token == token))).scalar()
        if session:
            await db.delete(session)
            await db.commit()
    return {"ok": True}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {"email": user.email, "onboarding_completed": user.onboarding_completed}
