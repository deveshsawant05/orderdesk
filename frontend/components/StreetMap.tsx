'use client';

import {useEffect,useRef} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

type Point = {lat:number;lng:number};
type Marker = Point & {name:string};

export default function StreetMap({markers, point, choose, unavailable, tileUrl}: {
  markers:Marker[]; point:Point|null; choose:(point:Point)=>void; unavailable:()=>void; tileUrl:string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map|null>(null);
  const pin = useRef<L.CircleMarker|null>(null);
  useEffect(() => {
    if (!container.current || !markers.length) return;
    const instance = L.map(container.current,{scrollWheelZoom:false,maxZoom:18});
    map.current = instance;
    const layer = L.tileLayer(tileUrl,{
      attribution: process.env.NEXT_PUBLIC_MAP_ATTRIBUTION || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      referrerPolicy:'origin',
      maxZoom:18,
    });
    layer.on('tileerror',unavailable).addTo(instance);
    instance.fitBounds(L.latLngBounds(markers.map(marker => [marker.lat,marker.lng])),{padding:[18,18]});
    markers.forEach(marker => {
      const label = document.createElement('span');
      label.textContent = marker.name;
      L.circleMarker([marker.lat,marker.lng],{
        radius:6,color:'#ffffff',weight:2,fillColor:'#343EA4',fillOpacity:1,
      }).addTo(instance).bindTooltip(label);
    });
    instance.on('click',event => choose({
      lat:Number(event.latlng.lat.toFixed(6)),lng:Number(event.latlng.lng.toFixed(6)),
    }));
    return () => {
      instance.remove();
      map.current = null;
      pin.current = null;
    };
  },[markers,choose,unavailable,tileUrl]);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (pin.current) {pin.current.remove();pin.current = null;}
    if (point) {
      pin.current = L.circleMarker([point.lat,point.lng],{
        radius:8,color:'#fff',weight:2,fillColor:'#B6422C',fillOpacity:1,interactive:false,
      }).addTo(instance);
    }
  },[point]);
  return <div ref={container} className="street-map" aria-label="Hyderabad street map. Tap to place your pin."/>;
}
