'use client';

import Link from 'next/link';
import {useEffect,useState} from 'react';
import {ArrowLeft,ArrowRight,Bike,Check,ChefHat,ChevronDown,ClipboardCheck,RefreshCw,Clock,MapPin,PackageCheck,ShoppingBag} from 'lucide-react';
import {api,clock,money,statusName,useResource} from '@/lib/api';
import {Order} from '@/lib/types';
import {TrackingMap} from './Location';
import {Licence,ErrorBox,Loading} from '@/components/ui';

const stages = [
  {status:'new', label:'Order placed', Icon:ClipboardCheck},
  {status:'preparing', label:'Preparing', Icon:ChefHat},
  {status:'ready', label:'Ready', Icon:PackageCheck},
  {status:'handed_off', label:'On the way', Icon:Bike},
];

const statusCopy: Record<string, {title:string; detail:string}> = {
  new:{title:'Order received', detail:'The kitchen will start preparing it shortly.'},
  preparing:{title:'The kitchen is preparing your order', detail:'Your food is being made fresh.'},
  ready:{title:'Your order is packed', detail:'It’s ready for the delivery partner to collect.'},
  handed_off:{title:'Your order is on the way', detail:'The delivery partner has picked up your order.'},
  cancelled:{title:'Order cancelled', detail:'Your test payment was reversed.'},
};

type TrackedOrder = Order & {estimated_arrival_at?:string|null};

function OrderTracking({order, token, error, reload}: {
  order:TrackedOrder; token:string; error:string; reload:()=>void;
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const update=()=>setNow(Date.now());
    const initial=setTimeout(update,0);
    const timer=setInterval(update,15000);
    return ()=>{clearTimeout(initial);clearInterval(timer);};
  }, [order.estimated_arrival_at]);

  const status = statusCopy[order.status];
  const activeStage = stages.findIndex(stage => stage.status === order.status);
  const cancelled = order.status === 'cancelled';
  const inKitchen = order.status === 'new' || order.status === 'preparing';
  const observedAt = order.snapshot_observed_at ? Date.parse(order.snapshot_observed_at) : now;
  const arrival = order.estimated_arrival_at;
  const delayed = (inKitchen && observedAt > Date.parse(order.revised_at || order.promised_at))
    || Boolean(arrival && observedAt > Date.parse(arrival));
  const revision = [...order.notifications].reverse().find(note=>note.kind.startsWith('eta-'));
  const destination = order.destination_lat != null && order.destination_lng != null
    ? {lat:order.destination_lat,lng:order.destination_lng}
    : null;

  const remaining=arrival?Math.max(0,Math.ceil((Date.parse(arrival)-now)/60000)):null;
  return <main className={'tracking-page tracking-inspired'+(cancelled?' is-cancelled':'')}>
    <section className="tracking-status-hero">
      <div className="tracking-status-nav"><Link href="/orders" aria-label="Back to your orders"><ArrowLeft size={23}/></Link><b>{order.outlet_name}</b><button aria-label="Refresh order status" onClick={()=>reload()}><RefreshCw size={21}/></button></div>
      <div className="tracker-update" aria-live="polite"><h1>{status?.title||statusName(order.status)}</h1>
        {!cancelled&&<div className="tracking-countdown">{arrival&&!delayed?<time dateTime={arrival}>Arriving in <b>{remaining} {remaining===1?'min':'mins'}</b></time>:<span>{delayed?'Updating your arrival estimate':'Checking delivery estimate'}</span>}</div>}
        <p>{delayed?'Your order is taking longer than expected.':status?.detail}</p>
      </div>
    </section>
    {error&&<ErrorBox message={error} retry={reload}/>}
    {revision&&<div className="tracking-update-note" role="status"><Clock size={17}/>{revision.message}</div>}
    {cancelled&&order.resolution_reason&&<div className="tracking-update-note" role="status">{order.resolution_reason}</div>}
    {destination && <section className="tracker-card tracker-delivery" aria-label="Delivery map">
      <TrackingMap token={token} outlet={{name:order.outlet_name,lat:order.outlet_lat,lng:order.outlet_lng}}
        destination={destination}/>
      {order.address && <div className="tracker-address"><MapPin size={20} aria-hidden="true"/>
        <div><b>{cancelled ? 'Drop location' : 'Delivering to'}</b><p>{order.address}</p></div>
      </div>}
    </section>}
    <div className="tracking-order-sidebar">
    {!cancelled&&<section className="tracking-progress-card"><ol className="tracker-steps" aria-label="Order progress">{stages.map(({status,label,Icon},index)=><li key={status} className={index<=activeStage?'reached':undefined} aria-current={index===activeStage?'step':undefined}><span>{index<activeStage?<Check size={18}/>:<Icon size={18}/>}</span>{label}</li>)}</ol></section>}
    <details className="tracker-card tracker-details">
      <summary><ShoppingBag size={19} aria-hidden="true"/> Order details <span>{money(order.total_paise)}</span>
        <ChevronDown size={18} aria-hidden="true"/></summary>
      <div className="tracker-receipt">
        {order.items.map((line,i) => <div className="receipt-line" key={i}>
          <b>{line.quantity} ×</b><span>{line.name}<small>{[line.choices.portion,...line.choices.addons].filter(Boolean).join(' · ')}</small></span>
          <b>{money(line.unit_paise*line.quantity)}</b>
        </div>)}
        {order.discount_paise > 0 && <div className="summary-row">
          <span>{order.redeemed_points ? 'Rewards redeemed' : 'Coupon savings'}</span><b>−{money(order.discount_paise)}</b>
        </div>}
        <div className="summary-row total"><b>{order.refunded_at ? 'Reversed' : 'Paid'} · {order.payment_method} simulation</b>
          <b>{money(order.total_paise)}</b></div>
        <small>Includes {money(order.gst_paise)} GST. No real money charged.</small>
        {!destination && order.address && <p className="muted">{order.address}</p>}
      </div>
    </details>
    <p className="tracker-licence"><span className="tracker-reference">{order.id}</span><br/>{order.outlet_name} · <Licence number={order.fssai}/></p>
    </div>
  </main>;
}

