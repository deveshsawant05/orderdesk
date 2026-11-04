from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .auth import staff_outlet
from .models import DailyCounter, Estimate, Event, Notification, Order, OrderItem, Outlet, Override, Payment
from .pricing import IST

NEXT = {'new': 'preparing', 'preparing': 'ready', 'ready': 'handed_off'}


def next_number(db, outlet_id, placed_at):
    day = placed_at.astimezone(IST).date()
    row = insert(DailyCounter).values(outlet_id=outlet_id, service_date=day, last_number=1)
    number = db.scalar(row.on_conflict_do_update(
        index_elements=['outlet_id', 'service_date'],
        set_={'last_number': DailyCounter.last_number + 1},
    ).returning(DailyCounter.last_number))
    return day, number


def tracking_order(db, token):
    order = db.scalar(select(Order).where(Order.tracking_token == token))
    if order is None:
        raise HTTPException(404, 'Tracking link not found.')
    return order


def accessible_order(db, user, order_id, lock=False):
    query = select(Order).where(Order.public_ref == order_id)
    if lock:
        query = query.with_for_update()
    order = db.scalar(query)
    if not order or (user.role == 'customer' and order.user_id != user.id):
        raise HTTPException(404, 'Order not found.')
    if user.role != 'customer':
        staff_outlet(user, order.outlet_id)
    return order


def order_json(db, order, include_private=True, include_token=False):
    return orders_json(db, [order], include_private, include_token)[0]


def orders_json(db, orders, include_private=False, include_token=False):
    """Hydrate the board with a fixed number of queries per refresh."""
    if not orders:
        return []
    order_ids = [order.id for order in orders]
    outlet_ids = {order.outlet_id for order in orders}
    payment_ids = {order.payment_id for order in orders}
    outlets = {outlet.id: outlet for outlet in db.scalars(select(Outlet).where(Outlet.id.in_(outlet_ids)))}
    payments = {payment.id: payment.method for payment in db.scalars(select(Payment).where(Payment.id.in_(payment_ids)))}
    estimates = {estimate.order_id: estimate for estimate in db.scalars(
        select(Estimate).where(Estimate.order_id.in_(order_ids))
    )}
    items = order_children(db, OrderItem, order_ids, OrderItem.name)
    events = order_children(db, Event, order_ids, Event.id)
    notifications = order_children(db, Notification, order_ids, Notification.created_at)
    overrides = order_children(db, Override, order_ids, Override.created_at)

    result = []
    for order in orders:
        outlet = outlets[order.outlet_id]
        estimate = estimates.get(order.id)
        data = {name: getattr(order, name) for name in (
            'outlet_id', 'daily_number', 'service_date', 'redeemed_points', 'status', 'subtotal_paise',
            'discount_paise', 'total_paise', 'gst_paise', 'placed_at', 'promised_at', 'revised_at',
            'completed_at', 'version', 'snapshot', 'snapshot_observed_at',
        )}
        data.update(
            id=order.public_ref, outlet_name=outlet.name, fssai=outlet.fssai,
            outlet_lat=outlet.lat, outlet_lng=outlet.lng, payment_method=payments[order.payment_id],
            refunded_at=order.refunded_at, resolution_reason=order.resolution_reason,
            items=[{name: getattr(item, name) for name in ('item_id', 'name', 'quantity', 'unit_paise', 'choices')}
                   for item in items[order.id]],
            estimate={name: getattr(estimate, name) for name in (
                'predicted_minutes', 'minimum_minutes', 'promised_minutes', 'source', 'features',
            )} if estimate else None,
            events=[{
                'id': event.id, 'kind': event.kind, 'created_at': event.created_at,
                'payload': {key: value for key, value in event.payload.items() if key != 'actor'},
            } for event in events[order.id]],
            notifications=[{
                'kind': message.kind, 'audience': message.audience, 'message': message.message,
                'transport': message.transport, 'status': message.status, 'created_at': message.created_at,
            } for message in notifications[order.id] if message.audience == ('customer' if include_private else 'manager')],
            overrides=[{
                'reason': revision.reason, 'revised_at': revision.revised_at, 'created_at': revision.created_at,
            } for revision in overrides[order.id]],
        )
        if include_private:
            data.update(address=order.address, destination_lat=order.destination_lat, destination_lng=order.destination_lng)
        if include_token:
            data['tracking_token'] = order.tracking_token
        result.append(data)
    return result


def order_children(db, model, order_ids, sort_by):
    records = defaultdict(list)
    for row in db.scalars(select(model).where(model.order_id.in_(order_ids)).order_by(sort_by)):
        records[row.order_id].append(row)
    return records
