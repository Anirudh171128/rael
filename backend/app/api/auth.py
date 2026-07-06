import smtplib
import random
import string
import secrets
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio

from ..database import get_session
from ..models import User, Session
from ..config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str

class VerifyRequest(BaseModel):
    email: str
    otp: str

def send_otp_email(to_email: str, otp: str):
    msg = EmailMessage()
    msg.set_content(f"Your login OTP for Rael is: {otp}")
    msg["Subject"] = "Login to Rael"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

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

    if settings.smtp_username:
        asyncio.create_task(asyncio.to_thread(send_otp_email, email, otp))
    else:
        print(f"SMTP not configured. OTP for {email} is {otp}")
        
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
