"""Hyderabad street and landmark suggestions from an OSM-based Photon geocoder."""
from functools import lru_cache
import os
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query
import httpx
from sqlalchemy import select

from .db import get_db
from .models import Outlet
from .pricing import outlets_by_radius

router = APIRouter()
DEMO_URL = 'https://photon.komoot.io'
HYDERABAD_BOUNDS = (78.24, 17.22, 78.68, 17.62)
_lock = Lock()
_last_search = 0.0


@lru_cache(maxsize=256)
def search_photon(base_url, query, cache_window):
    global _last_search
    if base_url == DEMO_URL:
        with _lock:
            instant = monotonic()
            if instant - _last_search < 1:
                raise HTTPException(429, 'Address search is busy. Wait a moment and retry.')
            _last_search = instant
    try:
        response = httpx.get(base_url+'/api', params={
            'q':query, 'bbox':','.join(map(str,HYDERABAD_BOUNDS)), 'limit':10, 'lang':'en',
        }, headers={'User-Agent':'OrderDesk/1.0 (Hyderabad ordering demo)'}, timeout=5)
        response.raise_for_status()
        features = response.json()['features']
        if not isinstance(features,list):
            raise ValueError('Unexpected Photon response')
        return features
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(503, 'Address suggestions are unavailable. You can still use the map.') from error


@router.get('/places')
def places(q: str = Query(min_length=3,max_length=100), db=Depends(get_db)):
    query = ' '.join(q.split())
    if len(query) < 3:
        return []
    base_url = os.getenv('GEOCODER_URL', '').strip().rstrip('/')
    if not base_url and os.getenv('DEMO_MODE') == 'true':
        base_url = DEMO_URL
    if not base_url:
        raise HTTPException(503, 'Address search is not configured. You can still use the map.')
    outlets = db.scalars(select(Outlet)).all()
    db.close()
    features = search_photon(base_url, query, int(monotonic() // 300))
    results = []
    seen = set()
    west, south, east, north = HYDERABAD_BOUNDS
    for feature in features:
        try:
            lng, lat = feature['geometry']['coordinates']
            properties = feature['properties']
            street = ' '.join(filter(None, [properties.get('housenumber'), properties.get('street')]))
            title = properties.get('name') or street
            context = ', '.join(dict.fromkeys(part for part in (
                street, properties.get('district'), properties.get('locality'), properties.get('city'), properties.get('postcode'),
            ) if part and part != title))
            if not title or not (west <= lng <= east and south <= lat <= north):
                continue
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        key = (title, context)
        if key in seen:
            continue
        seen.add(key)
        nearby = outlets_by_radius(outlets, lat, lng)
        results.append({
            'title':title, 'context':context, 'lat':lat, 'lng':lng,
            'outlet_name':nearby[0][1].name if nearby else None,
        })
    return sorted(results, key=lambda result: result['outlet_name'] is None)[:6]
