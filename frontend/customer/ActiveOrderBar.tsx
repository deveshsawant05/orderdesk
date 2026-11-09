'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {Bike,ArrowRight} from 'lucide-react';
import {useLive,useResource} from '@/lib/api';
import {Order} from '@/lib/types';

export default function ActiveOrderBar() {
  const [now,setNow]=useState(Date.now);
  const orders=useResource<Order[]>('/orders');
  const order=orders.data?.find(order=>['new','preparing','ready','handed_off'].includes(order.status)&&now-Date.parse(order.placed_at)<(order.status==='handed_off'?4:12)*3600000);
  const live=useLive(order?.tracking_token?'/tracking/'+order.tracking_token+'/events':null);
  const reload=orders.reload;
  useEffect(()=>{void reload();},[live.revision,reload]);
  useEffect(()=>{const timer=setInterval(()=>{setNow(Date.now());void reload();},30000);return ()=>clearInterval(timer);},[reload]);
  if(!order?.tracking_token)return null;
  const label:Record<string,string>={new:'Order received',preparing:'Preparing your food',ready:'Ready for pickup',handed_off:'Your order is on the way'};
  return <Link href={'/orders/'+order.tracking_token} className="active-order-bar" aria-label={'Track order: '+label[order.status]}><Bike size={25}/><span><strong>{label[order.status]}</strong><small>{order.outlet_name} · View order</small></span><ArrowRight size={20}/></Link>;
}
