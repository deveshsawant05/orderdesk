from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func
from app.models import *
from app.pricing import distance_km,serviceable,gst_inclusive,time_available
from app.prediction import predict,MODEL_ID
from app.events import escalate_late
from app.seed import seed
from .conftest import signin,fill_cart,pay

def test_seed_exact_records_and_safe_rerun(db):
    assert db.scalar(select(func.count()).select_from(Outlet))==17
    assert db.scalar(select(func.count()).select_from(Outlet).where(Outlet.kind=='restaurant'))==14
    for id,amount,status,method in [('WEB-778120',118000,'preparing','UPI'),('WEB-778131',64000,'ready','Card'),('WEB-778146',105000,'preparing','UPI')]:
        o=db.get(Order,id);assert (o.total_paise,o.status,db.get(Payment,o.payment_id).method)==(amount,status,method)
        assert sum(i.quantity*i.unit_paise for i in db.scalars(select(OrderItem).where(OrderItem.order_id==id)))==amount
    third=db.get(Order,'WEB-778146');assert (third.snapshot_observed_at-third.promised_at).total_seconds()==240
    item=db.get(MenuItem,'chicken');item.description='User-authored persistent edit';db.commit()
    seed(db);db.expire_all()
    assert db.get(MenuItem,'chicken').description=='User-authored persistent edit'
    assert db.scalar(select(func.count()).select_from(Order))==3

def test_radius_routing_and_closed_outlets(db,client):
    signin(client)
    o=db.get(Outlet,'kondapur')
    assert distance_km(o.lat,o.lng,o.lat,o.lng)==0
    assert serviceable(o,o.lat,o.lng)
    result=client.get('/serviceability',params={'lat':o.lat,'lng':o.lng}).json()
    assert result['selected']==o.id
    assert client.get('/serviceability',params={'lat':0,'lng':0}).json()['selected'] is None
    o.is_open=False
    assert not serviceable(o,o.lat,o.lng)

def test_tax_and_time_windows(db):
    assert gst_inclusive(10500)==500
    assert gst_inclusive(118000)==5619
    item=db.get(MenuItem,'haleem');item.start_hour=18;item.end_hour=23
    assert time_available(item,datetime(2026,11,2,14,tzinfo=timezone.utc))
    assert not time_available(item,datetime(2026,11,2,4,tzinfo=timezone.utc))
    item.start_hour=22;item.end_hour=3
    assert time_available(item,datetime(2026,11,2,18,tzinfo=timezone.utc))
    assert not time_available(item,datetime(2026,11,2,10,tzinfo=timezone.utc))

def test_customization_coupon_and_cart_persistence(client,db):
    signin(client);cart=fill_cart(client,quantity=2,portion='family',addons=['raita'])
    assert cart['quote']['total_paise']==188000
    saved=client.get('/cart').json();assert saved['lines']==cart['lines']
    payload={k:saved[k] for k in ['outlet_id','lines','address','lat','lng','coupon','version']}
    payload['coupon']='DIRECT10';r=client.put('/cart',json=payload)
    assert r.json()['quote']['discount_paise']==15000
    payload['version']=r.json()['version'];payload['coupon']='INVALID'
    assert client.put('/cart',json=payload).status_code==422
    payload['coupon']='';payload['lines'][0]['addons']=['unrecognized']
    assert client.put('/cart',json=payload).status_code==422

def test_payment_idempotency_and_historical_price(client,db):
    user=signin(client);cart=fill_cart(client);payment,result=pay(client,cart)
    order=result['order'];assert order['outlet_id']=='kondapur'
    repeated=client.post('/payments/'+payment['id']+'/confirm',json={'outcome':'success'})
    assert repeated.json()['order']['id']==order['id']
    assert db.scalar(select(func.count()).select_from(Order).where(Order.payment_id==payment['id']))==1
    assert client.get('/cart').json()['lines']==[]
    item=db.get(MenuItem,'chicken');item.price_paise=99900;db.commit()
    assert client.get('/orders/'+order['id']).json()['total_paise']==36000
    assert db.scalar(select(Event).where(Event.order_id==order['id'],Event.kind=='order_created'))
    estimate=db.get(Estimate,order['id']);assert estimate.promised_minutes>=estimate.minimum_minutes

def test_failed_cancelled_and_retry_payments(client,db):
    signin(client);cart=fill_cart(client)
    _,failed=pay(client,cart,'failed-key','failed');assert failed['status']=='failed'
    _,cancelled=pay(client,cart,'cancel-key','cancelled');assert cancelled['status']=='cancelled'
    assert len(client.get('/cart').json()['lines'])==1
    _,success=pay(client,cart,'success-key');assert success['order']['id']
    assert db.scalar(select(func.count()).select_from(Order).where(Order.snapshot.is_(False)))==1

def test_payment_revalidates_stock_price_and_cart(client,db):
    signin(client);cart=fill_cart(client)
    p=client.post('/payments',json={'method':'Card','idempotency_key':'stock-test','cart_version':cart['version']}).json()
    stock=db.get(Availability,('kondapur','chicken'));stock.available=False;db.commit()
    assert client.post('/payments/'+p['id']+'/confirm',json={'outcome':'success'}).status_code==409
    stock.available=True;db.get(MenuItem,'chicken').version+=1;db.commit()
    assert client.post('/payments/'+p['id']+'/confirm',json={'outcome':'success'}).status_code==409
    assert db.get(Payment,p['id']).status=='pending'

