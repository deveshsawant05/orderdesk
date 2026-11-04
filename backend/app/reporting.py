"""Outlet operational metrics over a rolling window."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func, select

from .auth import current_user, staff_outlet
from .db import get_db
from .models import Order, now

router = APIRouter()


@router.get('/staff/report')
def report(outlet_id: str, days: int = Query(default=7, ge=1, le=90),
           user=Depends(current_user), db=Depends(get_db)):
    if user.role != 'manager':
        raise HTTPException(403, 'Manager access is required.')
    staff_outlet(user, outlet_id)
    window = (Order.outlet_id == outlet_id, Order.snapshot.is_(False),
              Order.placed_at >= now() - timedelta(days=days))
    counts = dict(db.execute(select(Order.status, func.count()).where(*window).group_by(Order.status)).all())
    minutes = extract('epoch', Order.completed_at - Order.started_at) / 60
    median = db.scalar(select(func.percentile_cont(0.5).within_group(minutes)).where(
        *window, Order.started_at.is_not(None), Order.completed_at.is_not(None),
    ))
    repeat = select(Order.loyalty_phone).where(
        *window, Order.status == 'handed_off', Order.loyalty_phone.is_not(None),
    ).group_by(Order.loyalty_phone).having(func.count() >= 2)
    return {
        'days': days, 'orders': sum(counts.values()), 'cancelled': counts.get('cancelled', 0),
        'median_prep_minutes': round(float(median), 1) if median is not None else None,
        'repeat_verified_customers': db.scalar(select(func.count()).select_from(repeat.subquery())),
    }
