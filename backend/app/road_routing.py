"""Driving distance and route geometry from an OpenStreetMap-based OSRM service."""
from functools import lru_cache
import math
import os
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

DEMO_URL = 'https://routing.openstreetmap.de/routed-car'
DEMO_HOST = 'routing.openstreetmap.de'
_public_router = Lock()
_last_request = 0.0


def router_url():
    configured = os.getenv('ROUTING_API_URL', '').strip()
    if configured:
        return configured.rstrip('/')
    if os.getenv('DEMO_MODE') == 'true':
        return DEMO_URL
    raise HTTPException(503, 'Road routing is not configured.')


def request_router(base, points):
    global _last_request
    public = urlsplit(base).hostname == DEMO_HOST
    if public and not _public_router.acquire(timeout=2):
        raise HTTPException(503, 'Road routing is busy. Try again in a moment.')
    try:
        if public:
            sleep(max(0, 1.05 - (monotonic() - _last_request)))
            _last_request = monotonic()
        coordinates = ';'.join(f'{lng:.6f},{lat:.6f}' for lat, lng in points)
        response = httpx.get(
            f'{base}/route/v1/driving/{coordinates}',
            params={'overview':'full','geometries':'geojson','generate_hints':'false'},
            headers={'User-Agent': 'OrderDesk/1.0 (Hyderabad ordering demo)'}, timeout=5,
        )
        result = response.json()
        if result.get('code') in ('NoRoute', 'NoSegment'):
            return None
        response.raise_for_status()
        if result.get('code') != 'Ok':
            raise ValueError('Unexpected OSRM status')
        return result
    except (httpx.HTTPError, AttributeError, ValueError) as error:
        raise HTTPException(503, 'Road routing is unavailable. Try again shortly.') from error
    finally:
        if public:
            _public_router.release()


def valid_distance(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


@lru_cache(maxsize=128)
def route_geometry(base, origin, destination, cache_window):
    result = request_router(base, (origin, destination))
    if result is None:
        raise HTTPException(422, 'No driving route was found for these points.')
    try:
        route = result['routes'][0]
        meters = route['distance']
        path = [{'lat': lat, 'lng': lng} for lng, lat in route['geometry']['coordinates']]
        if not valid_distance(meters) or len(path) < 2 or any(
            not (-90 <= point['lat'] <= 90 and -180 <= point['lng'] <= 180) for point in path
        ):
            raise ValueError('Unexpected OSRM route geometry')
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(503, 'The routing service did not return a usable route.') from error
    return {'distance_km': round(meters / 1000, 2), 'path': path}


def road_route(origin, destination):
    return route_geometry(router_url(), origin, destination, int(monotonic() // 600))
