'use client';

import {useEffect, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export type Point = {lat:number; lng:number};
export type MapMarker = Point & {name:string; endpoint?:'hotel'|'drop'; is_open?:boolean};

const tileUrl = process.env.NEXT_PUBLIC_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const attribution = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const endpointIcons = {
  hotel:'<path d="M3 2v7a3 3 0 0 0 6 0V2M6 2v20M21 2c-3 1-5 4-5 7v4h5M21 2v20"/>',
  drop:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM9 21v-7h6v7"/>',
};

function trackingIcon(kind:'hotel'|'drop', name:string) {
  const label = kind === 'hotel' ? 'Hotel' : 'Drop location';
  const marker = document.createElement('span');
  marker.className = 'tracking-map-endpoint';
  marker.setAttribute('role','img');
  marker.setAttribute('aria-label',kind === 'hotel' ? `Hotel · ${name}` : label);
  marker.innerHTML = `<span class="tracking-map-badge"><svg viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true">${endpointIcons[kind]}</svg></span><span class="tracking-map-label">${label}</span>`;
  // Opposite anchors keep both endpoints visible even at the same coordinate.
  return L.divIcon({
    className:'tracking-map-icon '+kind, html:marker,
    iconSize:[34,34], iconAnchor:kind === 'hotel' ? [17,39] : [17,-5],
  });
}

function deliveryPoint(position: L.LatLng): Point {
  const wrapped = position.wrap();
  return {lat:Number(wrapped.lat.toFixed(6)), lng:Number(wrapped.lng.toFixed(6))};
}

export default function StreetMap({markers, point, focus, choose, route, coverage}: {
  markers:MapMarker[]; point?:Point|null; focus?:Point|null; choose?:(point:Point)=>void; route?:Point[]; coverage?:Point&{radius_km:number};
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map|null>(null);
  const pin = useRef<L.Marker|null>(null);
  const tiles = useRef<L.TileLayer|null>(null);
  const [tilesUnavailable, setTilesUnavailable] = useState(false);

  useEffect(() => {
    if (!container.current || !markers.length) return;
    const instance = L.map(container.current, {scrollWheelZoom:true, touchZoom:true, minZoom:3, maxZoom:19});
    map.current = instance;
    const layer = L.tileLayer(tileUrl, {attribution, referrerPolicy:'origin', maxZoom:19});
    tiles.current = layer;
    layer.on('tileerror', () => setTilesUnavailable(true));
    layer.on('tileload', () => setTilesUnavailable(false));
    instance.fitBounds(L.latLngBounds(markers.map(marker => [marker.lat,marker.lng])), {
      padding:choose ? [24,24] : [60,66], maxZoom:15, animate:false,
    });
    layer.addTo(instance);
    for (const marker of markers) {
      if (marker.endpoint) {
        L.marker(marker,{icon:trackingIcon(marker.endpoint,marker.name),interactive:false,keyboard:false}).addTo(instance);
        continue;
      }
      const label = document.createElement('span');
      label.textContent = marker.name + (marker.is_open === false ? ' · Closed' : '');
      L.circleMarker([marker.lat,marker.lng], {
        radius:9,
        weight:2,
        color:'#fff',
        fillColor:marker.is_open === false ? '#69646d' : '#343EA4',
        fillOpacity:1,
      }).addTo(instance).bindTooltip(label);
    }
    if (choose) instance.on('click', event => choose(deliveryPoint(event.latlng)));
    const observer = new ResizeObserver(() => instance.invalidateSize({pan:false, debounceMoveend:true}));
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.remove();
      map.current = null;
      pin.current = null;
      tiles.current = null;
    };
  }, [markers,choose]);

  useEffect(() => {
    const instance = map.current;
    if (instance && focus) instance.setView(focus,Math.max(15,instance.getZoom()),{animate:false});
  }, [focus,markers,choose]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !choose) return;
    if (!point) {
      pin.current?.remove();
      pin.current = null;
      return;
    }
    if (pin.current) {
      pin.current.setLatLng(point);
      return;
    }
    const marker = L.marker(point, {
      alt:'Delivery pin', title:'Drag to adjust your delivery pin', draggable:true,
      icon:L.divIcon({className:'delivery-map-pin', iconSize:[36,40], iconAnchor:[18,37]}),
    }).addTo(instance);
    marker.on('dragend', () => choose(deliveryPoint(marker.getLatLng())));
    pin.current = marker;
  }, [point,markers,choose]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !coverage) return;
    const circle = L.circle(coverage, {
      radius:coverage.radius_km*1000,color:'#343EA4',weight:2,fillOpacity:0.08,interactive:false,
    }).addTo(instance);
    circle.bringToBack();
    return () => {circle.remove();};
  },[coverage,markers,choose]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !route?.length) return;
    const halo = L.polyline(route,{color:'#fff',weight:8,opacity:0.9,interactive:false}).addTo(instance);
    const line = L.polyline(route,{color:'#2548c7',weight:5,opacity:0.95,interactive:false,
      className:'delivery-road-route'}).addTo(instance);
    line.bringToBack();
    halo.bringToBack();
    const bounds = line.getBounds();
    for (const marker of markers) bounds.extend(marker);
    instance.fitBounds(bounds,{padding:[60,66],maxZoom:16,animate:false});
    return () => {line.remove();halo.remove();};
  }, [route,markers,choose]);

  return <div className="street-map-block">
    <div ref={container} className="street-map" role="region"
      aria-label={choose ? 'Hyderabad delivery map' : 'Outlet and destination street map'}/>
    {tilesUnavailable && <p role="status" className="map-tile-error">
      Street tiles couldn’t load. <button type="button" className="text-button" onClick={() => tiles.current?.redraw()}>Retry tiles</button>
    </p>}
  </div>;
}
