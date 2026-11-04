'use client';

import {useCallback,useState} from 'react';
import dynamic from 'next/dynamic';
import {ArrowRight, LocateFixed} from 'lucide-react';
import {Cart, Outlet} from '@/lib/types';
import {ErrorBox, Modal} from './ui';

const StreetMap = dynamic(() => import('./StreetMap'), {ssr:false});
const streetTileUrl = process.env.NEXT_PUBLIC_MAP_TILE_URL;

type Point = {lat: number; lng: number};
type Marker = Point & {name: string};

export function PointMap({markers, point, choose}: {
  markers: Marker[]; point: Point | null; choose?: (point: Point) => void;
}) {
  const points = choose ? markers : [...markers, ...(point ? [point] : [])];
  if (!points.length) return null;
  const padding = choose ? 0.025 : 0.005;
  const west = Math.min(...points.map(p => p.lng)) - padding;
  const east = Math.max(...points.map(p => p.lng)) + padding;
  const north = Math.max(...points.map(p => p.lat)) + padding;
  const south = Math.min(...points.map(p => p.lat)) - padding;
  const x = (p: Point) => (p.lng - west) / (east - west) * 100;
  const y = (p: Point) => (north - p.lat) / (north - south) * 100;
  const plotPoint = point && x(point) >= 0 && x(point) <= 100 && y(point) >= 0 && y(point) <= 100;
  return <figure className="point-map">
    <div className={'point-grid'+(choose ? ' pin-picker' : '')} role={choose ? undefined : 'img'}
      aria-label={choose ? undefined : 'Map of the assigned outlet and your destination'}
      onClick={choose ? event => {
        const bounds = event.currentTarget.getBoundingClientRect();
        choose({
          lat: Number((north - (event.clientY - bounds.top) / bounds.height * (north - south)).toFixed(6)),
          lng: Number((west + (event.clientX - bounds.left) / bounds.width * (east - west)).toFixed(6)),
        });
      } : undefined}>
      <span className="map-north" aria-hidden="true">↑ N</span>
      {markers.map(marker => <span key={marker.name} className="outlet-marker"
        style={{left:x(marker)+'%', top:y(marker)+'%'}} title={marker.name}>
        {!choose && <span>{marker.name}</span>}
      </span>)}
      {plotPoint && <span className="destination-marker" style={{left:x(point)+'%', top:y(point)+'%'}}>
        {!choose && <span>Destination</span>}
      </span>}
    </div>
    <figcaption>{choose
      ? 'Tap the Hyderabad grid to place a pin, or enter coordinates below. Indigo dots mark demo outlets.'
      : 'Indigo marks the assigned outlet. Brick red marks the destination.'} Schematic map · straight-line positions.</figcaption>
  </figure>;
}

export default function Location({cart, outlets, close, save}: {
  cart: Pick<Cart,'lat'|'lng'|'address'>; outlets: Outlet[]; close: () => void; save: (change: {lat:number;lng:number;address:string}) => Promise<unknown>;
}) {
  const [lat, setLat] = useState(cart.lat?.toString() ?? '');
  const [lng, setLng] = useState(cart.lng?.toString() ?? '');
  const [address, setAddress] = useState(cart.address);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [street, showStreet] = useState(false);
  const [tileError, setTileError] = useState(false);
  const choose = useCallback((point: Point) => {
    setLat(String(point.lat));
    setLng(String(point.lng));
    setError('');
  },[]);
  const unavailable = useCallback(() => {
    showStreet(false);
    setTileError(true);
  },[]);
  const point = lat && lng ? {lat:Number(lat),lng:Number(lng)} : null;
  return <Modal title="Set your delivery point" close={close}>
    <form className="modal-body" onSubmit={async event => {
      event.preventDefault();
      setBusy(true);
      setError('');
      try {
        await save({address, lat:Number(lat), lng:Number(lng)});
        close();
      } catch (failure) {
        setError((failure as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <p>We’ll match your point to the nearest open kitchen within its service radius.</p>
      {street && streetTileUrl
        ? <StreetMap markers={outlets} point={point} choose={choose} unavailable={unavailable} tileUrl={streetTileUrl}/>
        : <PointMap markers={outlets} point={point} choose={choose}/>}
      {streetTileUrl && <div className="street-controls">
        <small>{tileError ? 'Street tiles are unavailable. The delivery grid and coordinate fields still work.' : 'Street tiles request the visible map area from the configured provider. Your address is entered here separately.'}</small>
        <button type="button" className="text-button" onClick={() => {setTileError(false);showStreet(!street);}}>
          {street ? 'Use delivery grid' : 'Load street map'}
        </button>
      </div>}
      <label>Try a demo delivery point
        <select defaultValue="" onChange={event => {
          const point = outlets.find(entry => entry.id === event.target.value);
          if (!point) return;
          choose(point);
          setAddress(point.address);
        }}>
          <option value="">Select a neighbourhood point</option>
          {outlets.map(outlet => <option key={outlet.id} value={outlet.id}>{outlet.name}</option>)}
        </select>
      </label>
      <button type="button" className="secondary full" onClick={() => {
        if (!navigator.geolocation) {
          setError('Location access is unavailable. Use the grid or enter coordinates.');
          return;
        }
        navigator.geolocation.getCurrentPosition(
          position => choose({lat:position.coords.latitude, lng:position.coords.longitude}),
          () => setError('Location access is unavailable. Use the grid or enter coordinates.'),
          {timeout:8000},
        );
      }}><LocateFixed size={18}/> Use my current location</button>
      <div className="form-grid">
        <label>Latitude<input required type="number" step="any" min="-90" max="90" value={lat} onChange={event => setLat(event.target.value)}/></label>
        <label>Longitude<input required type="number" step="any" min="-180" max="180" value={lng} onChange={event => setLng(event.target.value)}/></label>
      </div>
      <label>Delivery address<input required minLength={5} maxLength={300} value={address} onChange={event => setAddress(event.target.value)} placeholder="Flat, building, street and landmark"/></label>
      <ErrorBox message={error}/>
      <button className="primary full" disabled={busy}>Confirm location <ArrowRight size={18}/></button>
    </form>
  </Modal>;
}
