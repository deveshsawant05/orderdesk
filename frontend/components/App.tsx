'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {usePathname} from 'next/navigation';
import {ShoppingBag} from 'lucide-react';
import {api,useResource,useLive} from '@/lib/api';
import {Cart,Menu,User} from '@/lib/types';
import {Brand,ErrorBox,Loading} from './ui';
import ActiveOrderBar from '@/customer/ActiveOrderBar';
import MenuView from '@/customer/MenuView';
import Checkout from '@/customer/Checkout';
import OrdersView from '@/customer/OrdersView';
import Party from '@/customer/Party';
const empty:Cart={id:'',outlet_id:null,lines:[],address:'',lat:null,lng:null,coupon:'',version:1,quote:null,validation_error:null};
export default function App({initialMenu}:{initialMenu:Menu|null}){
 const path=usePathname();const [user,setUser]=useState<User|null>(null),[ready,setReady]=useState(false);
 const outlets=useResource<import('@/lib/types').Outlet[]>('/outlets');
 const cart=useResource<Cart>(user?'/cart':null);const active=cart.data??empty;
 const tracking=path.startsWith('/orders/')?path.split('/')[2]:'';
 const live=useLive(tracking?'/tracking/'+tracking+'/events':'/events/menu'+(active.outlet_id?'?outlet_id='+active.outlet_id:''));
 useEffect(()=>{api<User>('/auth/me').then(setUser).catch(()=>{}).finally(()=>setReady(true));},[]);
 const reload=cart.reload;useEffect(()=>{if(user)void reload();},[live.revision,user,reload]);
 const save=async(change:Partial<Cart>|((current:Cart)=>Partial<Cart>))=>{let current=active;if(!current.id){const guest=await api<User>('/auth/guest','POST');setUser(guest);current=await api<Cart>('/cart');}const {outlet_id,lines,address,lat,lng,coupon,version}={...current,...(typeof change==='function'?change(current):change)};const saved=await api<Cart>('/cart','PUT',{outlet_id,lines,address,lat,lng,coupon,version});cart.setData(saved);return saved;};
 const outlet=outlets.data?.find(o=>o.id===active.outlet_id);
 return <div className="app"><header className="topbar"><Brand/><nav aria-label="Customer navigation"><Link href="/">Menu</Link><Link href="/party">Party orders</Link><Link href="/orders">Your orders</Link></nav><Link className="bag-button" href="/checkout" aria-label="Your bag"><ShoppingBag size={20}/><b>{active.lines.reduce((n,l)=>n+l.quantity,0)}</b></Link></header><ErrorBox message={outlets.error||cart.error}/>
 {path.startsWith('/party')?<Party token={path.split('/')[2]||''} outlets={outlets.data??[]}/>:path.startsWith('/orders')?<OrdersView revision={live.revision} signedIn={!!user} token={tracking}/>:path==='/checkout'?(!ready||user&&cart.loading?<Loading/>:<Checkout cart={active} setCart={cart.setData} saveCart={save} outlets={outlets.data??[]} outlet={outlet}/>):<MenuView initialMenu={initialMenu} cart={active} saveCart={save} outlets={outlets.data??[]} outlet={outlet} revision={live.revision}/>}
 {user&&!tracking&&<ActiveOrderBar/>}<footer><Brand/><p>Hyderabad, served directly.<br/><small>Prices include 5% GST.</small></p></footer></div>;
}
