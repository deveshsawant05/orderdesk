from datetime import datetime, timezone
import uuid
from sqlalchemy import String, Integer, Boolean, Float, DateTime, ForeignKey, JSON, Text, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

def uid():
    return str(uuid.uuid4())

class Outlet(Base):
    __tablename__ = 'outlets'
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    city: Mapped[str] = mapped_column(String(80), default='Hyderabad')
    address: Mapped[str] = mapped_column(String(240))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float)
    minimum_minutes: Mapped[int] = mapped_column(Integer)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    fssai: Mapped[str] = mapped_column(String(80), default='DEMO — NOT A VALID LICENCE')
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint('radius_km > 0 AND minimum_minutes > 0'),)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default='customer')
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey('outlets.id'))
    can_manage: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("role IN ('customer', 'kitchen', 'admin')"),)

class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)

class MenuItem(Base):
    __tablename__ = 'menu_items'
    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=uid)
    category_id: Mapped[str] = mapped_column(ForeignKey('categories.id'))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500))
    price_paise: Mapped[int] = mapped_column(Integer)
    image: Mapped[str] = mapped_column(String(240))
    vegetarian: Mapped[bool] = mapped_column(Boolean)
    spice: Mapped[int] = mapped_column(Integer)
    allergens: Mapped[list] = mapped_column(JSON)
    portions: Mapped[list] = mapped_column(JSON)
    addons: Mapped[list] = mapped_column(JSON)
    city_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    start_hour: Mapped[int] = mapped_column(Integer, default=0)
    end_hour: Mapped[int] = mapped_column(Integer, default=24)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=20)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint('price_paise >= 0 AND spice BETWEEN 0 AND 3'), CheckConstraint('start_hour BETWEEN 0 AND 23 AND end_hour BETWEEN 0 AND 24'),)

class Availability(Base):
    __tablename__ = 'availability'
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('menu_items.id'), primary_key=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)

class Coupon(Base):
    __tablename__ = 'coupons'
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    percent: Mapped[int] = mapped_column(Integer)
    cap_paise: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Cart(Base):
    __tablename__ = 'carts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), unique=True)
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey('outlets.id'))
    lines: Mapped[list] = mapped_column(JSON, default=list)
    address: Mapped[str] = mapped_column(String(300), default='')
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    coupon: Mapped[str] = mapped_column(String(30), default='')
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    amount_paise: Mapped[int] = mapped_column(Integer)
    cart_version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key'), CheckConstraint('amount_paise >= 0'), CheckConstraint("method IN ('UPI', 'Card')"), CheckConstraint("status IN ('pending','success','failed','cancelled')"))

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payments.id'), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='new')
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    discount_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    gst_paise: Mapped[int] = mapped_column(Integer)
    address: Mapped[str] = mapped_column(String(300))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    promised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint('total_paise >= 0 AND total_paise = subtotal_paise - discount_paise'), CheckConstraint("status IN ('new','preparing','ready','handed_off','cancelled')"), Index('ix_orders_outlet_status', 'outlet_id','status'))

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('menu_items.id'))
    name: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_paise: Mapped[int] = mapped_column(Integer)
    choices: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (CheckConstraint('quantity > 0 AND unit_paise >= 0'),)

class Estimate(Base):
    __tablename__ = 'estimates'
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), primary_key=True)
    predicted_minutes: Mapped[int] = mapped_column(Integer)
    minimum_minutes: Mapped[int] = mapped_column(Integer)
    promised_minutes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80))
    features: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (CheckConstraint('promised_minutes >= minimum_minutes AND promised_minutes >= predicted_minutes'),)

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(30))
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey('outlets.id'), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey('orders.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    audience: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(500))
    transport: Mapped[str] = mapped_column(String(30), default='mock-sms')
    status: Mapped[str] = mapped_column(String(20), default='simulated')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('order_id', 'kind', 'audience'),)

class Override(Base):
    __tablename__ = 'overrides'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(300))
    previous_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class TrainingSample(Base):
    __tablename__ = 'training_samples'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    features: Mapped[list] = mapped_column(JSON)
    duration: Mapped[float] = mapped_column(Float)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

class PredictionModel(Base):
    __tablename__ = 'prediction_models'
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    coefficients: Mapped[list] = mapped_column(JSON)
    feature_names: Mapped[list] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
