'use client';

import Link from 'next/link';
import Image from 'next/image';
import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowRight, Check, Clock, CalendarDays, MapPin, Minus, Plus} from 'lucide-react';
import {api, useLive, useResource} from '@/lib/api';
import {Menu, Outlet, User} from '@/lib/types';
import {PartyRecord, partyDate, partyStatus} from '@/lib/party';
import {Licence,ErrorBox, FoodMark, Loading} from '@/components/ui';
import Location from './Location';

export default function Party({token, outlets, onIdentity}: {token:string;outlets:Outlet[];onIdentity:(user:User)=>void}) {
  return token ? <PartyTracking token={token}/> : <PartyForm outlets={outlets} onIdentity={onIdentity}/>;
}

function PartyTracking({token}: {token:string}) {
  const live = useLive('/party/tracking/'+token+'/events');
  const request = useResource<PartyRecord>('/party/tracking/'+token, live.revision);
  const party = request.data;
  const menu=useResource<Menu>('/menu');
  return <main className="party-receipt">
    <ErrorBox message={request.error} retry={request.reload}/>
    {request.loading && !party && <Loading/>}
    {party && <>
      <header className={'party-receipt-heading '+party.status}>
        <span className="receipt-icon">{!['pending','rejected'].includes(party.status)?<Check size={30}/>:<Clock size={30}/>}</span>
        <div><span className="eyebrow">YOUR FEAST, IN THE MAKING</span><h1>{party.status==='pending'?'Request received':party.status==='rejected'?'Unable to confirm this request':partyStatus(party.status)}</h1>
        <p>{party.status==='pending'?'The catering manager is checking availability. This page updates automatically.':party.status==='rejected'?'Please try another date or contact the outlet.':'Your scheduled feast is being handled by the catering kitchen.'}</p></div>
      </header>
      <div className="party-receipt-grid"><section className="paper">
        <h2>Your feast</h2>{party.items.map(line=>{const dish=menu.data?.items.find(item=>item.id===line.item_id);return <div className="receipt-dish" key={line.item_id}>
          {dish&&<Image src={dish.image} alt={line.name} width={100} height={75}/>}
          <div><strong>{dish&&<FoodMark veg={dish.vegetarian}/>} {line.name}</strong><small>{dish?.allergens.length?'Allergens · '+dish.allergens.join(', '):'Ask the kitchen about allergens'}</small></div><b>×{line.quantity}</b>
        </div>;})}
      </section><aside className="paper receipt-details"><span className="eyebrow">THE PLAN</span><h2><CalendarDays size={20}/> {partyDate(party.scheduled_at)}</h2><p><MapPin size={18}/> {party.outlet_name}</p>
        <div className="receipt-steps"><span className="done">1 · Request sent</span><span className={!['pending','rejected'].includes(party.status)?'done':''}>2 · Kitchen confirmation</span><span className={['preparing','ready','fulfilled'].includes(party.status)?'done':''}>3 · {['preparing','ready','fulfilled'].includes(party.status)?partyStatus(party.status):'Feast preparation'}</span></div>
        {party.reason&&<p className="warning">{party.reason}</p>}<p>No payment collected. The manager will confirm your final quote.</p><small>Prices include 5% GST.<br/><Licence number={party.fssai}/></small>
        <Link className="secondary full" href="/">Explore the menu <ArrowRight size={17}/></Link>
      </aside></div>
    </>}
  </main>;
}

