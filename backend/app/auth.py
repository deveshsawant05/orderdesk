import os, secrets, hashlib
from datetime import timedelta
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import User, Session, now

hasher = PasswordHasher()
COOKIE = 'orderdesk_session'
STAFF_COOKIE = 'orderdesk_staff'


def session_cookie(request):
    scope = request.headers.get('X-OrderDesk-Experience') or request.query_params.get('scope')
    return STAFF_COOKIE if scope == 'staff' else COOKIE

def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()

def create_session(db, user, response: Response):
    token = secrets.token_urlsafe(32)
    lifetime = 30*24*3600 if user.role == "customer" else 12*3600
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=now()+timedelta(seconds=lifetime)))
    db.commit()
    response.set_cookie(COOKIE if user.role == 'customer' else STAFF_COOKIE, token, httponly=True, secure=os.getenv('COOKIE_SECURE') == 'true', samesite='lax', max_age=lifetime, path='/')

def current_user(request: Request, db: DBSession = Depends(get_db)):
    token = request.cookies.get(session_cookie(request), '')
    session = db.get(Session, token_hash(token))
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Please sign in to continue.')
    return db.get(User, session.user_id)

def customer(user: User = Depends(current_user)):
    if user.role != 'customer':
        raise HTTPException(403, 'Sign in with a customer account to order.')
    return user

def admin(user: User = Depends(current_user)):
    if not central_manager(user):
        raise HTTPException(403, 'Central menu permission is required.')
    return user

def central_manager(user):
    return user.role == 'manager' and user.can_manage


def staff_outlet(user, outlet_id):
    if not central_manager(user) and not (user.role in ('manager', 'kitchen') and user.outlet_id == outlet_id):
        raise HTTPException(403, 'You do not have access to this kitchen.')

def user_json(user):
    return {k:getattr(user,k) for k in ['id','email','name','role','outlet_id','can_manage','marketing_consent','demo']}


def customer_history_phone(db, request, user):
    """Resolve history identity from the session, never from an orders query parameter."""
    if user.role != 'customer' or not user.contact_phone:
        return None
    session=db.get(Session,token_hash(request.cookies.get(session_cookie(request),'')))
    if not session or session.user_id != user.id or session.expires_at <= now():
        return None
    if session.verified_phone == user.contact_phone or os.getenv('MOBILE_LOGIN_SKIP_OTP','false') == 'true':
        return user.contact_phone
    return None
