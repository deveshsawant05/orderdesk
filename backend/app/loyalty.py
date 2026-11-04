"""Local mock SMS verification and transactional point accounting."""
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy.dialects.postgresql import insert

from .auth import customer, session_cookie, token_hash
from .db import get_db
from .models import DemoMessage, LoyaltyAccount, LoyaltyTransaction, OtpChallenge, Session, now
from .pricing import gst_inclusive
from .schemas import Strict

router = APIRouter(prefix='/auth/loyalty')
POINT_VALUE = 100
EARN_PER_PAISE = 10000
CAP_PERCENT = 20
DEMO_PHONE = r'^60000000[0-9]{2}$'


class Challenge(Strict):
    phone: str = Field(pattern=DEMO_PHONE)


class Verification(Challenge):
    code: str = Field(pattern=r'^[0-9]{6}$')


def browser_session(db, request, lock=False):
    key = token_hash(request.cookies.get(session_cookie(request), ''))
    session = db.get(Session, key, with_for_update=lock)
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Your guest session expired. Refresh before continuing.')
    return session


def verified_phone(db, request):
    session = browser_session(db, request)
    return session.verified_phone if session else None


def account_status(db, request):
    phone = verified_phone(db, request)
    account = db.get(LoyaltyAccount, phone) if phone else None
    return {
        'phone': phone, 'balance': account.balance if account else 0,
        'value_paise': POINT_VALUE, 'cap_percent': CAP_PERCENT,
        'demo_enabled': os.getenv('DEMO_MODE') == 'true',
    }


def require_demo():
    if os.getenv('DEMO_MODE') != 'true':
        raise HTTPException(404, 'Demo verification is disabled.')


@router.get('')
def balance(request: Request, user=Depends(customer), db=Depends(get_db)):
    return account_status(db, request)


@router.post('/challenge')
def challenge(body: Challenge, request: Request, user=Depends(customer), db=Depends(get_db)):
    require_demo()
    session = browser_session(db, request, lock=True)
    current = db.get(OtpChallenge, session.token_hash)
    instant = now()
    if current and current.expires_at - instant > timedelta(minutes=4, seconds=30):
        raise HTTPException(429, 'Wait 30 seconds before requesting a new code.')
    code = f'{secrets.randbelow(1000000):06}'
    if current is None:
        current = OtpChallenge(session_id=session.token_hash)
        db.add(current)
    current.phone = body.phone
    current.code_hash = token_hash(session.token_hash + code)
    current.expires_at = instant + timedelta(minutes=5)
    current.attempts = 0
    db.add(DemoMessage(kind='otp', destination=body.phone, body=code))
    db.commit()
    return {'queued': True, 'transport': 'mock-sms'}


@router.post('/verify')
def verify(body: Verification, request: Request, user=Depends(customer), db=Depends(get_db)):
    require_demo()
    session = browser_session(db, request, lock=True)
    current = db.get(OtpChallenge, session.token_hash)
    if not current or current.phone != body.phone or current.expires_at <= now() or current.attempts >= 5:
        raise HTTPException(422, 'Request a fresh demo code.')
    if not secrets.compare_digest(current.code_hash, token_hash(session.token_hash + body.code)):
        current.attempts += 1
        db.commit()
        raise HTTPException(422, 'That code is incorrect.')
    db.execute(insert(LoyaltyAccount).values(phone=body.phone, balance=0).on_conflict_do_nothing())
    session.verified_phone = body.phone
    db.delete(current)
    db.commit()
    return account_status(db, request)


def apply_redemption(db, totals, phone, points, coupon, lock=False):
    if not points:
        return None
    if not phone or coupon:
        raise HTTPException(422, 'Verify your mobile and remove the coupon before redeeming points.')
    account = db.get(LoyaltyAccount, phone, with_for_update=lock)
    discount = points * POINT_VALUE
    cap = totals['subtotal_paise'] * CAP_PERCENT // 100
    if not account or points > account.balance or discount > cap:
        raise HTTPException(422, 'Points exceed the verified balance or 20% of the food subtotal.')
    totals['discount_paise'] += discount
    totals['total_paise'] -= discount
    totals['gst_paise'] = gst_inclusive(totals['total_paise'])
    return account


def record_points(db, order, kind, points, account=None):
    if not order.loyalty_phone or not points:
        return
    if account is None:
        account = db.get(LoyaltyAccount, order.loyalty_phone, with_for_update=True)
    account.balance += points
    db.add(LoyaltyTransaction(phone=account.phone, order_id=order.id, kind=kind, points=points))