export default function OrdersView({revision,signedIn,token}:{revision:number;signedIn:boolean;token:string}){

  const list = useResource<Order[]>(!token && signedIn ? '/orders' : null,revision);
  const single = useResource<TrackedOrder>(token ? '/tracking/'+token : null,revision);

  const profile=useResource<{phone:string}>(signedIn?'/auth/profile':null);
  const [changingPhone,setChangingPhone]=useState(false);
  const [phone,setPhone]=useState(''),[loginError,setLoginError]=useState(''),[logging,setLogging]=useState(false);
  if(!token&&(changingPhone||!signedIn||profile.data&&!profile.data.phone))return <main className="narrow phone-login"><h1>Your orders</h1><p>Enter your mobile number to find your past orders.</p><form onSubmit={async e=>{e.preventDefault();setLogging(true);try{if(!signedIn)await api('/auth/guest','POST');await api('/auth/mobile','POST',{phone});window.location.reload();}catch(e){setLoginError((e as Error).message);}finally{setLogging(false);}}}><label>Mobile number<input type="tel" inputMode="numeric" required pattern="[6-9][0-9]{9}" maxLength={10} autoComplete="tel-national" value={phone} onChange={e=>setPhone(e.target.value)}/></label><ErrorBox message={loginError}/><button className="primary full" disabled={logging}>Continue</button><small>Your order history is linked to this mobile number.</small></form></main>;
  if (token) return single.data
    ? <OrderTracking key={token} order={single.data} token={token} error={single.error} reload={single.reload}/>
    : <main className="narrow"><ErrorBox message={single.error} retry={single.reload}/>{single.loading && <Loading/>}</main>;
  return <main className="orders-page"><span className="eyebrow">GOOD MEALS, REMEMBERED</span><h1>Your orders.</h1>{profile.data?.phone&&<div className="orders-mobile-account"><span>Orders for +91 {profile.data.phone}</span><button className="text-button" onClick={()=>{setPhone(profile.data!.phone);setChangingPhone(true);}}>Change mobile number</button></div>}<ErrorBox message={list.error} retry={list.reload}/>{list.loading&&!list.data?<Loading/>:!list.data?.length?<div className="empty"><ShoppingBag size={40}/><h2>Your first favourite is waiting.</h2><p>Once you order, you’ll find updates and receipts here.</p><Link className="primary" href="/">Explore the menu <ArrowRight size={18}/></Link></div>:<div className="order-list">{list.data.map(o=><Link className="order-row" prefetch={false} href={'/orders/'+o.tracking_token} key={o.id}><div><span className="mono">{o.id}</span><h3>{o.outlet_name}</h3><p>{o.items.map(i=>`${i.quantity} × ${i.name}`).join(' · ')}</p><small>{new Date(o.placed_at).toLocaleDateString('en-IN',{timeZone:'Asia/Kolkata'})} · {clock(o.placed_at)} IST</small></div><div><span className={'status-pill '+o.status}>{statusName(o.status)}</span><b>{money(o.total_paise)}</b><ArrowRight size={20}/></div></Link>)}</div>}</main>;
}
