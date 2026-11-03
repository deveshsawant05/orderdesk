from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(Strict):
    email: str = Field(min_length=3, max_length=180)
    password: str = Field(min_length=1, max_length=200)

class Register(Login):
    name: str = Field(min_length=2,max_length=80)
    password: str = Field(min_length=10,max_length=200)
    marketing_consent: bool = False
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Enter a valid email address')
        return v.lower()

class Demo(Strict):
    role: Literal['customer','kitchen','admin']
    outlet_id: str | None = None

class Line(Strict):
    item_id: str
    portion: str
    addons: list[str] = Field(default_factory=list,max_length=10)
    quantity: int = Field(ge=1,le=20)
    menu_version: int = Field(ge=1)

class CartUpdate(Strict):
    outlet_id: str
    lines: list[Line] = Field(max_length=40)
    address: str = Field(default='',max_length=300)
    lat: float = Field(ge=-90,le=90)
    lng: float = Field(ge=-180,le=180)
    coupon: str = Field(default='',max_length=30)
    version: int

class StartPayment(Strict):
    method: Literal['UPI','Card']
    idempotency_key: str = Field(min_length=8,max_length=80)
    cart_version: int

class ConfirmPayment(Strict):
    outcome: Literal['success','failed','cancelled']

class Transition(Strict):
    status: Literal['preparing','ready','handed_off','cancelled']
    version: int

class OverrideInput(Strict):
    minutes_from_now: int = Field(ge=1,le=180)
    reason: str = Field(min_length=5,max_length=300)
    version: int

class Option(Strict):
    id: str = Field(min_length=1,max_length=40,pattern=r'^[a-z0-9_-]+$')
    name: str = Field(min_length=1,max_length=80)
    price_paise: int = Field(ge=0,le=1000000)

class ItemInput(Strict):
    category_id: str
    name: str = Field(min_length=2,max_length=120)
    description: str = Field(min_length=5,max_length=500)
    price_paise: int = Field(ge=100,le=1000000)
    image: str = Field(pattern=r'^/food/[a-z0-9_-]+\.webp$')
    vegetarian: bool
    spice: int = Field(ge=0,le=3)
    allergens: list[str] = Field(max_length=15)
    portions: list[Option] = Field(min_length=1,max_length=8)
    addons: list[Option] = Field(max_length=10)
    city_prices: dict[str,int] = Field(default_factory=dict)
    start_hour: int = Field(ge=0,le=23)
    end_hour: int = Field(ge=0,le=24)
    prep_minutes: int = Field(ge=1,le=180)
    active: bool = True
    version: int = 1
    @field_validator('city_prices')
    @classmethod
    def cities_valid(cls,v):
        if len(v)>30 or any(not k.strip() or len(k)>80 or p<100 or p>1000000 for k,p in v.items()):
            raise ValueError('Invalid city price')
        return v
    @field_validator('portions','addons')
    @classmethod
    def unique_options(cls,v):
        if len({o.id for o in v}) != len(v):
            raise ValueError('Option identifiers must be unique')
        return v

class StockInput(Strict):
    available: bool
