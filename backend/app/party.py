"""Catering feasibility requests and a confirmed kitchen schedule."""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field
from sqlalchemy import select

from .auth import current_user, staff_outlet
from .db import get_db
from .events import emit
from .models import DemoMessage, MenuItem, Outlet, PartyRequest, now
from .pricing import eligible_outlets
from .schemas import Strict

router = APIRouter()
NOTICE_HOURS = 48


class PartyLine(Strict):
    item_id: str = Field(min_length=1, max_length=50)
    quantity: int = Field(ge=1, le=200)


class PartyInput(Strict):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=r'^[6-9][0-9]{9}$')
    address: str = Field(min_length=5, max_length=300)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    scheduled_at: AwareDatetime
    items: list[PartyLine] = Field(min_length=1, max_length=20)
    notes: str = Field(default='', max_length=500)


class PartyDecision(Strict):
    status: Literal['accepted', 'rejected']
    reason: str = Field(default='', max_length=300)


def public_party(db, party):
    outlet = db.get(Outlet, party.outlet_id)
    return {
        'outlet_name': outlet.name, 'status': party.status, 'reason': party.reason,
        'scheduled_at': party.scheduled_at, 'items': party.items, 'fssai': outlet.fssai,
    }


def find_party(db, token):
    party = db.scalar(select(PartyRequest).where(PartyRequest.token == token))
    if party is None:
        raise HTTPException(404, 'Party tracking link not found.')
    return party


@router.get('/party/policy')
def policy():
    return {'notice_hours': NOTICE_HOURS}


@router.post('/party')
def submit(body: PartyInput, db=Depends(get_db)):
    if body.scheduled_at < now() + timedelta(hours=NOTICE_HOURS):
        raise HTTPException(422, f'Party orders require at least {NOTICE_HOURS} hours of notice.')
    choices = eligible_outlets(db, body.lat, body.lng)
    if not choices:
        raise HTTPException(422, 'The delivery point is outside our service area.')
    items = []
    selected = set()
    for line in body.items:
        item = db.get(MenuItem, line.item_id)
        if not item or not item.active or item.id in selected:
            raise HTTPException(422, 'Choose distinct items from the current menu.')
        selected.add(item.id)
        items.append({'item_id': item.id, 'name': item.name, 'quantity': line.quantity})
    party = PartyRequest(
        outlet_id=choices[0][1].id, name=body.name, phone=body.phone, address=body.address,
        scheduled_at=body.scheduled_at, notes=body.notes, items=items,
    )
    db.add(party)
    db.flush()
    emit(db, 'party.created', outlet_id=party.outlet_id, party_id=party.id)
    db.add(DemoMessage(kind='party', destination=party.phone, body='Party request received. Awaiting manager confirmation.'))
    db.commit()
    return {**public_party(db, party), 'token': party.token}


@router.get('/party/tracking/{token}')
def track(token: str, db=Depends(get_db)):
    return public_party(db, find_party(db, token))


@router.get('/staff/party')
def queue(outlet_id: str, user=Depends(current_user), db=Depends(get_db)):
    staff_outlet(user, outlet_id)
    query = select(PartyRequest).where(PartyRequest.outlet_id == outlet_id)
    if user.role == 'kitchen':
        query = query.where(PartyRequest.status == 'accepted', PartyRequest.scheduled_at >= now())
    rows = db.scalars(query.order_by(PartyRequest.scheduled_at).limit(100))
    return [
        {
            **public_party(db, party), 'id': party.id,
            **({'name': party.name, 'address': party.address, 'notes': party.notes} if user.role == 'manager' else {}),
        } for party in rows
    ]


@router.post('/staff/party/{party_id}')
def decide(party_id: str, body: PartyDecision, user=Depends(current_user), db=Depends(get_db)):
    if user.role != 'manager':
        raise HTTPException(403, 'Manager access is required.')
    party = db.get(PartyRequest, party_id, with_for_update=True)
    if not party:
        raise HTTPException(404, 'Party request not found.')
    staff_outlet(user, party.outlet_id)
    if party.status != 'pending':
        raise HTTPException(409, 'This request already has a decision.')
    if body.status == 'rejected' and len(body.reason) < 3:
        raise HTTPException(422, 'Provide a reason for the customer.')
    if body.status == 'accepted' and party.scheduled_at <= now():
        raise HTTPException(409, 'The requested time has already passed.')
    party.status = body.status
    party.reason = body.reason or None
    emit(db, 'party.updated', outlet_id=party.outlet_id, party_id=party.id)
    message = f'Party request {party.status}. {body.reason}'.strip()
    db.add(DemoMessage(kind='party', destination=party.phone, body=message))
    db.commit()
    return public_party(db, party)
