import os
from pathlib import Path
import pytest
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2]/'.env')
base=os.environ['DATABASE_URL']
os.environ['DATABASE_URL']=os.environ.get('TEST_DATABASE_URL',base.rsplit('/',1)[0]+'/orderdesk_test')
if not os.environ['DATABASE_URL'].split('?')[0].endswith('/orderdesk_test'):
    raise RuntimeError('Tests require the isolated orderdesk_test database.')
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine,get_db
from app.main import app,limits
from app.seed import seed

@pytest.fixture(scope='session',autouse=True)
def database():
    from alembic.config import Config
    from alembic import command
    command.upgrade(Config('alembic.ini'),'head')
    with Session(engine) as db:
        seed(db)

@pytest.fixture
def db():
    with engine.connect() as connection:
        tx=connection.begin()
        session=Session(connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
        app.dependency_overrides[get_db]=lambda:session
        limits.clear()
        yield session
        session.close(); tx.rollback(); app.dependency_overrides.clear()

@pytest.fixture
def client(db):
    return TestClient(app,headers={'X-OrderDesk':'1','Origin':os.environ['APP_ORIGIN']})

def signin(client,role='customer',outlet_id=None):
    client.headers['X-OrderDesk-Experience'] = 'customer' if role == 'customer' else 'staff'
    if role == 'customer':
        response = client.post('/auth/guest')
    else:
        email = 'admin@orderdesk.demo' if role == 'manager' and not outlet_id else f'{role}.{outlet_id}@orderdesk.demo'
        response = client.post('/auth/login', json={'email':email,'password':os.environ['DEMO_PASSWORD']})
    assert response.status_code==200,response.text
    return response.json()

def fill_cart(client,outlet_id='kondapur',item_id='chicken',quantity=1,portion='regular',addons=None):
    outlets=client.get('/outlets').json(); outlet=next(o for o in outlets if o['id']==outlet_id)
    menu=client.get('/menu',params={'outlet_id':outlet_id}).json(); item=next(i for i in menu['items'] if i['id']==item_id)
    cart=client.get('/cart').json()
    body={'outlet_id':outlet_id,'lines':[{'item_id':item_id,'portion':portion,'addons':addons or [],'quantity':quantity,'menu_version':item['version']}],'address':'Synthetic test address, Hyderabad','lat':outlet['lat'],'lng':outlet['lng'],'coupon':'','version':cart['version']}
    response=client.put('/cart',json=body); assert response.status_code==200,response.text
    return response.json()

CONTACT = {'name':'Test Guest', 'phone':'6000000000'}


def pay(client,cart,key='test-payment-key',outcome='success'):
    r=client.post('/payments',json={'method':'UPI','idempotency_key':key,'cart_version':cart['version'],**CONTACT});assert r.status_code==200,r.text
    payment=r.json()
    r=client.post('/payments/'+payment['id']+'/confirm',json={'outcome':outcome});assert r.status_code==200,r.text
    return payment,r.json()
