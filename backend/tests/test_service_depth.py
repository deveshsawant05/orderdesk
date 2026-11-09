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


def test_loyalty_requires_verified_session_then_earns_and_restores(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_MODE","true")
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
               'scheduled_at':(now()+timedelta(hours=5,minutes=59)).isoformat(),
               'items':[{'item_id':'chicken','quantity':12}]}
    assert client.post('/party', json=request).status_code == 422
    request['scheduled_at'] = (now()+timedelta(hours=6,minutes=1)).isoformat()
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


def test_saved_checkout_profile_is_private_and_persists_contact(client, db):
    assert client.get('/auth/profile').status_code == 401
    response = client.post('/auth/guest')
    assert 'Max-Age=2592000' in response.headers['set-cookie']
    assert client.get('/auth/profile').json()['phone'] == ''
    cart = fill_cart(client)
    payment = client.post('/payments', json={
        'method':'UPI', 'idempotency_key':'saved-profile', 'cart_version':cart['version'],
        **CONTACT, 'marketing_consent':True,
    }).json()
    assert client.post('/payments/'+payment['id']+'/confirm', json={'outcome':'success'}).status_code == 200
    profile = client.get('/auth/profile').json()
    assert profile['name'] == CONTACT['name'] and profile['phone'] == CONTACT['phone']
    assert profile['address'] == cart['address'] and profile['marketing_consent'] is True
    assert client.get('/cart').json()['address'] == cart['address']
    client.cookies.clear()
    signin(client)
    assert client.get('/auth/profile').json()['phone'] == ''
    signin(client, 'kitchen', 'kondapur')
    assert client.get('/auth/profile').status_code == 403


def test_kitchen_adjustment_is_scoped_versioned_and_has_no_promise_history(client, db):
    from app.models import Override, Event
    signin(client)
    _, paid = pay(client, fill_cart(client))
    order = paid['order']
    signin(client, 'kitchen', 'kukatpally')
    assert client.post('/orders/'+order['id']+'/adjust-time', json={'version':1,'delta_minutes':5}).status_code == 403
    signin(client, 'kitchen', 'kondapur')
    response=client.post('/orders/'+order['id']+'/adjust-time', json={'version':1,'delta_minutes':5})
    assert response.status_code == 200
    assert response.json()['version'] == 2
    assert client.post('/orders/'+order['id']+'/adjust-time', json={'version':1,'delta_minutes':5}).status_code == 409
    actual=by_ref(db,order['id'])
    assert db.scalar(select(Override).where(Override.order_id==actual.id)) is None
    event=db.scalar(select(Event).where(Event.order_id==actual.id,Event.kind=='order.eta_updated'))
    assert event and event.payload['message']


def test_unverified_contact_does_not_recover_another_customers_orders(client, db, monkeypatch):
    signin(client)
    pay(client,fill_cart(client))
    client.cookies.clear()
    signin(client)
    monkeypatch.setenv('MOBILE_LOGIN_SKIP_OTP','false')
    assert client.post('/auth/contact',json={'phone':CONTACT['phone'],'name':'New customer'}).status_code == 200
    assert client.get('/orders').json() == []
    assert client.get('/auth/profile').json()['name'] == 'New customer'


def test_current_queue_excludes_previous_shift_and_history_retains_it(client, db):
    signin(client)
    _, paid=pay(client,fill_cart(client))
    order=by_ref(db,paid['order']['id'])
    order.placed_at=now()-timedelta(hours=13)
    db.commit()
    signin(client,'kitchen','kondapur')
    assert all(o['id'] != order.public_ref for o in client.get('/orders?outlet_id=kondapur&queue=true').json())
    signin(client,'manager','kondapur')
    assert any(o['id'] == order.public_ref for o in client.get('/orders?outlet_id=kondapur&history=true').json())


def test_arrival_uses_road_distance_and_returns_unknown_without_routing():
    from app.orders import estimated_arrival
    departure=now()
    order={'destination_lat':17.4,'destination_lng':78.4,'status':'preparing','revised_at':departure,'promised_at':departure}
    assert estimated_arrival(order,8)==departure+timedelta(minutes=29)
    assert estimated_arrival(order,None) is None


