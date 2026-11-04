from datetime import timedelta
from sqlalchemy import select, text, func
from .models import Event, Notification, Order, now

def emit(db,kind,order=None,payload=None,outlet_id=None,party_id=None):
    # Serializes event ID allocation through commit: no cursor skips a late commit.
    db.execute(text('SELECT pg_advisory_xact_lock(70412026)'))
    payload = dict(payload or {})
    if order:
        payload.setdefault('version', order.version)
    db.add(Event(kind=kind,outlet_id=order.outlet_id if order else outlet_id,user_id=order.user_id if order else None,order_id=order.id if order else None,party_id=party_id,payload=payload))

def notify(db,order,kind,message,audience='customer'):
    db.add(Notification(order_id=order.id,kind=kind,audience=audience,message=message,transport='in-app' if audience=='manager' else 'mock-sms'))

def escalate_late(db):
    orders=list(db.scalars(select(Order).where(Order.snapshot.is_(False),Order.status.in_(['new','preparing']),func.coalesce(Order.revised_at, Order.promised_at)<=now()-timedelta(minutes=10)).with_for_update(skip_locked=True)))
    count=0
    for order in orders:
        exists=db.scalar(select(Notification.id).where(Notification.order_id==order.id,Notification.kind=='late',Notification.audience=='manager'))
        if exists:
            continue
        message='Your order is taking longer than promised. The outlet manager has been alerted and will update your ready time.'
        notify(db,order,'late',message)
        notify(db,order,'late','Order is over 10 minutes late. Review preparation and update the ready time.','manager')
        emit(db,'late',order,{'message':message})
        count+=1
    db.commit()
    return count
