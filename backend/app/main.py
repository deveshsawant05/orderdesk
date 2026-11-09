import asyncio, contextlib, json, logging, os, time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, or_, text, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import get_db, SessionLocal
from .models import *
from .auth import current_user, customer, admin, central_manager, staff_outlet, user_json, hasher, create_session, token_hash, session_cookie, customer_history_phone
from .schemas import *
from .pricing import quote, eligible_outlets, time_available
from .road_routing import road_route
from .prediction import predict
from .orders import customer_order_scope, accessible_order, estimated_arrival, order_json, orders_json, tracking_order, next_number, NEXT
from .events import emit, notify, escalate_late
from .auth import staff_scope
from .party import router as party_router, find_party
from .places import router as places_router
from .reporting import router as reporting_router
from .loyalty import router as loyalty_router, verified_phone, apply_redemption, record_points, EARN_PER_PAISE

log=logging.getLogger('orderdesk')

async def late_worker():
    while True:
        await asyncio.sleep(15)
        def run():
            with SessionLocal() as db:
                escalate_late(db)
        try:
            await asyncio.to_thread(run)
        except Exception:
            log.exception('Late-order worker failed; will retry')

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(late_worker())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

app=FastAPI(title='OrderDesk API',version='1.0.0',lifespan=lifespan)
app.include_router(loyalty_router)
app.include_router(party_router)
app.include_router(places_router)
app.include_router(reporting_router)
def browser_origins(origin):
    origin = origin.strip().rstrip('/')
    parsed = urlsplit(origin)
    origins = [origin]
    if parsed.hostname in ('localhost', '127.0.0.1'):
        other_host = '127.0.0.1' if parsed.hostname == 'localhost' else 'localhost'
        port = f':{parsed.port}' if parsed.port is not None else ''
        origins.append(f'{parsed.scheme}://{other_host}{port}')
    return origins


ALLOWED_ORIGINS = browser_origins(os.getenv('APP_ORIGIN', 'http://localhost:3000'))
for setting in ('OPS_APP_ORIGIN', 'TUNNEL_APP_ORIGIN'):
    origin = os.getenv(setting, '').strip().rstrip('/')
    if origin:
        ALLOWED_ORIGINS.extend(browser_origins(origin))
limits=defaultdict(deque)

@app.middleware('http')
async def protect(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin = request.headers.get('origin')
        if (origin is not None and origin not in ALLOWED_ORIGINS) or request.headers.get('x-orderdesk')!='1':
            return JSONResponse({'detail':'Request origin or CSRF header rejected.'},403)
    if (request.url.path.startswith('/auth/') or request.url.path == '/party') and request.method=='POST':
        key=request.client.host
        q=limits[key]; cutoff=time.monotonic()-60
        while q and q[0]<cutoff:
            q.popleft()
        if len(q)>=30:
            return JSONResponse({'detail':'Too many sign-in attempts. Please wait a minute.'},429)
        q.append(time.monotonic())
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers.setdefault('Cache-Control','no-store')
    response.headers['Referrer-Policy']='no-referrer'
    return response

# CORS wraps the request guard so trusted browsers can read its rejection responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
    allow_headers=['Content-Type', 'X-OrderDesk', 'X-OrderDesk-Experience', 'Last-Event-ID'],
)

@app.exception_handler(SQLAlchemyError)
async def database_error(request,exc):
    log.error('Database operation failed: %s',type(exc).__name__)
    return JSONResponse({'detail':'The database is temporarily unavailable. Your saved data has not been replaced. Please retry.'},503)

@app.get('/health')
def health(db:DBSession=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok','database':'postgresql'}

@app.post('/auth/register')
def register(body:Register,response:Response,db:DBSession=Depends(get_db)):
    if db.scalar(select(User).where(User.email==body.email.lower())):
        raise HTTPException(409,'An account with this email already exists.')
    user=User(email=body.email.lower(),name=body.name,password_hash=hasher.hash(body.password),marketing_consent=body.marketing_consent)
    db.add(user); db.flush()
    db.add(Cart(user_id=user.id))
    create_session(db,user,response)
    return user_json(user)

@app.post('/auth/login')
def login(body:Login,response:Response,db:DBSession=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower()))
    try:
        if not user or not hasher.verify(user.password_hash,body.password):
            raise ValueError()
    except Exception:
        raise HTTPException(401,'Email or password is incorrect.')
    create_session(db,user,response)
    return user_json(user)

