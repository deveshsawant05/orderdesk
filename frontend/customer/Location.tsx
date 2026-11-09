'use client';

import {useCallback, useEffect, useId, useMemo, useRef, useState} from 'react';
import dynamic from 'next/dynamic';
import {ArrowRight, LocateFixed, MapPin, Search} from 'lucide-react';
import {api, useResource} from '@/lib/api';
import {Cart, Outlet} from '@/lib/types';
import {ErrorBox, Modal} from '@/components/ui';
import type {Point} from '@/components/StreetMap';

const StreetMap = dynamic(() => import('@/components/StreetMap'), {
  ssr:false,
  loading:() => <div className="street-map map-loading" role="status">Loading Hyderabad street map…</div>,
});

type PlaceSuggestion = Point & {title:string;context:string;outlet_name:string|null};

function AddressSearch({select}: {select:(place:PlaceSuggestion)=>void}) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const resultsList = useRef<HTMLUListElement>(null);
  const resultsId = useId();
  const trimmed = query.trim();
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(trimmed),650);
    return () => clearTimeout(timer);
  },[trimmed]);
  const ready = trimmed.length >= 3 && debounced === trimmed;
  const results = useResource<PlaceSuggestion[]>(ready ? '/places?q='+encodeURIComponent(debounced) : null);
  const pick = (place:PlaceSuggestion) => {
    select(place);
    setQuery('');
  };
  return <div className="delivery-search">
    <label htmlFor={resultsId+'-input'}>Search street or landmark</label>
    <small>Searches OpenStreetMap via Photon. Enter private flat or unit details below.</small>
    <div className="delivery-search-field"><Search size={18}/><input id={resultsId+'-input'} type="search"
      autoComplete="off" maxLength={100} value={query} placeholder="Try HITEC City metro or Kondapur"
      aria-controls={ready ? resultsId : undefined} onChange={event => setQuery(event.target.value)}
      onKeyDown={event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          const first = results.data?.find(place => place.outlet_name);
          if (first) pick(first);
        }
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          resultsList.current?.querySelector<HTMLButtonElement>('button:not([disabled])')?.focus();
        }
      }}/>
    </div>
    {ready && <>
      {results.loading && <small role="status">Searching Hyderabad…</small>}
      {results.data?.length === 0 && <small role="status">No matches. Try a nearby landmark or tap the map.</small>}
      <ErrorBox message={results.error} retry={results.reload}/>
      <ul className="delivery-suggestions" id={resultsId} ref={resultsList}>
        {results.data?.map(place => <li key={`${place.title}:${place.context}:${place.lat},${place.lng}`}>
          <button type="button" disabled={!place.outlet_name} onClick={() => pick(place)}>
            <MapPin size={18} aria-hidden="true"/>
            <span><strong>{place.title}</strong>{place.context && <small>{place.context}</small>}
              <small>{place.outlet_name ? 'Delivered by '+place.outlet_name : 'Outside delivery radius'}</small></span>
          </button>
        </li>)}
      </ul>
    </>}
  </div>;
}

type Serviceability = {
  selected:string|null;
  eligible:{id:string;name:string;distance_km:number}[];
};

function readPoint(lat:string,lng:string): Point|null {
  if (!lat.trim() || !lng.trim()) return null;
  const latitude = Number(lat);
  const longitude = Number(lng);
  return Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180 ? {lat:latitude,lng:longitude} : null;
}

type Route = {distance_km:number; path:Point[]};

function useRoadRoute(token:string) {
  const [current, setCurrent] = useState<{token:string;route?:Route;error?:string}|null>(null);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setCurrent(null);
    try {
      const route = await api<Route>('/tracking/'+token+'/road-route','POST');
      if (request === sequence.current) setCurrent({token,route});
    } catch (failure) {
      if (request === sequence.current) setCurrent({token,error:(failure as Error).message});
    }
  },[token]);
  useEffect(() => {
    const pending = sequence;
    const timer = setTimeout(load,0);
    return () => {clearTimeout(timer);pending.current++;};
  },[load]);
  const result = current?.token === token ? current : null;
  return {...result,busy:!result,load};
}


export function TrackingMap({token, outlet, destination}: {token:string;outlet:Point&{name:string};destination:Point}) {
  const {lat, lng, name} = outlet;
  const {lat:destinationLat, lng:destinationLng} = destination;
  const markers = useMemo(() => [
    {name,lat,lng,endpoint:'hotel' as const},
    {name:'Drop location',lat:destinationLat,lng:destinationLng,endpoint:'drop' as const},
  ],[name,lat,lng,destinationLat,destinationLng]);
  const road = useRoadRoute(token);
  return <div className="tracking-street-map">
    <StreetMap markers={markers} route={road.route?.path}/>
    <div className="tracking-map-footer">
      <div>
        {road.route && <p className="road-distance"><strong>{road.route.distance_km.toFixed(2)} km by road</strong> · Blue line shows the driving route</p>}
        {road.busy && <p role="status">Finding a driving route…</p>}

      </div>
      <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">Report a map issue</a>
      <ErrorBox message={road.error || ''} retry={road.load}/>
    </div>
  </div>;
}

