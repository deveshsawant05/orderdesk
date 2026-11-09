'use client';
import Image from 'next/image';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {money,useResource} from '@/lib/api';
import {Menu,Outlet} from '@/lib/types';
import {ErrorBox,FoodMark,Licence,Loading} from '@/components/ui';

export default function MenuDisplay({outlet,revision,menuCode}:{outlet:Outlet;revision:number;menuCode?:{url:string;image:string}}){
 const router=useRouter();
 useEffect(()=>{
  let entered=!!document.fullscreenElement;
  const enter=()=>{if(!document.fullscreenElement)void document.documentElement.requestFullscreen?.().catch(()=>{});};
  const changed=()=>{if(document.fullscreenElement)entered=true;else if(entered)router.replace('/dashboard');};
  const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){if(document.fullscreenElement)void document.exitFullscreen().catch(()=>{});router.replace('/dashboard');}};
  const tap=(event:PointerEvent)=>{if(!(event.target instanceof Element)||!event.target.closest('a,button'))enter();};
  document.addEventListener('fullscreenchange',changed);
  document.addEventListener('keydown',key);
  document.addEventListener('pointerdown',tap);
  if(navigator.userActivation?.isActive)enter();
  return()=>{document.removeEventListener('fullscreenchange',changed);document.removeEventListener('keydown',key);document.removeEventListener('pointerdown',tap);};
 },[router]);
 const menu=useResource<Menu>('/menu?outlet_id='+outlet.id,revision);
 const [position,setPosition]=useState(0);
 const items=menu.data?.items??[],size=items.length,index=size?position%size:0,item=items[index];
 useEffect(()=>{if(size<2)return;const timer=setInterval(()=>setPosition(p=>(p+1)%size),8000);return()=>clearInterval(timer);},[size]);
 return <main className="menu-display immersive-display">
  {menu.error&&<div className="immersive-display-message"><ErrorBox message={menu.error} retry={menu.reload}/></div>}
  {menu.loading&&!menu.data&&<div className="immersive-display-message"><Loading/></div>}
  {item?<article className="immersive-slide" key={item.id}>
   <Image className="immersive-food-photo" src={item.image} alt={item.name} fill sizes="100vw" priority/>
   <div className="immersive-shade"/>
   <div className="immersive-details"><span className="immersive-category"><FoodMark veg={item.vegetarian}/>{menu.data?.categories.find(c=>c.id===item.category_id)?.name}<span>{outlet.name}</span></span><h1>{item.name}</h1><p>{item.description}</p><div className="immersive-price"><b>{money(item.effective_price_paise)}</b><span>{item.portions[0]?.name}<small>Prices include 5% GST</small></span></div>{!item.available&&<span className="immersive-unavailable">{item.in_stock===false?'Currently sold out':'Outside serving hours'}</span>}<small className="immersive-allergens">Allergens · {item.allergens.join(', ')||'Ask the kitchen'}</small></div>
  </article>:menu.data&&<div className="immersive-display-message">No dishes available to display.</div>}
  <div className="immersive-licence"><Licence number={outlet.fssai}/></div>
  {menuCode&&<a className="immersive-qr" href={menuCode.url}><Image src={menuCode.image} alt="QR code for the customer ordering site" width={88} height={88} unoptimized/><span>Scan to order</span></a>}
 </main>;
}