def test_stock_change_is_outlet_scoped(client,db):
    signin(client,'kitchen','kondapur')
    assert client.put('/availability/kondapur/chicken',json={'available':False}).status_code==200
    assert not client.get('/menu?outlet_id=kondapur').json()['items'][0]['available']
    assert next(i for i in client.get('/menu?outlet_id=kukatpally').json()['items'] if i['id']=='chicken')['available']
    assert client.put('/availability/kukatpally/chicken',json={'available':False}).status_code==403

def test_state_machine_stale_version_and_permissions(client,db):
    signin(client);_,result=pay(client,fill_cart(client));o=result['order']
    assert client.post('/orders/'+o['id']+'/status',json={'status':'preparing','version':1}).status_code==403
    signin(client,'kitchen','kukatpally')
    assert client.get('/orders/'+o['id']).status_code==403
    assert client.get('/orders?outlet_id=kondapur').status_code==403
    signin(client,'kitchen','kondapur')
    assert client.post('/orders/'+o['id']+'/status',json={'status':'ready','version':1}).status_code==409
    assert client.post('/orders/'+o['id']+'/status',json={'status':'preparing','version':1}).status_code==200
    assert client.post('/orders/'+o['id']+'/status',json={'status':'preparing','version':1}).status_code==409
    assert client.post('/orders/'+o['id']+'/status',json={'status':'ready','version':2}).status_code==200
    assert client.post('/orders/'+o['id']+'/status',json={'status':'handed_off','version':3}).status_code==200
    db.expire_all();assert db.get(Order,o['id']).status=='handed_off'

def test_prediction_real_model_and_fallback(db):
    o=db.get(Outlet,'kondapur');lines=[{'quantity':2,'prep_minutes':30}]
    result=predict(db,o,lines)
    assert result['source']==MODEL_ID
    assert result['promised_minutes']==max(result['predicted_minutes'],o.minimum_minutes)
    model=db.get(PredictionModel,MODEL_ID);assert model.metrics['synthetic'] and model.metrics['test_rows']==120
    db.delete(model);db.flush()
    fallback=predict(db,o,lines)
    assert fallback['source']=='deterministic-fallback'
    assert fallback['promised_minutes']>=o.minimum_minutes

def test_late_escalation_once_and_manager_override(client,db):
    signin(client);_,r=pay(client,fill_cart(client));id=r['order']['id']
    o=db.get(Order,id);o.placed_at=now()-timedelta(hours=2);o.promised_at=now()-timedelta(minutes=11);db.commit()
    assert escalate_late(db)==1
    assert escalate_late(db)==0
    assert len(db.scalars(select(Notification).where(Notification.order_id==id,Notification.kind=='late')).all())==2
    signin(client,'kitchen','kondapur')
    r=client.post('/orders/'+id+'/override',json={'version':1,'minutes_from_now':20,'reason':'Extra time on dum needed.'})
    assert r.status_code==200,r.text
    db.expire_all();o=db.get(Order,id);assert o.revised_at>now() and o.promised_at<now()
    assert db.scalar(select(Override).where(Override.order_id==id))

def test_auth_privacy_csrf_and_consent(client,db):
    assert client.get('/menu?outlet_id=kondapur').status_code==401
    assert client.post('/auth/demo',json={'role':'customer'},headers={'X-OrderDesk':'0'}).status_code==403
    assert client.post('/auth/demo',json={'role':'customer'},headers={'Origin':'https://evil.example'}).status_code==403
    r=client.post('/auth/register',json={'email':'test-only@example.invalid','name':'Test Only','password':'synthetic-test-password'})
    assert r.status_code==200,r.text
    assert not r.json()['marketing_consent']
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=lax' in r.headers['set-cookie']
    assert client.get('/orders/WEB-778120').status_code==404
    assert client.get('/admin/menu?outlet_id=kondapur').status_code==403
    assert client.post('/auth/logout').status_code==200
    assert client.get('/auth/me').status_code==401

def test_admin_menu_edit_archive_and_snapshot_immutable(client,db):
    signin(client,'admin')
    item=client.get('/admin/menu?outlet_id=kondapur').json()[0]
    body={k:v for k,v in item.items() if k not in ('id','effective_price_paise','available','in_stock','time_available')}
    body['price_paise']=42000;body['city_prices']={'Hyderabad':43000};body['description']='A revised description from the CMS.'
    response=client.put('/admin/menu/'+item['id'],json=body);assert response.status_code==200,response.text
    assert client.put('/admin/menu/'+item['id'],json=body).status_code==409
    updated=next(i for i in client.get('/menu?outlet_id=kondapur').json()['items'] if i['id']==item['id'])
    assert updated['effective_price_paise']==43000
    body['version']=response.json()['version'];body['active']=False
    assert client.put('/admin/menu/'+item['id'],json=body).status_code==200
    assert item['id'] not in [i['id'] for i in client.get('/menu?outlet_id=kondapur').json()['items']]
    assert client.post('/orders/WEB-778120/status',json={'status':'ready','version':1}).status_code==409

def test_empty_cart_invalid_location_and_duplicate_options(client,db):
    signin(client)
    c=client.get('/cart').json()
    assert client.post('/payments',json={'method':'UPI','idempotency_key':'empty-test-key','cart_version':c['version']}).status_code==422
    c=fill_cart(client)
    body={k:c[k] for k in ['outlet_id','lines','address','lat','lng','coupon','version']}
    body['lat']=0;body['lng']=0
    # Persisting removal-only edits does not permit a bad address to check out.
    client.put('/cart',json=body)
    c=client.get('/cart').json();assert c['validation_error']
    assert client.post('/payments',json={'method':'UPI','idempotency_key':'outside-test-key','cart_version':c['version']}).status_code==422