function PartyForm({outlets,onIdentity}: {outlets:Outlet[];onIdentity:(user:User)=>void}) {
  const router = useRouter();
  const menu = useResource<Menu>('/menu');
  const profile=useResource<{name:string;phone:string}>('/auth/profile');
  const policy = useResource<{notice_hours:number}>('/party/policy');
  const [location, showLocation] = useState(false);
  const [destination, setDestination] = useState<{lat:number;lng:number;address:string}|null>(null);
  const [quantities, setQuantities] = useState<Record<string,number>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [observedAt, setObservedAt] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setObservedAt(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  const notice = policy.data?.notice_hours;
  const earliest = notice === undefined ? undefined : new Date(
    Math.ceil((observedAt+(notice+5.5)*3600000)/60000)*60000,
  ).toISOString().slice(0,16);
  const quantity = Object.values(quantities).reduce((total,value) => total+value,0);
  const changeQuantity = (id:string,value:number) => {
    setQuantities(current => ({...current,[id]:Math.min(200,Math.max(0,Math.trunc(value)))}));
  };
  return <main className="party-page party-order-page">
    <header className="party-intro">
      <div><span className="eyebrow">HYDERABADI CATERING</span><h1>Party orders</h1>
        <p>Bring dum biryani, haleem and Hyderabad’s favourite sides to your table.</p></div>
      {notice !== undefined && <span><CalendarDays size={17}/> Order at least {notice} hours ahead</span>}
    </header>
    <ErrorBox message={menu.error || policy.error} retry={() => {void menu.reload();void policy.reload();}}/>
    <form className="party-form" onSubmit={async event => {
      event.preventDefault();
      if (!destination) {setError('Choose a delivery point.');return;}
      const fields = new FormData(event.currentTarget);
      const items = Object.entries(quantities).filter(([,quantity]) => quantity > 0).map(([item_id,quantity]) => ({item_id,quantity}));
      if (!items.length) {setError('Add at least one dish to your request.');return;}
      setBusy(true);
      setError('');
      try {
        const identity=await api<User>('/auth/guest','POST');
        onIdentity(identity);
        await api('/auth/contact','POST',{name:fields.get('name'),phone:fields.get('phone')});
        const result = await api<{token:string}>('/party','POST',{
          ...destination, name:fields.get('name'), phone:fields.get('phone'), notes:fields.get('notes'),
          scheduled_at:String(fields.get('date'))+':00+05:30',items,
        });
        router.push('/party/'+result.token);
      } catch (failure) {
        setError((failure as Error).message);
      } finally {
        setBusy(false);
      }
    }}>
      <fieldset className="party-catalog"><legend>Build your feast</legend>
        {menu.loading && <Loading/>}
        <div className="party-dishes">
          {menu.data?.items.map(item => {
            const count = quantities[item.id] ?? 0;
            return <article key={item.id} className="party-dish">
              <div className="party-dish-image"><Image src={item.image} alt={item.name} fill
                sizes="(max-width: 440px) 90vw, (max-width: 820px) 46vw, 28vw"/></div>
              <div className="party-dish-info">
                <h3><FoodMark veg={item.vegetarian}/> {item.name}</h3>
                <p>{item.description}</p>
                {item.allergens.length > 0 && <small>Allergens · {item.allergens.join(', ')}</small>}
                <div className="party-quantity">
                  <button type="button" aria-label={'Remove one '+item.name} disabled={count===0}
                    onClick={() => changeQuantity(item.id,count-1)}><Minus size={18}/></button>
                  <input type="number" inputMode="numeric" aria-label={item.name+' quantity'} min="0" max="200" step="1"
                    value={count || ''} placeholder="0" onChange={event => changeQuantity(item.id,Number(event.target.value))}/>
                  <button type="button" aria-label={'Add one '+item.name} disabled={count===200}
                    onClick={() => changeQuantity(item.id,count+1)}><Plus size={18}/></button>
                </div>
              </div>
            </article>;
          })}
        </div>
      </fieldset>
      <section className="paper party-details">
      <h2>Delivery details</h2>
      <p className="muted" role="status">{quantity} {quantity===1 ? 'item' : 'items'} selected</p>
      <div className="form-grid">
        <label>Your name<input name="name" defaultValue={profile.data?.name||''} required minLength={2} maxLength={80} autoComplete="name"/></label>
        <label>Indian mobile number<input name="phone" defaultValue={profile.data?.phone||''} required type="tel" pattern="[6-9][0-9]{9}" maxLength={10} autoComplete="tel-national"/></label>
      </div>
      <label><CalendarDays size={16}/> Requested date and time (IST)
        <input type="datetime-local" name="date" min={earliest} required/>
      </label>
      {notice !== undefined && <small>Allow at least {notice} hours of notice.</small>}
      <div><button type="button" className="secondary" onClick={() => showLocation(true)}><MapPin size={16}/> {destination ? 'Change delivery point' : 'Choose delivery point'}</button>
      {destination && <p>{destination.address}</p>}</div>
      <label>Notes<textarea name="notes" rows={3} maxLength={500} placeholder="Guest count, portion needs or timing details"/></label>
      <ErrorBox message={error}/>
      <button className="primary full" disabled={busy || !menu.data || !policy.data}>Request confirmation <ArrowRight size={18}/></button>
      <small>An outlet manager will confirm availability. No payment is collected with this request.</small>
      </section>
    </form>
    {location && <Location cart={destination ?? {lat:null,lng:null,address:''}} outlets={outlets} close={() => showLocation(false)}
      save={async change => setDestination(change)}/>}
  </main>;
}