def test_detailed_report_reconciles_cancellations_and_retained_value(client, db):
    signin(client)
    _, first=pay(client,fill_cart(client),'dashboard-first')
    _, second=pay(client,fill_cart(client),'dashboard-second')
    signin(client,'manager','kondapur')
    cancelled=client.post('/orders/'+second['order']['id']+'/status',json={'version':1,'status':'cancelled','reason':'Item unavailable'})
    assert cancelled.status_code==200
    data=client.get('/staff/report?outlet_id=kondapur&days=7').json()
    assert data['orders']==2 and data['cancelled']==1 and data['cancellation_percent']==50
    assert data['gross_paise']==72000 and data['refunds_paise']==36000 and data['net_paise']==36000
    assert data['average_order_paise']==36000
    assert data['customers']==1 and data['repeat_customers']==0
    assert sum(h['orders'] for h in data['hourly'])==2
    assert sum(d['net_paise'] for d in data['daily'])==36000
    assert data['top_dishes'][0]['quantity']==1
    assert sum(p['amount_paise'] for p in data['payments'])==36000
    assert data['cancellation_reasons']==[{'reason':'Item unavailable','orders':1}]
    assert len(data['recent_orders'])==2
    assert data['median_prep_minutes'] is None and data['on_time_percent'] is None
    assert client.get('/staff/report?outlet_id=kukatpally').status_code==403
    signin(client,'kitchen','kondapur')
    assert client.get('/staff/report?outlet_id=kondapur').status_code==403


def test_demo_mobile_history_follows_phone_across_sessions_and_changes(client, db, monkeypatch):
    monkeypatch.setenv('MOBILE_LOGIN_SKIP_OTP','true')
    signin(client)
    _, first=pay(client,fill_cart(client),'phone-history-one')
    client.cookies.clear();signin(client)
    _, second=pay(client,fill_cart(client),'phone-history-two')
    client.cookies.clear();signin(client)
    cart=fill_cart(client)
    attempt=client.post('/payments',json={'method':'Card','idempotency_key':'other-number-payment','cart_version':cart['version'],'name':'Other Guest','phone':'6000000001'}).json()
    other=client.post('/payments/'+attempt['id']+'/confirm',json={'outcome':'success'}).json()['order']
    client.cookies.clear();signin(client)
    assert client.get('/orders').json()==[]
    assert client.get('/orders/'+first['order']['id']).status_code==404
    assert client.post('/auth/mobile',json={'phone':CONTACT['phone']}).status_code==200
    orders=client.get('/orders').json()
    assert {o['id'] for o in orders}=={first['order']['id'],second['order']['id']}
    assert all(o['tracking_token'] for o in orders)
    assert client.get('/orders/'+first['order']['id']).status_code==200
    assert client.get('/orders/'+other['id']).status_code==404
    assert client.get('/auth/profile').json()['name']==CONTACT['name']
    assert {o['id'] for o in client.get('/orders?phone=6000000001').json()}=={first['order']['id'],second['order']['id']}
    assert client.post('/auth/mobile',json={'phone':'6000000001'}).status_code==200
    assert [o['id'] for o in client.get('/orders').json()]==[other['id']]
    assert client.get('/orders/'+first['order']['id']).status_code==404


def test_production_mobile_history_requires_verified_session(client, db, monkeypatch):
    from app.auth import token_hash
    from app.models import Session
    signin(client)
    _, first=pay(client,fill_cart(client),'verified-history-order')
    client.cookies.clear();signin(client)
    monkeypatch.setenv('MOBILE_LOGIN_SKIP_OTP','false')
    assert client.post('/auth/mobile',json={'phone':CONTACT['phone']}).status_code==403
    assert client.get('/orders').json()==[]
    session=db.get(Session,token_hash(client.cookies.get('orderdesk_session')))
    session.verified_phone=CONTACT['phone'];db.commit()
    assert client.post('/auth/mobile',json={'phone':CONTACT['phone']}).status_code==200
    assert [o['id'] for o in client.get('/orders').json()]==[first['order']['id']]
    assert client.get('/orders/'+first['order']['id']).status_code==200
    assert client.post('/auth/contact',json={'phone':'6000000001'}).status_code==200
    assert client.get('/orders').json()==[]
    assert client.get('/orders/'+first['order']['id']).status_code==404
