from math import radians, sin, cos, asin, sqrt
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from .models import Outlet, MenuItem, Availability, Coupon, now

IST = ZoneInfo('Asia/Kolkata')

def distance_km(lat1, lng1, lat2, lng2):
    a = sin(radians(lat2-lat1)/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(radians(lng2-lng1)/2)**2
    return 6371 * 2 * asin(sqrt(min(1,a)))

def serviceable(outlet, lat, lng):
    return outlet.is_open and lat is not None and lng is not None and distance_km(lat,lng,outlet.lat,outlet.lng) <= outlet.radius_km

def time_available(item, at=None):
    hour = (at or now()).astimezone(IST).hour
    if item.start_hour == item.end_hour:
        return True
    if item.start_hour < item.end_hour:
        return item.start_hour <= hour < item.end_hour
    return hour >= item.start_hour or hour < item.end_hour

def gst_inclusive(paise):
    # Integer rounding to nearest paise: gross * 5 / 105 == gross / 21.
    return (paise + 10) // 21

def quote(db, outlet_id, lines, lat, lng, coupon='', lock=False):
    outlet = db.get(Outlet,outlet_id)
    if not outlet or not serviceable(outlet,lat,lng):
        raise HTTPException(422,'This address is outside the selected outlet’s delivery area, or the outlet is closed.')
    output=[]
    # Stable lock ordering prevents concurrent CMS edits from racing payment validation.
    ids=sorted({line['item_id'] for line in lines})
    query=select(MenuItem).where(MenuItem.id.in_(ids)).order_by(MenuItem.id)
    if lock:
        query=query.with_for_update()
    items={i.id:i for i in db.scalars(query)}
    stocks_query=select(Availability).where(Availability.outlet_id==outlet_id,Availability.item_id.in_(ids)).order_by(Availability.item_id)
    if lock:
        stocks_query=stocks_query.with_for_update()
    stocks={s.item_id:s.available for s in db.scalars(stocks_query)}
    for line in lines:
        item=items.get(line['item_id'])
        if not item or not item.active or not stocks.get(item.id,False) or not time_available(item):
            raise HTTPException(409,f'{item.name if item else "An item"} is currently unavailable. Remove it from your bag.')
        if line['menu_version'] != item.version:
            raise HTTPException(409,f'{item.name} has changed. Remove it and add it again to review the current price and options.')
        portions={p['id']:p for p in item.portions}
        addons={a['id']:a for a in item.addons}
        selected=line['addons']
        if line['portion'] not in portions or len(set(selected)) != len(selected) or any(a not in addons for a in selected):
            raise HTTPException(422,'This customization is no longer available.')
        portion=portions[line['portion']]
        price=item.city_prices.get(outlet.city,item.price_paise)+portion['price_paise']+sum(addons[a]['price_paise'] for a in selected)
        output.append({**line,'name':item.name,'image':item.image,'portion_name':portion['name'],'addon_names':[addons[a]['name'] for a in selected], 'unit_paise':price,'line_paise':price*line['quantity'],'prep_minutes':item.prep_minutes})
    subtotal=sum(l['line_paise'] for l in output)
    discount=0
    if coupon:
        offer=db.get(Coupon,coupon.upper())
        if not offer or not offer.active:
            raise HTTPException(422,'Coupon not recognized or no longer active.')
        discount=min(subtotal*offer.percent//100,offer.cap_paise)
    total=subtotal-discount
    return {'lines':output,'subtotal_paise':subtotal,'discount_paise':discount,'delivery_paise':0,'total_paise':total,'gst_paise':gst_inclusive(total)}
