"""Outlet-scoped operational reporting, aggregated in PostgreSQL."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, extract, func, select
from .auth import current_user, staff_outlet
from .db import get_db
from .models import Availability, MenuItem, Order, OrderItem, PartyRequest, Payment, now
router = APIRouter()

@router.get('/staff/report')
def report(outlet_id:str, days:int=Query(default=7,ge=1,le=90),user=Depends(current_user),db=Depends(get_db)):
    if user.role != 'manager':
        raise HTTPException(403,'Manager access is required.')
    staff_outlet(user,outlet_id)
    observed=now()
    window=(Order.outlet_id==outlet_id,Order.snapshot.is_(False),Order.placed_at>=observed-timedelta(days=days),Order.placed_at<=observed)
    counts=dict(db.execute(select(Order.status,func.count()).where(*window).group_by(Order.status)).all())
    total=sum(counts.values())
    live=(Order.status.in_(['new','preparing','ready']),Order.placed_at>=observed-timedelta(hours=12))
    active=db.scalar(select(func.count()).select_from(Order).where(*window,*live))
    overdue=db.scalar(select(func.count()).select_from(Order).where(*window,*live,Order.status.in_(['new','preparing']),func.coalesce(Order.revised_at,Order.promised_at)<observed))
    finance=db.execute(select(
        func.coalesce(func.sum(Order.total_paise),0),
        func.coalesce(func.sum(case((Order.status=='cancelled',Order.total_paise),else_=0)),0),
        func.coalesce(func.sum(case((Order.status!='cancelled',Order.total_paise),else_=0)),0),
        func.coalesce(func.sum(case((Order.status!='cancelled',Order.discount_paise),else_=0)),0),
        func.coalesce(func.sum(case((Order.status!='cancelled',Order.gst_paise),else_=0)),0),
    ).where(*window)).one()
    minutes=extract('epoch',Order.completed_at-Order.started_at)/60
    eligible=(*window,Order.started_at.is_not(None),Order.completed_at.is_not(None),Order.status!='cancelled')
    performance=db.execute(select(func.count(),func.avg(minutes),func.percentile_cont(.5).within_group(minutes),func.percentile_cont(.9).within_group(minutes),
        func.sum(case((Order.completed_at<=func.coalesce(Order.revised_at,Order.promised_at),1),else_=0))).where(*eligible)).one()
    contacts=select(Order.contact_phone,func.count().label('orders')).where(*window,Order.status!='cancelled',Order.contact_phone.is_not(None)).group_by(Order.contact_phone).subquery()
    customers=db.execute(select(func.count(),func.coalesce(func.sum(case((contacts.c.orders>=2,1),else_=0)),0)).select_from(contacts)).one()
    verified=select(Order.loyalty_phone).where(*window,Order.status=='handed_off',Order.loyalty_phone.is_not(None)).group_by(Order.loyalty_phone).having(func.count()>=2)
    paid_count=total-counts.get('cancelled',0)
    day=func.date(func.timezone('Asia/Kolkata',Order.placed_at))
    daily=[{'date':str(date),'orders':number,'cancelled':cancelled,'net_paise':int(net)} for date,number,cancelled,net in db.execute(select(day,func.count(),func.sum(case((Order.status=='cancelled',1),else_=0)),func.sum(case((Order.status!='cancelled',Order.total_paise),else_=0))).where(*window).group_by(day).order_by(day)).all()]
    hour=extract('hour',func.timezone('Asia/Kolkata',Order.placed_at))
    hourly=dict(db.execute(select(hour,func.count()).where(*window).group_by(hour)).all())
    dishes=[{'name':name,'quantity':int(quantity),'food_value_paise':int(value)} for name,quantity,value in db.execute(select(OrderItem.name,func.sum(OrderItem.quantity),func.sum(OrderItem.unit_paise*OrderItem.quantity)).join(Order,Order.id==OrderItem.order_id).where(*window,Order.status!='cancelled').group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc(),OrderItem.name).limit(8)).all()]
    payments=[{'method':method,'orders':number,'amount_paise':int(amount)} for method,number,amount in db.execute(select(Payment.method,func.count(),func.sum(Order.total_paise)).join(Order,Order.payment_id==Payment.id).where(*window,Order.status!='cancelled').group_by(Payment.method).order_by(Payment.method)).all()]
    reasons=[{'reason':reason or 'Unspecified','orders':number} for reason,number in db.execute(select(Order.resolution_reason,func.count()).where(*window,Order.status=='cancelled').group_by(Order.resolution_reason).order_by(func.count().desc())).all()]
    party_window=(PartyRequest.outlet_id==outlet_id,PartyRequest.created_at>=observed-timedelta(days=days),PartyRequest.created_at<=observed)
    parties=dict(db.execute(select(PartyRequest.status,func.count()).where(*party_window).group_by(PartyRequest.status)).all())
    upcoming=[{'scheduled_at':p.scheduled_at,'items':sum(line['quantity'] for line in p.items),'status':p.status} for p in db.scalars(select(PartyRequest).where(PartyRequest.outlet_id==outlet_id,PartyRequest.scheduled_at>=observed,PartyRequest.status.in_(['pending','accepted'])).order_by(PartyRequest.scheduled_at).limit(5))]
    unavailable=list(db.scalars(select(MenuItem.name).join(Availability,Availability.item_id==MenuItem.id).where(Availability.outlet_id==outlet_id,Availability.available.is_(False),MenuItem.active.is_(True)).order_by(MenuItem.name)))
    recent=[{'id':o.public_ref,'number':o.daily_number,'status':o.status,'total_paise':o.total_paise,'placed_at':o.placed_at,'ready_at':o.revised_at or o.promised_at} for o in db.scalars(select(Order).where(*window).order_by(Order.placed_at.desc()).limit(10))]
    rounded=lambda value:round(float(value),1) if value is not None else None
    return {'days':days,'as_of':observed,'orders':total,'cancelled':counts.get('cancelled',0),'statuses':counts,'active':active,'overdue':overdue,
        'median_prep_minutes':rounded(performance[2]),'average_prep_minutes':rounded(performance[1]),'p90_prep_minutes':rounded(performance[3]),'timed_orders':performance[0],
        'on_time_percent':round(100*(performance[4] or 0)/performance[0],1) if performance[0] else None,
        'repeat_verified_customers':db.scalar(select(func.count()).select_from(verified.subquery())),
        'customers':customers[0],'repeat_customers':int(customers[1]),'repeat_percent':round(100*customers[1]/customers[0],1) if customers[0] else None,
        'gross_paise':int(finance[0]),'refunds_paise':int(finance[1]),'net_paise':int(finance[2]),'discounts_paise':int(finance[3]),'gst_paise':int(finance[4]),
        'average_order_paise':round(finance[2]/paid_count) if paid_count else None,'cancellation_percent':round(100*counts.get('cancelled',0)/total,1) if total else 0,
        'daily':daily,'hourly':[{'hour':h,'orders':hourly.get(h,0)} for h in range(24)],'top_dishes':dishes,'payments':payments,'cancellation_reasons':reasons,
        'party':parties,'upcoming_parties':upcoming,'unavailable_items':unavailable,'recent_orders':recent}
