import asyncio, contextlib, json, logging, os, time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, or_, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session as DBSession
from .db import get_db, SessionLocal
from .models import *
from .auth import current_user, customer, admin, staff_outlet, user_json, hasher, create_session, token_hash, COOKIE
from .schemas import *
from .pricing import quote, serviceable, distance_km, time_available
from .prediction import predict
from .orders import accessible_order, order_json, NEXT
from .events import emit, notify, escalate_late

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
ORIGIN=os.getenv('APP_ORIGIN','http://localhost:3010')
app.add_middleware(CORSMiddleware,allow_origins=[ORIGIN],allow_credentials=True,allow_methods=['GET','POST','PUT','PATCH','DELETE'],allow_headers=['Content-Type','X-OrderDesk','Last-Event-ID'])
limits=defaultdict(deque)

@app.middleware('http')
async def protect(request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('origin') not in (None,ORIGIN) or request.headers.get('x-orderdesk')!='1':
            return JSONResponse({'detail':'Request origin or CSRF header rejected.'},403)
    if request.url.path.startswith('/auth/') and request.method=='POST':
        key=request.client.host
        q=limits[key]; cutoff=time.monotonic()-60
        while q and q[0]<cutoff:
            q.popleft()
        if len(q)>=30:
            return JSONResponse({'detail':'Too many sign-in attempts. Please wait a minute.'},429)
        q.append(time.monotonic())
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='same-origin'
    return response

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

@app.post('/auth/demo')
def demo(body:Demo,response:Response,db:DBSession=Depends(get_db)):
    if os.getenv('DEMO_MODE')!='true':
        raise HTTPException(404,'Demo access is disabled.')
    query=select(User).where(User.demo.is_(True),User.role==body.role)
    if body.role=='kitchen':
        query=query.where(User.outlet_id==(body.outlet_id or 'kondapur'))
    user=db.scalar(query.order_by(User.email))
    if not user:
        raise HTTPException(503,'Demo account is not seeded. Run the database seed.')
    create_session(db,user,response)
    return user_json(user)

@app.post('/auth/logout')
def logout(request:Request,response:Response,db:DBSession=Depends(get_db)):
    session=db.get(Session,token_hash(request.cookies.get(COOKIE,'')))
    if session:
        db.delete(session); db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

@app.get('/auth/me')
def me(user:User=Depends(current_user)):
    return user_json(user)

@app.get('/outlets')
def outlets(user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return [{k:getattr(o,k) for k in ['id','name','kind','city','address','lat','lng','radius_km','minimum_minutes','is_open','fssai','synthetic']} for o in db.scalars(select(Outlet).order_by(Outlet.name))]

@app.get('/serviceability')
def serviceability(lat:float,lng:float,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    if not -90<=lat<=90 or not -180<=lng<=180:
        raise HTTPException(422,'Invalid coordinates.')
    eligible=[{'id':o.id,'name':o.name,'distance_km':round(distance_km(lat,lng,o.lat,o.lng),2)} for o in db.scalars(select(Outlet)) if serviceable(o,lat,lng)]
    eligible.sort(key=lambda o:(o['distance_km'],o['id']))
    return {'eligible':eligible,'selected':eligible[0]['id'] if eligible else None,'rule':'Nearest open outlet within its synthetic delivery radius; ID breaks distance ties.'}

def menu_json(db,item,outlet):
    stock=db.get(Availability,(outlet.id,item.id))
    data={c.name:getattr(item,c.name) for c in MenuItem.__table__.columns}
    data['effective_price_paise']=item.city_prices.get(outlet.city,item.price_paise)
    data['available']=bool(item.active and stock and stock.available and time_available(item) and outlet.is_open)
    data['in_stock']=bool(stock and stock.available)
    data['time_available']=time_available(item)
    return data

@app.get('/menu')
def menu(outlet_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    outlet=db.get(Outlet,outlet_id)
    if not outlet:
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
    if cart.outlet_id:
        try:
            data['quote']=quote(db,cart.outlet_id,cart.lines,cart.lat,cart.lng,cart.coupon)
        except HTTPException as e:
            data['validation_error']=e.detail
    return data

@app.get('/cart')
def get_cart(user:User=Depends(customer),db:DBSession=Depends(get_db)):
    return cart_json(db,cart_record(db,user))

@app.put('/cart')
def update_cart(body:CartUpdate,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    cart=cart_record(db,user,True)
    if cart.version!=body.version:
        raise HTTPException(409,'Your bag changed in another tab. Reload and try again.')
    if cart.lines and cart.outlet_id!=body.outlet_id and body.lines:
        raise HTTPException(409,'Empty your bag before switching outlets.')
    lines=[l.model_dump() for l in body.lines]
    # Allow removing obsolete lines even when another line has become unavailable.
    old={(l['item_id'],l['portion'],tuple(l['addons']),l['menu_version']):l['quantity'] for l in cart.lines}
    removal=cart.outlet_id==body.outlet_id and body.coupon==cart.coupon and all(old.get((l['item_id'],l['portion'],tuple(l['addons']),l['menu_version']),0)>=l['quantity'] for l in lines)
    if not removal:
        quote(db,body.outlet_id,lines,body.lat,body.lng,body.coupon,lock=True)
    for k,v in body.model_dump(exclude={'version'}).items():
        setattr(cart,k,v)
    cart.version+=1; cart.updated_at=now()
    db.commit()
    return cart_json(db,cart)

@app.post('/payments')
def start_payment(body:StartPayment,user:User=Depends(customer),db:DBSession=Depends(get_db)):
    cart=cart_record(db,user,True)
    existing=db.scalar(select(Payment).where(Payment.user_id==user.id,Payment.idempotency_key==body.idempotency_key))
    if existing:
        return {'id':existing.id,'status':existing.status,'amount_paise':existing.amount_paise,'method':existing.method}
    if cart.version!=body.cart_version:
        raise HTTPException(409,'Your bag has changed. Review it before paying.')
    if not cart.lines or len(cart.address)<5:
        raise HTTPException(422,'Add food and a complete delivery address before checkout.')
    totals=quote(db,cart.outlet_id,cart.lines,cart.lat,cart.lng,cart.coupon,lock=True)
    payment=Payment(user_id=user.id,idempotency_key=body.idempotency_key,method=body.method,amount_paise=totals['total_paise'],cart_version=cart.version,
        snapshot={'outlet_id':cart.outlet_id,'lines':cart.lines,'lat':cart.lat,'lng':cart.lng,'address':cart.address,'coupon':cart.coupon})
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
        return {'status':'success','order':order_json(db,order)}
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
    totals=quote(db,snap['outlet_id'],snap['lines'],snap['lat'],snap['lng'],snap['coupon'],lock=True)
    if totals['total_paise']!=payment.amount_paise:
        raise HTTPException(409,'The total has changed. Review your bag and start a new attempt.')
    outlet=db.get(Outlet,snap['outlet_id'])
    estimate=predict(db,outlet,totals['lines'])
    placed=now()
    order=Order(id='WEB-'+uid().replace('-','')[:12].upper(),user_id=user.id,outlet_id=outlet.id,payment_id=payment.id,address=snap['address'],placed_at=placed,promised_at=placed+timedelta(minutes=estimate['promised_minutes']),
        subtotal_paise=totals['subtotal_paise'],discount_paise=totals['discount_paise'],total_paise=totals['total_paise'],gst_paise=totals['gst_paise'])
    db.add(order); db.flush()
    for line in totals['lines']:
        db.add(OrderItem(order_id=order.id,item_id=line['item_id'],name=line['name'],quantity=line['quantity'],unit_paise=line['unit_paise'],choices={'portion':line['portion_name'],'addons':line['addon_names']}))
    db.add(Estimate(order_id=order.id,**estimate))
    payment.status='success'; cart.lines=[]; cart.coupon=''; cart.version+=1
    notify(db,order,'new','Your test payment succeeded. The kitchen has received your order.')
    emit(db,'order_created',order,{'status':'new'})
    db.commit()
    return {'status':'success','order':order_json(db,order)}

@app.get('/orders')
def orders(outlet_id:str|None=None,snapshots:bool=False,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    query=select(Order).where(Order.snapshot==snapshots)
    if user.role=='customer':
        query=query.where(Order.user_id==user.id)
    else:
        outlet_id=outlet_id or user.outlet_id
        if not outlet_id:
            raise HTTPException(422,'Select an outlet.')
        staff_outlet(user,outlet_id)
        query=query.where(Order.outlet_id==outlet_id)
    return [order_json(db,o,user.role=='customer') for o in db.scalars(query.order_by(Order.placed_at.desc()).limit(100))]

@app.get('/orders/{order_id}')
def get_order(order_id:str,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    return order_json(db,accessible_order(db,user,order_id),user.role=='customer')

@app.post('/orders/{order_id}/status')
def status(order_id:str,body:Transition,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    order=accessible_order(db,user,order_id,True); staff_outlet(user,order.outlet_id)
    if order.snapshot:
        raise HTTPException(409,'Client snapshot records are read-only. Place a live order to test the workflow.')
    if order.version!=body.version:
        raise HTTPException(409,'Another kitchen screen updated this order. The board will refresh; retry with the latest status.')
    if body.status!=NEXT.get(order.status):
        raise HTTPException(409,'Invalid order transition. Advance one preparation stage at a time.')
    order.status=body.status; order.version+=1
    if body.status=='ready':
        order.completed_at=now()
    notify(db,order,body.status,f'Order status updated: {body.status.replace("_"," ")}.')
    emit(db,'status',order,{'status':body.status,'actor':user.id})
    db.commit()
    return order_json(db,order,False)

@app.post('/orders/{order_id}/override')
def override(order_id:str,body:OverrideInput,user:User=Depends(current_user),db:DBSession=Depends(get_db)):
    order=accessible_order(db,user,order_id,True); staff_outlet(user,order.outlet_id)
    if not user.can_manage or order.snapshot or order.status not in ('new','preparing'):
        raise HTTPException(403,'A manager can revise active live orders only.')
    if order.version!=body.version:
        raise HTTPException(409,'Order changed. Refresh before revising the estimate.')
    estimate=db.get(Estimate,order.id)
    revised=max(now()+timedelta(minutes=body.minutes_from_now),order.placed_at+timedelta(minutes=estimate.minimum_minutes))
    db.add(Override(order_id=order.id,user_id=user.id,reason=body.reason,previous_at=order.revised_at or order.promised_at,revised_at=revised))
    order.revised_at=revised; order.version+=1
    notify(db,order,f'override-{order.version}',f'The kitchen revised your ready time. {body.reason}')
    emit(db,'override',order,{'reason':body.reason,'revised_at':revised.isoformat()})
    db.commit()
    return order_json(db,order,False)

@app.get('/admin/menu')
def admin_menu(outlet_id:str,user:User=Depends(admin),db:DBSession=Depends(get_db)):
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
    row=db.scalar(select(Availability).where(Availability.outlet_id==outlet_id,Availability.item_id==item_id).with_for_update())
    if not row:
        raise HTTPException(404,'Outlet item not found.')
    row.available=body.available
    emit(db,'menu',payload={'item_id':item_id},outlet_id=outlet_id); db.commit()
    return {'available':row.available}

@app.get('/admin/model')
def model_info(user:User=Depends(admin),db:DBSession=Depends(get_db)):
    return [{c.name:getattr(m,c.name) for c in PredictionModel.__table__.columns} for m in db.scalars(select(PredictionModel))]

@app.get('/events')
async def stream(request:Request,user:User=Depends(current_user)):
    try:
        cursor=max(0,int(request.headers.get('last-event-id',request.query_params.get('after','0'))))
    except ValueError:
        raise HTTPException(422,'Invalid event cursor.')
    token=request.cookies.get(COOKIE,'')
    def read_events(after):
        with SessionLocal() as db:
            session=db.get(Session,token_hash(token))
            if not session or session.expires_at<=now():
                return None
            # Global menu invalidations carry only item IDs. Private events are scoped.
            scope=Event.user_id==user.id if user.role=='customer' else Event.outlet_id==user.outlet_id
            if user.role=='admin':
                scope=text('true')
            events=db.scalars(select(Event).where(Event.id>after,or_(Event.kind=='menu',scope)).order_by(Event.id).limit(100)).all()
            return [{'id':e.id,'kind':e.kind,'order_id':e.order_id,'outlet_id':e.outlet_id} for e in events]
    async def generate():
        nonlocal cursor
        yield 'retry: 2000\n\n'
        tick=0
        while not await request.is_disconnected():
            events=await asyncio.to_thread(read_events,cursor)
            if events is None:
                yield 'event: expired\ndata: {}\n\n'; break
            for e in events:
                cursor=e['id']
                yield f'id: {cursor}\ndata: {json.dumps(e)}\n\n'
            if tick%10==0:
                yield ': heartbeat\n\n'
            tick+=1
            await asyncio.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})
