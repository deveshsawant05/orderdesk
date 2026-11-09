'use client';
import TouchChoices from './TouchChoices';

import Image from 'next/image';
import {CalendarDays,Check,ChefHat,ArrowRight,Users} from 'lucide-react';
import {Menu} from '@/lib/types';
import {useState} from 'react';
import {api, useResource} from '@/lib/api';
import {PartyRecord, partyDate, partyStatus} from '@/lib/party';
import {ErrorBox, Loading} from '@/components/ui';

type Report = {
  days:number; orders:number; cancelled:number; median_prep_minutes:number|null; repeat_verified_customers:number;
};

export function OutletReport({outletId, revision}: {outletId:string;revision:number}) {
  const [days, setDays] = useState(7);
  const report = useResource<Report>(`/staff/report?outlet_id=${outletId}&days=${days}`,revision);
  return <section className="paper service-pane">
    <TouchChoices label="Reporting window" value={String(days)} options={[7,30,90].map(value=>({id:String(value),name:"Last "+value+" days"}))} onChange={value=>setDays(Number(value))}/>
    <ErrorBox message={report.error} retry={report.reload}/>
    {report.loading && !report.data && <Loading/>}
    {report.data && <dl className="report-list">
      <div><dt>Paid orders</dt><dd>{report.data.orders}</dd></div>
      <div><dt>Cancelled orders</dt><dd>{report.data.cancelled}</dd></div>
      <div><dt>Median prep · start to ready</dt><dd>{report.data.median_prep_minutes === null ? '—' : report.data.median_prep_minutes+' min'}</dd></div>
      <div><dt>Verified customers with 2+ handoffs in this window</dt><dd>{report.data.repeat_verified_customers}</dd></div>
    </dl>}
    <small>Scope is the selected outlet and rolling order placement window.</small>
  </section>;
}

export function PartyDesk({outletId, revision, kitchen=false}: {outletId:string|null;revision:number;kitchen?:boolean}) {
 const requests=useResource<PartyRecord[]>('/staff/party'+(outletId?'?outlet_id='+outletId:''),revision);
 const menu=useResource<Menu>('/menu');
 const [filter,setFilter]=useState('pending');
 const rows=(requests.data??[]).filter(p=>kitchen?['accepted','preparing','ready'].includes(p.status):filter==='all'||(filter==='confirmed'?['accepted','preparing','ready'].includes(p.status):p.status===filter));
 const pending=(requests.data??[]).filter(p=>p.status==='pending').length;
 if(kitchen&&!rows.length)return requests.error?<ErrorBox message={requests.error} retry={requests.reload}/>:null;
 return <section className={'party-desk-v2'+(kitchen?' kitchen-party-board':'')} aria-label={kitchen?'Scheduled party orders':'Party order desk'}>
  <header className="party-desk-heading"><div><span className="eyebrow">{kitchen?'RESERVED FOR LATER':'CATERING / BY CONFIRMATION'}</span><h2>{kitchen?'Scheduled feasts':'Party orders'}</h2><p>{kitchen?'Confirmed catering, separate from immediate orders.':'Review the menu and quantities before reserving kitchen capacity.'}</p></div><span className="party-count"><Users size={18}/>{kitchen?rows.length:pending} {kitchen?'scheduled':'awaiting confirmation'}</span></header>
  {!kitchen&&<TouchChoices label="Party order status" value={filter} onChange={setFilter} options={[{id:'pending',name:'Needs confirmation'},{id:'confirmed',name:'Confirmed & in progress'},{id:'fulfilled',name:'Fulfilled'},{id:'rejected',name:'Declined'},{id:'all',name:'All requests'}]}/>}
  <ErrorBox message={requests.error} retry={requests.reload}/>{requests.loading&&!requests.data&&<Loading/>}
  <div className="party-desk-grid">{rows.map(entry=><PartyRow key={entry.id} entry={entry} kitchen={kitchen} menu={menu.data} reload={requests.reload}/>)}</div>
  {!requests.loading&&!rows.length&&<p className="party-desk-empty">{kitchen?'No confirmed parties scheduled.':'No party orders in this view.'}</p>}
 </section>;
}
function PartyRow({entry,kitchen,menu,reload}:{entry:PartyRecord;kitchen:boolean;menu:Menu|null;reload:()=>Promise<void>}){
 const [declining,setDeclining]=useState(false),[reason,setReason]=useState('Kitchen capacity'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const action=({accepted:{next:'preparing',label:'Start party preparation'},preparing:{next:'ready',label:'Mark feast ready'},ready:{next:'fulfilled',label:'Confirm party handoff'}} as Record<string,{next:string;label:string}>)[entry.status];
 const decide=async(status:string,reason='')=>{setBusy(true);setError('');try{await api('/staff/party/'+entry.id,'POST',{status,reason});await reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <article className={'party-desk-card '+entry.status} data-party-id={entry.id}>
  <header><span className="party-kind"><CalendarDays size={16}/> PARTY ORDER</span><span className={'status-pill '+entry.status}>{partyStatus(entry.status)}</span></header>
  <div className="party-schedule"><small>Scheduled service · IST</small><strong>{partyDate(entry.scheduled_at)}</strong><span>{entry.outlet_name} · {entry.items.reduce((sum,i)=>sum+i.quantity,0)} portions</span></div>
  <div className="party-card-dishes">{entry.items.map(line=>{const dish=menu?.items.find(item=>item.id===line.item_id);return <div key={line.item_id}>{!kitchen&&dish&&<Image src={dish.image} alt="" width={48} height={48}/>}<span>{line.name}</span><b>×{line.quantity}</b></div>;})}</div>
  {!kitchen&&<div className="party-contact"><b>{entry.name}</b><p>{entry.address}</p><small>Quote and payment confirmed separately</small></div>}
  {entry.notes&&<p className="party-card-note">{entry.notes}</p>}{entry.reason&&<p className="party-card-note">{entry.reason}</p>}<ErrorBox message={error}/>
  <footer>{entry.status==='pending'&&!kitchen&&<>{declining?<div className="party-decline"><TouchChoices label="Decline reason" value={reason} options={['Kitchen capacity','Item unavailable','Insufficient notice'].map(name=>({id:name,name}))} onChange={setReason}/><button className="secondary" disabled={busy} onClick={()=>setDeclining(false)}>Keep request</button><button className="primary danger" disabled={busy} onClick={()=>void decide('rejected',reason)}>Confirm decline</button></div>:<><button className="primary" disabled={busy} onClick={()=>void decide('accepted','Confirmed with the kitchen')}><Check size={18}/> Accept party order</button><button className="secondary" disabled={busy} onClick={()=>setDeclining(true)}>Decline</button></>}</>}{action&&<button className="primary full" disabled={busy} onClick={()=>void decide(action.next)}><ChefHat size={18}/>{action.label}<ArrowRight size={17}/></button>}</footer>
 </article>;
}
