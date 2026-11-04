"""Repeatable synthetic API + PostgreSQL smoke workload.

Run only against an isolated orderdesk_load database after migration and seed.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

from dotenv import load_dotenv
import httpx

load_dotenv(Path(__file__).resolve().parents[2] / '.env')
database_url = os.environ.get('LOAD_DATABASE_URL', '')
if not database_url.split('?')[0].endswith('/orderdesk_load'):
    raise SystemExit('Set LOAD_DATABASE_URL to the isolated orderdesk_load PostgreSQL database.')
os.environ['DATABASE_URL'] = database_url
from app.main import app  # noqa: E402


async def smoke(count, interval, concurrency):
    if not 1 <= count <= 25 or interval < 0 or concurrency < 1:
        raise ValueError('Use 1–25 orders and positive concurrency. Each guest creates an auth request.')
    transport = httpx.ASGITransport(app=app)
    headers = {'X-OrderDesk': '1'}
    async with httpx.AsyncClient(transport=transport, base_url='http://localhost', headers=headers) as client:
        outlets = (await client.get('/outlets')).json()
        kondapur = next(outlet for outlet in outlets if outlet['id'] == 'kondapur')
        outlets = outlets if interval else [kondapur]
    gate = asyncio.Semaphore(concurrency)

    async def purchase(index):
        await asyncio.sleep(index * interval)
        async with gate:
            start = perf_counter()
            async with httpx.AsyncClient(transport=transport, base_url='http://localhost', headers=headers) as client:
                async def request(method, path, **kwargs):
                    response = await client.request(method, path, **kwargs)
                    response.raise_for_status()
                    return response.json()

                outlet = outlets[index % len(outlets)]
                await request('POST', '/auth/guest')
                cart = await request('GET', '/cart')
                menu = await request('GET', '/menu', params={'outlet_id': outlet['id']})
                dish = next(item for item in menu['items'] if item['id'] == 'chicken')
                cart = await request('PUT', '/cart', json={
                    'version': cart['version'], 'lat': outlet['lat'], 'lng': outlet['lng'],
                    'address': 'Synthetic performance run',
                    'lines': [{'item_id': dish['id'], 'portion': dish['portions'][0]['id'],
                               'quantity': 1, 'menu_version': dish['version']}],
                })
                attempt = await request('POST', '/payments', json={
                    'method': 'UPI', 'idempotency_key': str(uuid4()), 'cart_version': cart['version'],
                    'name': 'Synthetic Guest', 'phone': '6000000000',
                })
                confirmations = await asyncio.gather(*[
                    request('POST', '/payments/'+attempt['id']+'/confirm', json={'outcome': 'success'})
                    for _ in range(2)
                ])
                first, retry = (result['order'] for result in confirmations)
                assert first['id'] == retry['id']
                assert first['outlet_id'] == outlet['id']
                ticket = (first['outlet_id'], first['service_date'], first['daily_number'])
                return ticket, (perf_counter() - start) * 1000

    start = perf_counter()
    results = await asyncio.gather(*(purchase(index) for index in range(count)))
    elapsed = perf_counter() - start
    tickets, times = zip(*results)
    assert len(set(tickets)) == count
    times = sorted(times)
    print(json.dumps({
        'orders': count, 'confirmation_retries': count,
        'elapsed_seconds': round(elapsed, 2),
        'interval_seconds': interval, 'concurrency_limit': concurrency,
        'p50_ms': round(median(times)), 'p95_ms': round(times[max(0, (95*count+99)//100-1)]),
    }, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--interval', type=float, default=0)
    parser.add_argument('--concurrency', type=int, default=4)
    args = parser.parse_args()
    asyncio.run(smoke(args.count,args.interval,args.concurrency))