export default function Location({cart, outlets, close, save}: {
  cart:Pick<Cart,'lat'|'lng'|'address'>; outlets:Outlet[]; close:()=>void;
  save:(change:{lat:number;lng:number;address:string})=>Promise<unknown>;
}) {
  const formId = useId();
  const [lat, setLat] = useState(cart.lat?.toString() ?? '');
  const [lng, setLng] = useState(cart.lng?.toString() ?? '');
  const [address, setAddress] = useState(cart.address);
  const [focus, setFocus] = useState<Point|null>(() => cart.lat != null && cart.lng != null
    ? {lat:cart.lat,lng:cart.lng} : null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const point = useMemo(() => readPoint(lat,lng),[lat,lng]);
  const [checkedPoint, setCheckedPoint] = useState<Point|null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setCheckedPoint(point),180);
    return () => clearTimeout(timer);
  },[point]);
  const matchesPoint = point !== null && checkedPoint === point;
  const service = useResource<Serviceability>(matchesPoint
    ? `/serviceability?lat=${point.lat}&lng=${point.lng}` : null);
  const match = matchesPoint ? service.data?.eligible[0] : undefined;
  const outlet = outlets.find(entry => entry.id === match?.id);
  const choose = useCallback((point: Point) => {
    setLat(String(point.lat));
    setLng(String(point.lng));
    setError('');
  },[]);

  return <Modal title="Set your delivery point" close={close} className="delivery-dialog">
    <form id={formId} className="modal-body delivery-form" onSubmit={async event => {
      event.preventDefault();
      if (!point || !match) return;
      setBusy(true);
      setError('');
      try {
        await save({...point,address});
        close();
      } catch (failure) {
        setError((failure as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <AddressSearch select={place => {
        choose(place);
        setFocus(place);
        setAddress([place.title,place.context].filter(Boolean).join(', '));
      }}/>
      <p>Scroll or pinch to zoom. Tap the map or drag the pin to refine your location.</p>

      {outlets.length > 0
        ? <StreetMap markers={outlets} point={point} focus={focus} choose={choose} coverage={outlet}/>
        : <div className="street-map map-loading" role="status">Loading outlet locations…</div>}
      <div className="delivery-match" role="status">
        {!point ? 'Place a delivery pin to check nearby kitchens.'
          : !matchesPoint || service.loading ? 'Checking delivery coverage…'
          : match ? <><strong>{match.name}</strong> · {match.distance_km.toFixed(2)} km straight-line{outlet ? ` · ${outlet.radius_km} km service radius` : ''}</>
          : !service.error ? 'No open kitchen delivers to this pin. Try a nearby point.' : 'Coverage could not be checked.'}
      </div>
      <ErrorBox message={matchesPoint ? service.error : ''} retry={service.reload}/>
      <button type="button" className="secondary full" disabled={locating} onClick={() => {
        if (!navigator.geolocation) {
          setError('Location access is unavailable. Tap the map or enter coordinates.');
          return;
        }
        setLocating(true);
        navigator.geolocation.getCurrentPosition(position => {
          const here = {lat:Number(position.coords.latitude.toFixed(6)),lng:Number(position.coords.longitude.toFixed(6))};
          choose(here);
          setFocus(here);
          setLocating(false);
        }, () => {
          setError('Location access is unavailable. Tap the map or enter coordinates.');
          setLocating(false);
        },{timeout:8000});
      }}><LocateFixed size={18}/> {locating ? 'Finding your location…' : 'Use my current location'}</button>
      <label>Delivery address<input required minLength={5} maxLength={300} value={address}
        onChange={event => setAddress(event.target.value)} placeholder="Flat, building, street and landmark"/></label>
      <details className="delivery-input-options">
        <summary>Nearby localities and coordinates</summary>
        <label>Choose a nearby locality
          <select defaultValue="" onChange={event => {
            const outlet = outlets.find(entry => entry.id === event.target.value);
            if (!outlet) return;
            choose(outlet);
            setFocus(outlet);
            setAddress(outlet.address);
          }}>
            <option value="">Select a neighbourhood point</option>
            {outlets.map(outlet => <option key={outlet.id} value={outlet.id}>{outlet.name}</option>)}
          </select>
        </label>
        <div className="form-grid">
          <label>Latitude<input type="number" step="any" min="-90" max="90" value={lat} onChange={event => setLat(event.target.value)}/></label>
          <label>Longitude<input type="number" step="any" min="-180" max="180" value={lng} onChange={event => setLng(event.target.value)}/></label>
        </div>
      </details>
      <ErrorBox message={error}/>
    </form>
    <div className="delivery-actions">
      <button type="submit" form={formId} className="primary full" disabled={busy || !match || !!service.error}>
        Confirm location <ArrowRight size={18}/>
      </button>
    </div>
  </Modal>;
}