@app.post('/auth/logout')
def logout(request:Request,response:Response,db:DBSession=Depends(get_db)):
    session=db.get(Session,token_hash(request.cookies.get(session_cookie(request),'')))
    if session:
        db.delete(session); db.commit()
    response.delete_cookie(session_cookie(request),path='/')
    return {'ok':True}

@app.post('/auth/guest')
def guest(request: Request, response: Response, db: DBSession = Depends(get_db)):
    # A shared customer demo account would leak unrelated carts and history.
    try:
        existing = current_user(request, db)
    except HTTPException:
        existing = None
    if existing and existing.role == 'customer':
        return user_json(existing)
    identity = uid()
    user = User(id=identity, email=f'{identity}@guest.invalid', name='Guest', password_hash='!')
    db.add(user)
    db.flush()
    db.add(Cart(user_id=user.id))
    create_session(db, user, response)
    return user_json(user)


@app.get('/auth/me')
def me(user:User=Depends(current_user)):
    return user_json(user)

@app.get('/auth/profile')
def profile(request:Request,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    order=db.scalar(select(Order).where(customer_order_scope(user,customer_history_phone(db,request,user)),Order.snapshot.is_(False)).order_by(Order.placed_at.desc()).limit(1))
    return {'name':user.name if user.contact_phone and user.name != 'Guest' else (order.contact_name if order else ''), 'phone':user.contact_phone or (order.contact_phone if order else ''),
            'address':order.address if order else '', 'marketing_consent':user.marketing_consent}

@app.post('/auth/contact')
def save_contact(body:ContactInput,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    if user.contact_phone != body.phone:
        user.marketing_consent=False;user.consent_updated_at=now()
    user.contact_phone=body.phone
    if body.name:user.name=body.name
    db.commit()
    return {'phone':body.phone}

@app.post('/auth/mobile')
def mobile_login(body:ContactInput,request:Request,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    if os.getenv('MOBILE_LOGIN_SKIP_OTP','false') != 'true' and verified_phone(db,request) != body.phone:
        raise HTTPException(403,'Verify your mobile number before accessing its order history.')
    if user.contact_phone != body.phone:
        user.marketing_consent=False;user.consent_updated_at=now()
        user.name=body.name or 'Guest'
    elif body.name:
        user.name=body.name
    user.contact_phone=body.phone
    db.commit()
    return {'phone':body.phone}

@app.get('/outlets')
def outlets(db:DBSession=Depends(get_db)):
    return [{k:getattr(o,k) for k in ['id','name','kind','city','address','lat','lng','radius_km','minimum_minutes','is_open','fssai','synthetic']} for o in db.scalars(select(Outlet).order_by(Outlet.name))]

@app.get('/serviceability')
def serviceability(lat:float,lng:float,db:DBSession=Depends(get_db)):
    if not -90<=lat<=90 or not -180<=lng<=180:
        raise HTTPException(422,'Invalid coordinates.')
    eligible=[{'id':o.id,'name':o.name,'distance_km':round(distance,2)} for distance,o in eligible_outlets(db,lat,lng)]
    return {'eligible':eligible,'selected':eligible[0]['id'] if eligible else None,'rule':'Nearest open outlet within its synthetic delivery radius; ID breaks distance ties.'}

def menu_json(db,item,outlet):
    stock=db.get(Availability,(outlet.id,item.id)) if outlet else None
    data={c.name:getattr(item,c.name) for c in MenuItem.__table__.columns}
    data['effective_price_paise']=item.city_prices.get(outlet.city,item.price_paise) if outlet else item.price_paise
    data['available']=bool(item.active and time_available(item) and (not outlet or (stock and stock.available and outlet.is_open)))
    data['in_stock']=bool(stock and stock.available) if outlet else None
    data['time_available']=time_available(item)
    return data

@app.get('/menu')
def menu(outlet_id:str|None=None,db:DBSession=Depends(get_db)):
    outlet=db.get(Outlet,outlet_id) if outlet_id else None
    if outlet_id and not outlet:
        raise HTTPException(404,'Outlet not found.')
    return {'categories':[{'id':c.id,'name':c.name} for c in db.scalars(select(Category).order_by(Category.position))],
        'items':[menu_json(db,i,outlet) for i in db.scalars(select(MenuItem).where(MenuItem.active.is_(True)).order_by(MenuItem.id))],
        'coupons':[{'code':c.code,'percent':c.percent,'cap_paise':c.cap_paise} for c in db.scalars(select(Coupon).where(Coupon.active.is_(True)))],
        'imagery_note':'AI-generated demonstration imagery. Food details and allergens are synthetic; verify before production.'}

def cart_record(db,user,lock=False):
    query=select(Cart).where(Cart.user_id==user.id)
    if lock:
        query=query.with_for_update()
    cart=db.scalar(query)
    if not cart:
        raise HTTPException(409,'Cart not initialized. Contact support.')
    return cart

def cart_json(db,cart):
    data={c.name:getattr(cart,c.name) for c in Cart.__table__.columns if c.name!='user_id'}
    data['quote']=None; data['validation_error']=None
    if cart.lines:
        try:
            data['quote']=quote(db,cart.outlet_id,cart.lines,cart.lat,cart.lng,cart.coupon)
        except HTTPException as e:
            data['validation_error']=e.detail
    data['item_details']={i.id:{'name':i.name,'image':i.image} for i in db.scalars(select(MenuItem).where(MenuItem.id.in_([line['item_id'] for line in cart.lines])))}
    return data

@app.get('/cart')
def get_cart(user:User=Depends(customer),db:DBSession=Depends(get_db)):
    return cart_json(db,cart_record(db,user))

def basket_counts(lines):
    counts = Counter()
    for line in lines:
        key = (line['item_id'], line['portion'], tuple(sorted(line['addons'])), line['menu_version'])
        counts[key] += line['quantity']
    return counts


@app.put('/cart')
def update_cart(body:CartUpdate,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    cart=cart_record(db,user,True)
    if cart.version!=body.version:
        raise HTTPException(409,'Your bag changed in another tab. Reload and try again.')
    outlet_id = None
    if body.lat is not None or body.lng is not None:
        if body.lat is None or body.lng is None:
            raise HTTPException(422,'Choose a complete delivery point.')
        eligible = eligible_outlets(db, body.lat, body.lng)
        if not eligible:
            raise HTTPException(422,'This point is outside the delivery area of every open outlet.')
        outlet_id = eligible[0][1].id
    elif cart.outlet_id:
        raise HTTPException(422,'Choose a delivery point.')
    lines=[l.model_dump() for l in body.lines]
    # Allow removing obsolete lines even when another line has become unavailable.
    removal = body.coupon == cart.coupon and not (basket_counts(lines) - basket_counts(cart.lines))
    if not removal:
        quote(db,outlet_id,lines,body.lat,body.lng,body.coupon,lock=True)
    for k,v in body.model_dump(exclude={'version','outlet_id'}).items():
        setattr(cart,k,v)
    cart.outlet_id = outlet_id
    cart.version+=1; cart.updated_at=now()
    db.commit()
    return cart_json(db,cart)

@app.post('/payments')
def start_payment(body:StartPayment,request:Request,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    cart=cart_record(db,user,True)
    existing=db.scalar(select(Payment).where(Payment.user_id==user.id,Payment.idempotency_key==body.idempotency_key))
    if existing:
        requested = (body.method, body.cart_version, body.name, body.phone, body.redeem_points, body.marketing_consent)
        original = (existing.method, existing.cart_version, existing.snapshot.get('name'), existing.snapshot.get('phone'),
                    existing.snapshot.get('redeemed_points', 0), existing.snapshot.get('marketing_consent', False))
        if original != requested:
            raise HTTPException(409, 'This key already belongs to a different test payment attempt.')
        return {'id':existing.id,'status':existing.status,'amount_paise':existing.amount_paise,'method':existing.method}
    if cart.version!=body.cart_version:
        raise HTTPException(409,'Your bag has changed. Review it before paying.')
    if not cart.lines or not cart.outlet_id or len(cart.address)<5:
        raise HTTPException(422,'Add food and a complete delivery address before checkout.')
    totals=quote(db,cart.outlet_id,cart.lines,cart.lat,cart.lng,cart.coupon,lock=True)
    loyalty_phone = body.phone if body.phone == verified_phone(db, request) else None
    apply_redemption(db, totals, loyalty_phone, body.redeem_points, cart.coupon)
    payment=Payment(user_id=user.id,idempotency_key=body.idempotency_key,method=body.method,amount_paise=totals['total_paise'],cart_version=cart.version,
        snapshot={'outlet_id':cart.outlet_id,'lines':cart.lines,'lat':cart.lat,'lng':cart.lng,'address':cart.address,'coupon':cart.coupon,'name':body.name,'phone':body.phone,'marketing_consent':body.marketing_consent,'loyalty_phone':loyalty_phone,'redeemed_points':body.redeem_points})
    db.add(payment); db.commit()
    return {'id':payment.id,'status':payment.status,'amount_paise':payment.amount_paise,'method':payment.method}

@app.post('/payments/{payment_id}/confirm')
def confirm_payment(payment_id:str,body:ConfirmPayment,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    # Always lock the cart before the payment to keep a single lock ordering.
    cart=cart_record(db,user,True)
    payment=db.scalar(select(Payment).where(Payment.id==payment_id,Payment.user_id==user.id).with_for_update())
    if not payment:
        raise HTTPException(404,'Payment not found.')
    if payment.status=='success':
        order=db.scalar(select(Order).where(Order.payment_id==payment.id))
        return {'status':'success','order':order_json(db,order,include_token=True)}
    if payment.status!='pending':
        raise HTTPException(409,'This payment attempt is closed. Start a new attempt from your bag.')
    if body.outcome!='success':
        payment.status=body.outcome; db.commit()
        return {'status':payment.status}
    if now()-payment.created_at>timedelta(minutes=10):
        raise HTTPException(409,'Payment expired. Start a new attempt from your bag.')
    if cart.version!=payment.cart_version:
        raise HTTPException(409,'Your bag changed after payment started. Review it and start a new attempt.')
    snap=payment.snapshot
    if not snap.get('phone') or not snap.get('name'):
        raise HTTPException(409,'Start a fresh attempt with your contact details.')
    totals=quote(db,snap['outlet_id'],snap['lines'],snap['lat'],snap['lng'],snap['coupon'],lock=True)
    points = snap.get('redeemed_points', 0)
    account = apply_redemption(db, totals, snap.get('loyalty_phone'), points, snap['coupon'], lock=True)
    if totals['total_paise']!=payment.amount_paise:
        raise HTTPException(409,'The total has changed. Review your bag and start a new attempt.')
    outlet=db.get(Outlet,snap['outlet_id'])
    estimate=predict(db,outlet,totals['lines'])
    placed=now()
    service_date, daily_number = next_number(db, outlet.id, placed)
    public_ref = f'WEB-{service_date:%y%m%d}-{uid().replace("-", "")[:12].upper()}'
    order=Order(public_ref=public_ref,service_date=service_date,daily_number=daily_number,
        destination_lat=snap['lat'],destination_lng=snap['lng'],contact_name=snap['name'],contact_phone=snap['phone'],
        loyalty_phone=snap.get('loyalty_phone'),redeemed_points=points,user_id=user.id,outlet_id=outlet.id,payment_id=payment.id,address=snap['address'],placed_at=placed,promised_at=placed+timedelta(minutes=estimate['promised_minutes']),
        subtotal_paise=totals['subtotal_paise'],discount_paise=totals['discount_paise'],total_paise=totals['total_paise'],gst_paise=totals['gst_paise'])
    db.add(order); db.flush()
    for line in totals['lines']:
        db.add(OrderItem(order_id=order.id,item_id=line['item_id'],name=line['name'],quantity=line['quantity'],unit_paise=line['unit_paise'],choices={'portion':line['portion_name'],'addons':line['addon_names']}))
    db.add(Estimate(order_id=order.id,**estimate))
    record_points(db, order, 'redeemed', -points, account)
    payment.status='success'; cart.lines=[]; cart.coupon=''; cart.version+=1
    user.name=snap['name'];user.contact_phone=snap['phone']
    user.marketing_consent = snap['marketing_consent']
    user.consent_updated_at = placed
    notify(db,order,'new','Your test payment succeeded. The kitchen has received your order.')
    emit(db,'order_created',order,{'status':'new'})
    db.commit()
    return {'status':'success','order':order_json(db,order,include_token=True)}

@app.get('/orders')
def orders(request:Request,outlet_id:str|None=None,snapshots:bool=False,queue:bool=False,history:bool=False,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    query=select(Order).where(Order.snapshot==snapshots)
    if user.role=='customer':
        query=query.where(customer_order_scope(user,customer_history_phone(db,request,user)))
    else:
        outlet_id=staff_scope(user,outlet_id)
        if outlet_id:
            query=query.where(Order.outlet_id==outlet_id)
        if queue:
            query=query.where(Order.status.in_(['new','preparing','ready']),Order.placed_at>=now()-timedelta(hours=12))
        elif history:
            query=query.where(or_(Order.status.in_(['handed_off','cancelled']),Order.placed_at<now()-timedelta(hours=12)))
    query = query.order_by(Order.placed_at.desc())
    if not queue or user.role == 'customer':
        query = query.limit(100)
    return orders_json(db, db.scalars(query).all(), user.role == 'customer', user.role == 'customer')

@app.post('/tracking/{token}/road-route')
def tracking_road_route(token: str, db: DBSession = Depends(get_db)):
    order = tracking_order(db, token)
    if order.destination_lat is None or order.destination_lng is None:
        raise HTTPException(404, 'This order has no delivery pin.')
    outlet = db.get(Outlet, order.outlet_id)
    origin = outlet.lat, outlet.lng
    destination = order.destination_lat, order.destination_lng
    db.close()
    return road_route(origin, destination)


@app.get('/tracking/{token}')
def track(token: str, db: DBSession = Depends(get_db)):
    order = order_json(db, tracking_order(db, token))
    db.close()
    try:
        route=road_route((order['outlet_lat'],order['outlet_lng']),(order['destination_lat'],order['destination_lng'])) if order['destination_lat'] is not None else None
    except HTTPException:
        route=None
    return {**order, 'estimated_arrival_at': estimated_arrival(order,route['distance_km'] if route else None)}


@app.get('/orders/{order_id}')
def get_order(order_id:str,request:Request,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return order_json(db,accessible_order(db,user,order_id,customer_phone=customer_history_phone(db,request,user)),user.role=='customer')

@app.post('/orders/{order_id}/status')
def status(order_id:str,body:Transition,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    order=accessible_order(db,user,order_id,True); staff_outlet(user,order.outlet_id)
    if order.snapshot:
        raise HTTPException(409,'Client snapshot records are read-only. Place a live order to test the workflow.')
    if order.version!=body.version:
        raise HTTPException(409,'Another kitchen screen updated this order. The board will refresh; retry with the latest status.')
    if body.status == 'cancelled':
        if user.role == 'kitchen' and body.reason != 'Item unavailable':
            raise HTTPException(403, 'Kitchen staff can cancel orders only for unavailable items.')
        if order.status not in ('new', 'preparing') or len(body.reason) < 3:
            raise HTTPException(409, 'Only active orders can be cancelled. Include a reason.')
        order.resolution_reason = body.reason
        order.refunded_at = now()
        record_points(db, order, 'restored', order.redeemed_points)
        notify(db, order, 'refund', f'Test payment reversed. {body.reason}')
        emit(db, 'order.refunded', order, {'reason': body.reason})
    elif body.status != NEXT.get(order.status):
        raise HTTPException(409, 'Invalid order transition. Advance one preparation stage at a time.')
    if body.status == 'preparing':
        item_ids = select(OrderItem.item_id).where(OrderItem.order_id == order.id)
        stocks = db.scalars(select(Availability).where(
            Availability.outlet_id == order.outlet_id, Availability.item_id.in_(item_ids)
        ).order_by(Availability.item_id).with_for_update()).all()
        if not all(stock.available for stock in stocks):
            raise HTTPException(409, 'One or more dishes are out of stock. Resolve stock or reject the order.')
    order.status=body.status; order.version+=1
    if body.status == 'preparing':
        order.started_at = now()
    if body.status == 'handed_off':
        record_points(db, order, 'earned', order.total_paise // EARN_PER_PAISE)
    if body.status=='ready':
        order.completed_at=now()
    notify(db,order,body.status,f'Order status updated: {body.status.replace("_"," ")}.')
    emit(db,'order.'+body.status,order,{'status':body.status,'actor':user.id})
    db.commit()
    return order_json(db,order,False)

@app.post('/orders/{order_id}/adjust-time')
def adjust_time(order_id:str,body:AdjustTime,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    order=accessible_order(db,user,order_id,True); staff_outlet(user,order.outlet_id)
    if user.role not in ('manager','kitchen') or order.snapshot or order.status not in ('new','preparing'):
        raise HTTPException(403,'Only active kitchen orders can be adjusted.')
    if order.version != body.version:
        raise HTTPException(409,'Order changed. Please retry with the latest ticket.')
    estimate=db.get(Estimate,order.id)
    previous=order.revised_at or order.promised_at
    minimum=order.placed_at+timedelta(minutes=estimate.minimum_minutes)
    revised=max(now(),minimum,max(now(),previous)+timedelta(minutes=body.delta_minutes))
    order.revised_at=revised;order.version+=1
    message='Delivery will take longer than expected.' if revised>previous else 'Your delivery time has been updated.'
    notify(db,order,f'eta-{order.version}',message)
    emit(db,'order.eta_updated',order,{'message':message,'revised_at':revised.isoformat()})
    db.commit()
    return order_json(db,order,False)

@app.get('/admin/menu')
def admin_menu(outlet_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    staff_outlet(user, outlet_id)
    if user.role != 'manager':
        raise HTTPException(403, 'Manager access is required.')
    outlet=db.get(Outlet,outlet_id)
    if not outlet:
        raise HTTPException(404,'Outlet not found.')
    return [menu_json(db,i,outlet) for i in db.scalars(select(MenuItem).order_by(MenuItem.name))]

def validate_item(db,body):
    if not db.get(Category,body.category_id):
        raise HTTPException(422,'Choose an existing category.')
    # Approved local image catalog; never fetch arbitrary URLs on the server.
    from .seed import IMAGE_PATHS
    if body.image not in IMAGE_PATHS:
        raise HTTPException(422,'Choose an approved local demonstration image.')

@app.post('/admin/menu')
def create_item(body:ItemInput,user:User=Depends(admin),db:DBSession=Depends(get_db)):
    validate_item(db,body)
    item=MenuItem(**body.model_dump()); db.add(item); db.flush()
    for outlet in db.scalars(select(Outlet)):
        db.add(Availability(outlet_id=outlet.id,item_id=item.id,available=True))
    emit(db,'menu',payload={'item_id':item.id}); db.commit()
    return {'id':item.id}

@app.put('/admin/menu/{item_id}')
def edit_item(item_id:str,body:ItemInput,user:User=Depends(admin),db:DBSession=Depends(get_db)):
    validate_item(db,body)
    item=db.scalar(select(MenuItem).where(MenuItem.id==item_id).with_for_update())
    if not item:
        raise HTTPException(404,'Item not found.')
    if body.version!=item.version:
        raise HTTPException(409,'Someone edited this item. Reload the editor to avoid overwriting their changes.')
    for k,v in body.model_dump(exclude={'version'}).items():
        setattr(item,k,v)
    item.version+=1
    emit(db,'menu',payload={'item_id':item.id}); db.commit()
    return {'id':item.id,'version':item.version}

@app.put('/availability/{outlet_id}/{item_id}')
def stock(outlet_id:str,item_id:str,body:StockInput,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    staff_outlet(user,outlet_id)
    if user.role != 'manager':
        raise HTTPException(403, 'Manager access is required.')
    row=db.scalar(select(Availability).where(Availability.outlet_id==outlet_id,Availability.item_id==item_id).with_for_update())
    if not row:
        raise HTTPException(404,'Outlet item not found.')
    row.available=body.available
    emit(db,'menu',payload={'item_id':item_id},outlet_id=outlet_id); db.commit()
    return {'available':row.available}

@app.get('/admin/model')
def model_info(user:User=Depends(admin),db:DBSession=Depends(get_db)):
    return [{c.name:getattr(m,c.name) for c in PredictionModel.__table__.columns} for m in db.scalars(select(PredictionModel))]

def event_response(request, db, scope, session=None):
    raw_cursor = request.headers.get('last-event-id')
    try:
        cursor = max(0, int(raw_cursor)) if raw_cursor else db.scalar(select(func.max(Event.id))) or 0
    except ValueError:
        raise HTTPException(422, 'Invalid event cursor.')

    def read_events(after):
        with SessionLocal() as reader:
            if session:
                active = reader.get(Session, session)
                if not active or active.expires_at <= now():
                    return None
            rows = reader.execute(
                select(Event, Order.public_ref).outerjoin(Order, Event.order_id == Order.id)
                .where(Event.id > after, scope).order_by(Event.id).limit(100)
            )
            return [{
                'id': event.id, 'kind': event.kind, 'order_id': ref,
                'outlet_id': event.outlet_id, 'created_at': event.created_at.isoformat(),
                'version': event.payload.get('version'),
            } for event, ref in rows]

    async def generate():
        nonlocal cursor
        yield 'retry: 2000\n\n'
        tick = 0
        while not await request.is_disconnected():
            events = await asyncio.to_thread(read_events, cursor)
            if events is None:
                yield 'event: expired\ndata: {}\n\n'
                break
            for event in events:
                cursor = event['id']
                yield f'id: {cursor}\ndata: {json.dumps(event)}\n\n'
            if tick % 10 == 0:
                yield ': heartbeat\n\n'
            tick += 1
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store, no-transform'})


@app.get('/events/menu')
def public_menu_events(request: Request, outlet_id: str | None = None):
    with SessionLocal() as db:
        scope = (Event.kind == 'menu') & or_(Event.outlet_id.is_(None), Event.outlet_id == outlet_id)
        return event_response(request, db, scope)


@app.get('/tracking/{token}/events')
def tracking_events(token: str, request: Request):
    with SessionLocal() as db:
        order = tracking_order(db, token)
        return event_response(request, db, Event.order_id == order.id)


@app.get('/party/tracking/{token}/events')
def party_events(token: str, request: Request):
    with SessionLocal() as db:
        party = find_party(db, token)
        return event_response(request, db, Event.party_id == party.id)


@app.get('/events')
def stream(request: Request, outlet_id: str | None = None):
    with SessionLocal() as db:
        user = current_user(request, db)
        global_menu = (Event.kind == 'menu') & Event.outlet_id.is_(None)
        if user.role == 'customer':
            scope = Event.user_id == user.id
        elif central_manager(user) and not outlet_id:
            scope = text('true')
        else:
            if outlet_id:
                staff_outlet(user, outlet_id)
            scope = or_(global_menu, Event.outlet_id == (outlet_id or user.outlet_id))
            if user.role == 'kitchen':
                scope = scope & (Event.kind != 'party.created')
        session = token_hash(request.cookies.get(session_cookie(request), ''))
        return event_response(request, db, scope, session)
