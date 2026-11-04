'use client';

import {useEffect, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export type Point = {lat:number; lng:number};
export type MapMarker = Point & {name:string; destination?:boolean; is_open?:boolean};

const tileUrl = process.env.NEXT_PUBLIC_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const attribution = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

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
      padding:[24,24], maxZoom:15, animate:false,
    });
    layer.addTo(instance);
    for (const marker of markers) {
      const label = document.createElement('span');
      label.textContent = marker.name + (marker.is_open === false ? ' · Closed' : '');
      L.circleMarker([marker.lat,marker.lng], {
        radius:marker.destination ? 5 : 9,
        weight:marker.destination ? 1 : 2,
        color:'#fff',
        fillColor:marker.destination ? '#B6422C' : marker.is_open === false ? '#69646d' : '#343EA4',
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
    instance.fitBounds(line.getBounds(),{padding:[28,28],maxZoom:16,animate:false});
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
