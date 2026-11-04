'use client';

import Link from 'next/link';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowRight, CalendarDays, MapPin} from 'lucide-react';
import {api, useLive, useResource} from '@/lib/api';
import {Menu, Outlet} from '@/lib/types';
import {ErrorBox, Loading} from './ui';
import Location from './Location';

export type PartyRecord = {
  id: string; status: 'pending'|'accepted'|'rejected'; scheduled_at: string;
  outlet_name: string; reason: string | null; fssai: string; name?: string; address?: string; notes?: string;
  items: {item_id:string; name:string; quantity:number}[];
};

export const partyDate = (date: string) => new Intl.DateTimeFormat('en-IN', {
  timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short',
}).format(new Date(date))+' IST';

export default function Party({token, outlets}: {token:string;outlets:Outlet[]}) {
  return token ? <PartyTracking token={token}/> : <PartyForm outlets={outlets}/>;
}

function PartyTracking({token}: {token:string}) {
  const live = useLive('/party/tracking/'+token+'/events');
  const request = useResource<PartyRecord>('/party/tracking/'+token, live.revision);
  const party = request.data;
  return <main className="narrow party-page">
    <ErrorBox message={request.error} retry={request.reload}/>
    {request.loading && !party && <Loading/>}
    {party && <>
      <span className="eyebrow">PARTY ORDER · {party.outlet_name}</span>
      <h1>{party.status === 'pending' ? 'Awaiting confirmation.' : party.status === 'accepted' ? 'Your request is confirmed.' : 'Your request was declined.'}</h1>
      <p>{partyDate(party.scheduled_at)}</p>
      {party.reason && <p className="warning">{party.reason}</p>}
      <section className="paper"><h2>Your request</h2>
        {party.items.map(line => <p key={line.item_id}>{line.quantity} × {line.name}</p>)}
        <small>Party request · no payment collected · confirmations are simulated.</small>
      </section>
      <p className="muted">FSSAI · {party.fssai}</p>
      <Link className="secondary" href="/party">Start another request <ArrowRight size={17}/></Link>
    </>}
  </main>;
}

function PartyForm({outlets}: {outlets:Outlet[]}) {
  const router = useRouter();
  const menu = useResource<Menu>('/menu');
  const policy = useResource<{notice_hours:number}>('/party/policy');
  const [location, showLocation] = useState(false);
  const [destination, setDestination] = useState<{lat:number;lng:number;address:string}|null>(null);
  const [quantities, setQuantities] = useState<Record<string,number>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <main className="narrow party-page">
    <span className="eyebrow">THE TABLE IS GETTING BIGGER</span>
    <h1>Food for a gathering.</h1>
    <p>Tell us what you’re planning. An outlet manager will review the request and confirm capacity.</p>
    <ErrorBox message={menu.error || policy.error} retry={() => {void menu.reload();void policy.reload();}}/>
    <form className="paper party-form" onSubmit={async event => {
      event.preventDefault();
      if (!destination) {setError('Choose a delivery point.');return;}
      const fields = new FormData(event.currentTarget);
      const items = Object.entries(quantities).filter(([,quantity]) => quantity > 0).map(([item_id,quantity]) => ({item_id,quantity}));
      if (!items.length) {setError('Add at least one dish to your request.');return;}
      setBusy(true);
      setError('');
      try {
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
      <div className="form-grid">
        <label>Your name<input name="name" required minLength={2} maxLength={80} autoComplete="name"/></label>
        <label>Indian mobile number<input name="phone" required type="tel" pattern="[6-9][0-9]{9}" maxLength={10} autoComplete="tel-national"/></label>
      </div>
      <label><CalendarDays size={16}/> Requested date and time (IST)
        <input type="datetime-local" name="date" required/>
      </label>
      {policy.data && <small>Allow at least {policy.data.notice_hours} hours of notice.</small>}
      <div><button type="button" className="secondary" onClick={() => showLocation(true)}><MapPin size={16}/> {destination ? 'Change delivery point' : 'Choose delivery point'}</button>
      {destination && <p>{destination.address}</p>}</div>
      <fieldset><legend>Dishes and quantities</legend>
        {menu.data?.items.map(item => <label key={item.id} className="party-line">
          {item.name}<input type="number" aria-label={item.name+' quantity'} min="0" max="200" step="1"
            value={quantities[item.id] ?? 0} onChange={event => setQuantities({...quantities,[item.id]:Number(event.target.value)})}/>
        </label>)}
      </fieldset>
      <label>Notes<textarea name="notes" rows={3} maxLength={500} placeholder="Guest count, portion needs or timing details"/></label>
      <ErrorBox message={error}/>
      <button className="primary full" disabled={busy || !menu.data || !policy.data}>Request confirmation <ArrowRight size={18}/></button>
    </form>
    {location && <Location cart={destination ?? {lat:null,lng:null,address:''}} outlets={outlets} close={() => showLocation(false)}
      save={async change => setDestination(change)}/>}
  </main>;
}
