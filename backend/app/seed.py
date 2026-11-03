"""Insert-only demonstration seed. Reruns never replace user or CMS edits."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from .db import SessionLocal
from .models import *
from .auth import hasher
from .prediction import train_if_missing
from .pricing import gst_inclusive

IMAGE_PATHS=['/food/chicken.webp','/food/vegetable.webp','/food/mutton.webp','/food/haleem.webp','/food/salan.webp','/food/meetha.webp']
OUTLETS=[
 ('kondapur','Kondapur','restaurant',17.4622,78.3568),
 ('kukatpally','Kukatpally','restaurant',17.4948,78.3996),
 ('jubilee-hills','Jubilee Hills','restaurant',17.4311,78.4073),
 ('banjara-hills','Banjara Hills','restaurant',17.4156,78.4347),
 ('madhapur','Madhapur','restaurant',17.4483,78.3915),
 ('hitech-city','HITEC City','restaurant',17.4504,78.3808),
 ('begumpet','Begumpet','restaurant',17.4448,78.4664),
 ('secunderabad','Secunderabad','restaurant',17.4399,78.4983),
 ('ameerpet','Ameerpet','restaurant',17.4375,78.4483),
 ('manikonda','Manikonda','restaurant',17.4015,78.3753),
 ('miyapur','Miyapur','restaurant',17.4968,78.3614),
 ('sainikpuri','Sainikpuri','restaurant',17.4860,78.5400),
 ('dilsukhnagar','Dilsukhnagar','restaurant',17.3687,78.5247),
 ('lb-nagar','LB Nagar','restaurant',17.3457,78.5522),
 ('gachibowli','Gachibowli cloud kitchen','cloud_kitchen',17.4401,78.3489),
 ('nallagandla','Nallagandla cloud kitchen','cloud_kitchen',17.4708,78.3006),
 ('uppal','Uppal cloud kitchen','cloud_kitchen',17.4058,78.5591),
]

def seed(db):
    db.execute(text('SELECT pg_advisory_xact_lock(70412025)'))
    for id,name,kind,lat,lng in OUTLETS:
        if not db.get(Outlet,id):
            db.add(Outlet(id=id,name=name,kind=kind,address=f'Synthetic demo location · {name}, Hyderabad',lat=lat,lng=lng,radius_km=5,minimum_minutes=30 if kind=='restaurant' else 25))
    db.flush()
    categories=[('biryani','Dum biryanis'),('specials','Slow-cooked specials'),('sides','On the side'),('desserts','Sweet endings')]
    for position,(id,name) in enumerate(categories):
        if not db.get(Category,id):
            db.add(Category(id=id,name=name,position=position))
    db.flush()
    regular=[{'id':'regular','name':'Regular · serves 1','price_paise':0}]
    biryani_addons=[{'id':'raita','name':'Extra raita','price_paise':4000},{'id':'salan','name':'Extra salan','price_paise':5000}]
    dishes=[
      ('chicken','biryani','Chicken dum biryani','Fragrant basmati, tender chicken and whole spices, sealed and slow-cooked in the dum tradition.',36000,False,2,['Milk'],regular+[{'id':'family','name':'Family pack · serves 3–4','price_paise':54000}],biryani_addons,30),
      ('mutton','biryani','Mutton dum biryani','Tender mutton, saffron-kissed rice and crisp onions. A generous Hyderabadi classic.',44000,False,3,['Milk'],regular+[{'id':'family','name':'Family pack · serves 3–4','price_paise':65000}],biryani_addons,40),
      ('vegetable','biryani','Veg biryani','Seasonal vegetables, long-grain basmati and garden mint, layered with warming spices.',27000,True,1,['Milk'],regular+[{'id':'family','name':'Family pack · serves 3–4','price_paise':43000}],biryani_addons,25),
      ('haleem','specials','Mutton haleem','Slow-simmered mutton, wheat and lentils, finished with ghee, fried onions and a squeeze of lime.',35000,False,2,['Wheat','Milk','Tree nuts'],regular,[],35),
      ('salan','sides','Mirchi ka salan','A comforting sesame and peanut gravy with whole green chillies. Biryani’s favourite companion.',10000,True,3,['Peanuts','Sesame'],[{'id':'regular','name':'Bowl · 200 ml','price_paise':0}],[],12),
      ('meetha','desserts','Double ka meetha','Golden bread, saffron milk and toasted nuts. A little taste of old Hyderabad.',14000,True,0,['Wheat','Milk','Tree nuts'],[{'id':'regular','name':'Single serving','price_paise':0}],[],8),
    ]
    for id,cat,name,desc,price,veg,spice,allergens,portions,addons,prep in dishes:
        if not db.get(MenuItem,id):
            db.add(MenuItem(id=id,category_id=cat,name=name,description=desc,price_paise=price,image=f'/food/{id}.webp',vegetarian=veg,spice=spice,allergens=allergens,portions=portions,addons=addons,prep_minutes=prep,start_hour=0,end_hour=24,city_prices={}))
    db.flush()
    for outlet in db.scalars(select(Outlet)):
        for item in db.scalars(select(MenuItem)):
            if not db.get(Availability,(outlet.id,item.id)):
                db.add(Availability(outlet_id=outlet.id,item_id=item.id,available=not(outlet.id=='uppal' and item.id=='haleem')))
    if not db.get(Coupon,'DIRECT10'):
        db.add(Coupon(code='DIRECT10',percent=10,cap_paise=15000))
    password=os.environ.get('DEMO_PASSWORD')
    if not password:
        raise RuntimeError('Set DEMO_PASSWORD for synthetic demo accounts.')
    accounts=[('customer@orderdesk.demo','Demo customer','customer',None,False),('admin@orderdesk.demo','Central menu editor','admin',None,True)]
    accounts += [(f'kitchen.{id}@orderdesk.demo',f'{name} kitchen','kitchen',id,id in ('kondapur','kukatpally','gachibowli')) for id,name,*_ in OUTLETS]
    for email,name,role,outlet_id,manager in accounts:
        user=db.scalar(select(User).where(User.email==email))
        if not user:
            user=User(email=email,name=name,role=role,outlet_id=outlet_id,can_manage=manager,password_hash=hasher.hash(password),demo=True)
            db.add(user); db.flush()
        if role=='customer' and not db.scalar(select(Cart).where(Cart.user_id==user.id)):
            db.add(Cart(user_id=user.id))
    customer=db.scalar(select(User).where(User.email=='customer@orderdesk.demo'))
    tz=ZoneInfo('Asia/Kolkata')
    def at(t):
        return datetime.fromisoformat('2026-11-02T'+t+':00').replace(tzinfo=tz)
    samples=[
      ('WEB-778120','kondapur','UPI','20:14','20:59','preparing',118000,[('chicken','Chicken dum biryani family pack',1,90000,'Family pack'),('meetha','Double ka meetha',2,14000,'Single serving')]),
      ('WEB-778131','gachibowli','Card','20:21','21:01','ready',64000,[('vegetable','Veg biryani',2,27000,'Regular'),('salan','Mirchi ka salan',1,10000,'Bowl')]),
      ('WEB-778146','kukatpally','UPI','20:26','21:16','preparing',105000,[('haleem','Mutton haleem',3,35000,'Regular')]),
    ]
    for id,outlet,method,placed,promised,status,total,lines in samples:
        if db.get(Order,id):
            continue
        payment=Payment(user_id=customer.id,idempotency_key='seed-'+id,method=method,status='success',amount_paise=total,cart_version=0,snapshot={'source':'client snapshot'},created_at=at(placed))
        db.add(payment); db.flush()
        order=Order(id=id,user_id=customer.id,outlet_id=outlet,payment_id=payment.id,status=status,subtotal_paise=total,total_paise=total,gst_paise=gst_inclusive(total),address='Synthetic sample delivery address',placed_at=at(placed),promised_at=at(promised),snapshot=True,snapshot_observed_at=at('21:20'))
        db.add(order); db.flush()
        for item,name,qty,unit,portion in lines:
            db.add(OrderItem(order_id=id,item_id=item,name=name,quantity=qty,unit_paise=unit,choices={'portion':portion,'addons':[]}))
        duration=int((at(promised)-at(placed)).total_seconds()/60)
        db.add(Estimate(order_id=id,predicted_minutes=duration,minimum_minutes=db.get(Outlet,outlet).minimum_minutes,promised_minutes=duration,source='client-snapshot-not-a-model-prediction',features={}))
        db.add(Event(kind='snapshot',order_id=id,user_id=customer.id,outlet_id=outlet,payload={'status':status,'observation':'2026-11-02 21:20 Asia/Kolkata','source':'Client snapshot; synthetic reference date'},created_at=at(placed)))
    train_if_missing(db)
    db.commit()

if __name__=='__main__':
    with SessionLocal() as db:
        seed(db)
        print('Insert-only seed complete: 17 outlets, menu, demo accounts, 3 client snapshots and synthetic training records.')
