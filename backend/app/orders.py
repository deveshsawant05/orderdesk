from fastapi import HTTPException
from sqlalchemy import select
from .models import Order, OrderItem, Outlet, Payment, Estimate, Event, Notification, Override
from .auth import staff_outlet

NEXT={'new':'preparing','preparing':'ready','ready':'handed_off'}

def accessible_order(db,user,order_id,lock=False):
    q=select(Order).where(Order.id==order_id)
    if lock:
        q=q.with_for_update()
    order=db.scalar(q)
    if not order:
        raise HTTPException(404,'Order not found.')
    if user.role=='customer':
        if order.user_id!=user.id:
            raise HTTPException(404,'Order not found.')
    else:
        staff_outlet(user,order.outlet_id)
    return order

def order_json(db,o,include_private=True):
    estimate=db.get(Estimate,o.id)
    outlet=db.get(Outlet,o.outlet_id)
    notifications=db.scalars(select(Notification).where(Notification.order_id==o.id)).all()
    overrides=db.scalars(select(Override).where(Override.order_id==o.id).order_by(Override.created_at)).all()
    result={k:getattr(o,k) for k in ['id','outlet_id','status','subtotal_paise','discount_paise','total_paise','gst_paise','placed_at','promised_at','revised_at','completed_at','version','snapshot','snapshot_observed_at']}
    result.update(outlet_name=outlet.name, fssai=outlet.fssai,payment_method=db.get(Payment,o.payment_id).method,
        items=[{k:getattr(i,k) for k in ['item_id','name','quantity','unit_paise','choices']} for i in db.scalars(select(OrderItem).where(OrderItem.order_id==o.id))],
        estimate={k:getattr(estimate,k) for k in ['predicted_minutes','minimum_minutes','promised_minutes','source','features']} if estimate else None,
        events=[{'id':e.id,'kind':e.kind,'payload':e.payload,'created_at':e.created_at} for e in db.scalars(select(Event).where(Event.order_id==o.id).order_by(Event.id))],
        notifications=[{'kind':n.kind,'audience':n.audience,'message':n.message,'transport':n.transport,'status':n.status,'created_at':n.created_at} for n in notifications if include_private or n.audience=='manager'],
        overrides=[{'reason':v.reason,'revised_at':v.revised_at,'created_at':v.created_at} for v in overrides])
    if include_private:
        result['address']=o.address
    return result
