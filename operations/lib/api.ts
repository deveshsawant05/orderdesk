'use client';

import {useCallback, useEffect, useRef, useState} from 'react';
import {useRouter} from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL || '/api';
const loopbackHosts = ['localhost', '127.0.0.1'];

function browserApiUrl(path:string) {
  const url = new URL(API+path, window.location.origin);
  if (loopbackHosts.includes(url.hostname) && loopbackHosts.includes(window.location.hostname)) {
    url.hostname = window.location.hostname;
  }
  return url.href;
}

export class ApiError extends Error {
  constructor(public status:number, message:string) {super(message);}
}

export async function api<T>(path:string, method='GET', body?:unknown):Promise<T> {
  const staff = true;
  let response: Response;
  try {
    response = await fetch(browserApiUrl(path),{
      method, credentials:'include',
      headers:{'Content-Type':'application/json','X-OrderDesk':'1','X-OrderDesk-Experience':staff?'staff':'customer'},
      ...(body===undefined ? {} : {body:JSON.stringify(body)}),
    });
  } catch {
    throw new ApiError(0,'Cannot reach OrderDesk. Check that the API and PostgreSQL are running, then retry.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(response.status,typeof detail==='string' ? detail
      : Array.isArray(detail) ? detail.map((entry:{msg:string}) => entry.msg).join('. ') : 'The request failed. Please retry.');
  }
  return data;
}

export function useResource<T>(path:string|null, refresh=0, initial:T|null=null) {
  const [snapshot, setSnapshot] = useState<{path:string;data:T|null;error:string}|null>(null);
  const sequence = useRef({id:0});
  const load = useCallback(async () => {
    if (!path) return;
    const id = ++sequence.current.id;
    try {
      const data = await api<T>(path);
      if (id === sequence.current.id) setSnapshot({path,data,error:''});
    } catch (failure) {
      if (id === sequence.current.id) setSnapshot(current => ({
        path, data:current?.path === path ? current.data : null, error:(failure as Error).message,
      }));
    }
  }, [path]);
  useEffect(() => {
    const counter = sequence.current;
    void load();
    return () => {counter.id++;};
  }, [load, refresh]);
  const setData = (data:T) => {
    if (!path) return;
    sequence.current.id++;
    setSnapshot({path,data,error:''});
  };
  const current = snapshot?.path === path ? snapshot : null;
  return {data:current?.data ?? initial,error:current?.error ?? '',loading:!!path && !current && initial===null,reload:load,setData};
}

export function useLive(path:string|null) {
  const router = useRouter();
  const [revision,setRevision] = useState(0);
  const [connectedPath,setConnectedPath] = useState<string|null>(null);
  useEffect(() => {
    if (!path) return;
    const source = new EventSource(browserApiUrl(path),{withCredentials:true});
    let last = 0;
    let open = false;
    let timer: ReturnType<typeof setTimeout>|undefined;
    const invalidate = () => {
      if (timer === undefined) timer = setTimeout(() => {
        timer = undefined;
        setRevision(value => value+1);
      },100);
    };
    source.onopen = () => {open = true;setConnectedPath(path);invalidate();};
    source.onerror = () => {open = false;setConnectedPath(null);};
    source.onmessage = event => {
      const id = Number(event.lastEventId);
      if (id > last) {last = id;invalidate();}
    };
    source.addEventListener('expired',() => {
      source.close();
      setConnectedPath(null);
      router.replace('/login');
    });
    const poll = setInterval(() => {if (!open) invalidate();},15000);
    return () => {source.close();clearInterval(poll);clearTimeout(timer);};
  }, [path, router]);
  return {revision,connected:path !== null && path === connectedPath};
}

export const money = (n:number) => new Intl.NumberFormat('en-IN',{
  style:'currency',currency:'INR',maximumFractionDigits:n%100===0 ? 0 : 2,
}).format(n/100);
export const clock = (date:string) => new Intl.DateTimeFormat('en-IN',{
  timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:false,
}).format(new Date(date));
export const statusName = (s:string) => ({
  new:'Incoming',preparing:'Preparing',ready:'Ready for pickup',handed_off:'Handed off',cancelled:'Cancelled',
}[s] || s);
