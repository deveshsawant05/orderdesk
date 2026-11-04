from datetime import timedelta
from sqlalchemy import select

from app.events import escalate_late
from app.models import DemoMessage, LoyaltyAccount, Outlet, PartyRequest, now
from .conftest import CONTACT, fill_cart, pay, signin
from .test_domain import by_ref


def verify_demo_mobile(client, db):
    response = client.post('/auth/loyalty/challenge', json={'phone': CONTACT['phone']})
    assert response.json() == {'queued': True, 'transport': 'mock-sms'}
    message = db.scalar(select(DemoMessage).where(DemoMessage.kind == 'otp'))
    assert client.post('/auth/loyalty/verify', json={
        'phone': CONTACT['phone'], 'code': '000000' if message.body != '000000' else '999999',
    }).status_code == 422
    response = client.post('/auth/loyalty/verify', json={'phone': CONTACT['phone'], 'code': message.body})
    assert response.status_code == 200, response.text


def test_loyalty_requires_verified_session_then_earns_and_restores(client, db):
    signin(client)
    cart = fill_cart(client)
    request = {'method': 'Card', 'idempotency_key': 'loyalty-payment', 'cart_version': cart['version'],
               'redeem_points': 1, **CONTACT}
    assert client.post('/payments', json=request).status_code == 422
    verify_demo_mobile(client, db)
    assert client.post('/payments', json=request).status_code == 422
    _, first = pay(client, cart, 'first-order')
    first = first['order']
    signin(client, 'manager', 'kondapur')
    assert client.post(f"/orders/{first['id']}/status", json={'version':1,'status':'preparing'}).status_code == 200
    signin(client, 'kitchen', 'kondapur')
    assert client.post(f"/orders/{first['id']}/status", json={'version':2,'status':'ready'}).status_code == 200
    assert client.post(f"/orders/{first['id']}/status", json={'version':3,'status':'handed_off'}).status_code == 200
    assert client.post(f"/orders/{first['id']}/status", json={'version':3,'status':'handed_off'}).status_code == 409

    signin(client)
    assert client.get('/auth/loyalty').json()['balance'] == 3
    cart = fill_cart(client)
    request['cart_version'] = cart['version']
    response = client.post('/payments', json=request)
    assert response.status_code == 200, response.text
    assert response.json()['amount_paise'] == 35900
    payment_id = response.json()['id']
    confirm = client.post(f'/payments/{payment_id}/confirm', json={'outcome':'success'}).json()
    second = confirm['order']
    assert client.get('/auth/loyalty').json()['balance'] == 2
    assert client.post(f'/payments/{payment_id}/confirm', json={'outcome':'success'}).json()['order']['id'] == second['id']
    signin(client, 'manager', 'kondapur')
    response = client.post(f"/orders/{second['id']}/status", json={
        'version':1, 'status':'cancelled', 'reason':'Kitchen capacity',
    })
    assert response.status_code == 200, response.text
    assert response.json()['refunded_at']
    db.expire_all()
    assert db.get(LoyaltyAccount, CONTACT['phone']).balance == 3
    stats = client.get('/staff/report?outlet_id=kondapur').json()
    assert stats['orders'] == 2 and stats['cancelled'] == 1
    assert stats['median_prep_minutes'] is not None
    assert client.get('/staff/report?outlet_id=kukatpally').status_code == 403


def test_party_notice_scope_and_confirmation(client, db):
    outlet = db.get(Outlet, 'kondapur')
    request = {**CONTACT, 'address':'Synthetic gathering venue', 'lat':outlet.lat, 'lng':outlet.lng,
               'scheduled_at':(now()+timedelta(hours=47)).isoformat(),
               'items':[{'item_id':'chicken','quantity':12}]}
    assert client.post('/party', json=request).status_code == 422
    request['scheduled_at'] = (now()+timedelta(days=3)).isoformat()
    response = client.post('/party', json=request)
    assert response.status_code == 200, response.text
    token = response.json()['token']
    party = db.scalar(select(PartyRequest).where(PartyRequest.token == token))
    assert client.get('/party/tracking/'+token).json()['status'] == 'pending'
    assert client.get('/party/tracking/'+party.id).status_code == 404
    signin(client, 'kitchen', 'kondapur')
    assert client.get('/staff/party?outlet_id=kondapur').json() == []
    signin(client, 'manager', 'kukatpally')
    assert client.post('/staff/party/'+party.id,json={'status':'accepted'}).status_code == 403
    signin(client, 'manager', 'kondapur')
    assert client.post('/staff/party/'+party.id,json={'status':'accepted'}).status_code == 200
    assert client.post('/staff/party/'+party.id,json={'status':'rejected','reason':'Too many guests'}).status_code == 409
    assert client.get('/party/tracking/'+token).json()['status'] == 'accepted'
    signin(client, 'kitchen', 'kondapur')
    assert client.get('/staff/party?outlet_id=kondapur').json()[0]['items'][0]['quantity'] == 12


def test_tracking_identifier_and_current_promise(client, db):
    signin(client)
    _, result = pay(client, fill_cart(client))
    public_order = result['order']
    order = by_ref(db, public_order['id'])
    assert order.id != order.public_ref and order.daily_number == public_order['daily_number']
    assert client.get('/tracking/'+order.public_ref).status_code == 404
    assert client.get('/tracking/'+order.tracking_token).json()['id'] == order.public_ref
    order.promised_at = now() - timedelta(minutes=15)
    order.revised_at = now() + timedelta(minutes=10)
    db.commit()
    assert escalate_late(db) == 0
