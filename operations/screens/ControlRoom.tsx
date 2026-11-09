'use client';

import Link from 'next/link';
import {useEffect,useState} from 'react';
import {ArrowRight,Clock,PackageCheck,RefreshCw,Search,UtensilsCrossed,X} from 'lucide-react';
import {api,clock,money,statusName,useResource} from '@/lib/api';
import {Order,Outlet,User} from '@/lib/types';
import {ErrorBox,Loading,Modal} from '@/components/ui';
import {PartyDesk} from './ServiceTabs';
import {PartyRecord} from '@/lib/party';
import TouchChoices from './TouchChoices';

const activeStages=['new','preparing','ready'];
const actions:Record<string,{status:string;label:string}>={new:{status:'preparing',label:'Start preparing'},preparing:{status:'ready',label:'Mark ready'},ready:{status:'handed_off',label:'Confirm handoff'}};
const due=(o:Order)=>Date.parse(o.revised_at||o.promised_at);
const reasons=['Item unavailable','Kitchen capacity','Customer requested cancellation'];

export default function ControlRoom({outlet,revision}:{user:User;outlets:Outlet[];outlet:Outlet|null;selectOutlet:(id:string)=>void;revision:number}){
 const [view,setView]=useState<'live'|'history'|'party'>('live');
 const [filter,setFilter]=useState('all'),[query,setQuery]=useState('');
 const [selected,setSelected]=useState<Order|null>(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [now,setNow]=useState(Date.now);
 const current=useResource<Order[]>('/orders?queue=true'+(outlet?'&outlet_id='+outlet.id:''),revision);
 const archive=useResource<Order[]>(view==='history'?'/orders?history=true'+(outlet?'&outlet_id='+outlet.id:''):null,revision);
 const parties=useResource<PartyRecord[]>('/staff/party'+(outlet?'?outlet_id='+outlet.id:''),revision);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),15000);return()=>clearInterval(timer);},[]);
 const orders=(current.data??[]).filter(o=>activeStages.includes(o.status));
 const overdue=orders.filter(o=>o.status!=='ready'&&due(o)<now).length;
 const pending=parties.data?.filter(p=>p.status==='pending').length??0;
 const entries=(view==='history'?archive.data??[]:orders).filter(o=>(view==='history'||filter==='all'||(filter==='late'?o.status!=='ready'&&due(o)<now:o.status===filter))&&(!query||[o.id,String(o.daily_number),...o.items.map(i=>i.name)].join(' ').toLowerCase().includes(query.toLowerCase()))).sort((a,b)=>view==='history'?Date.parse(b.placed_at)-Date.parse(a.placed_at):due(a)-due(b));
 const latest=selected?[...orders,...(archive.data??[])].find(o=>o.id===selected.id):null;
 const selectedOrder=latest&&selected&&latest.version>=selected.version?latest:selected;
 const reload=async()=>{await Promise.all([current.reload(),archive.reload(),parties.reload()]);};
 const act=async(o:Order,path:string,body:object)=>{
  setBusy(o.id);setError('');setNotice('');
  try{const updated=await api<Order>('/orders/'+o.id+'/'+path,'POST',{...body,version:o.version});if(selected?.id===o.id)setSelected(updated);setNotice(path==='adjust-time'?'Preparation and customer delivery estimate updated.':'Order #'+String(o.daily_number).padStart(3,'0')+' · '+statusName(updated.status));}
  catch(e){setError((e as Error).message);}finally{await reload();setBusy('');}
 };
 const nextDue=[...orders].filter(o=>o.status!=='ready').sort((a,b)=>due(a)-due(b)).slice(0,3);
 return <main className="orders-workspace">
  <header className="orders-heading"><div><span className="eyebrow">{(outlet?.name||'All outlets').toUpperCase()} / ORDER DESK</span><h1>Orders <span>{orders.length} live</span></h1></div><div className="orders-heading-actions"><button className="secondary" aria-label="Refresh orders" onClick={()=>void reload()}><RefreshCw size={17}/></button><Link href="/kitchen" className="primary" onClick={()=>{void document.documentElement.requestFullscreen?.().catch(()=>{});}}><UtensilsCrossed size={17}/> Kitchen board <ArrowRight size={16}/></Link></div></header>
  <nav className="orders-views" aria-label="Order desk views">{([{id:'live',name:'Live orders',count:orders.length},{id:'party',name:'Party requests',count:pending},{id:'history',name:'Order history'}] as const).map(tab=><button key={tab.id} className={view===tab.id?'selected':''} aria-pressed={view===tab.id} onClick={()=>{setView(tab.id);setQuery('');}}>{tab.name}{'count' in tab&&<b>{tab.count}</b>}</button>)}</nav>
  <ErrorBox message={error||current.error||archive.error||parties.error} retry={()=>void reload()}/>{notice&&<div className="orders-notice" role="status">{notice}<button aria-label="Dismiss update" onClick={()=>setNotice('')}><X size={15}/></button></div>}
  {view==='party'?<div className="orders-party-view"><PartyDesk outletId={outlet?.id??null} revision={revision}/></div>:<div className={'orders-workspace-grid'+(view==='history'?' history':'')}>
   <section className="orders-primary" aria-label={view==='history'?'Order history':'Live order grid'}>
    <div className="orders-filterbar">{view==='live'?<div className="orders-filters" role="group" aria-label="Filter live orders">{[{id:'all',name:'All',count:orders.length},...activeStages.map(id=>({id,name:id==='new'?'Incoming':id==='ready'?'Ready':statusName(id),count:orders.filter(o=>o.status===id).length})),{id:'late',name:'Overdue',count:overdue}].map(f=><button key={f.id} className={filter===f.id?'selected '+f.id:f.id} aria-pressed={filter===f.id} onClick={()=>setFilter(f.id)}>{f.name}<b>{f.count}</b></button>)}</div>:<span className="orders-history-caption">Recent fulfilled, cancelled and previous-shift orders</span>}<label className="orders-search"><Search size={16}/><input aria-label="Find an order" placeholder="Order number or dish" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
    {(view==='live'?current.loading&&!current.data:archive.loading&&!archive.data)?<Loading/>:entries.length?<div className="order-ticket-grid">{entries.map(o=>{
     const late=o.status!=='ready'&&activeStages.includes(o.status)&&due(o)<now;
     const remaining=Math.max(0,Math.ceil((due(o)-now)/60000));
     return <article className={'manager-ticket '+o.status+(late?' is-late':'')} key={o.id} data-order-id={o.id}>
      <header><button onClick={()=>setSelected(o)} aria-label={'View order '+o.id}><strong>#{String(o.daily_number).padStart(3,'0')}</strong></button><span className={'status-pill '+o.status}>{statusName(o.status)}</span></header>
      {!outlet&&<span className="ticket-outlet">{o.outlet_name}</span>}<div className="manager-ticket-timing"><span><Clock size={14}/>{activeStages.includes(o.status)?o.status==='ready'?'Awaiting pickup':late?Math.max(1,Math.floor((now-due(o))/60000))+' min overdue':remaining+' min to ready':clock(o.placed_at)+' IST'}</span><small>{o.payment_method}</small></div>
      <div className="manager-ticket-items">{o.items.slice(0,2).map((line,i)=><div key={i}><b>{line.quantity}×</b><span>{line.name}<small>{line.choices.portion}</small></span></div>)}{o.items.length>2&&<small>+{o.items.length-2} more dishes</small>}</div>
      <div className="manager-ticket-summary"><span>Placed {clock(o.placed_at)}<small>Ready {clock(o.revised_at||o.promised_at)}</small></span><b>{money(o.total_paise)}</b></div>
      <footer>{actions[o.status]&&<button className={'ticket-quick-action '+o.status} disabled={!!busy} onClick={()=>void act(o,'status',{status:actions[o.status].status})}>{actions[o.status].label}<ArrowRight size={16}/></button>}<button className="ticket-details-button" onClick={()=>setSelected(o)}>View details</button></footer>
     </article>;
    })}</div>:<div className="orders-empty"><PackageCheck size={35}/><h2>{view==='history'?'No orders found':filter==='all'&&!query?'All caught up':'No matching orders'}</h2><p>{view==='history'?'Completed orders will appear here.':'New orders appear here automatically.'}</p>{(query||filter!=='all')&&<button className="secondary" onClick={()=>{setFilter('all');setQuery('');}}>Clear filters</button>}</div>}
   </section>
   {view==='live'&&<aside className="orders-sidebar"><section className="orders-side-panel"><h2>On the pass</h2><p>Current kitchen workload</p><dl>{activeStages.map(stage=><div key={stage}><dt><i className={stage}/>{stage==='new'?'Awaiting preparation':stage==='ready'?'Ready for pickup':'In preparation'}</dt><dd>{orders.filter(o=>o.status===stage).length}</dd></div>)}</dl>{overdue>0&&<button className="orders-late-link" onClick={()=>setFilter('late')}>{overdue} overdue · review now <ArrowRight size={15}/></button>}</section><section className="orders-side-panel"><h2>Next ready times</h2>{nextDue.map(o=><button key={o.id} className="orders-next-due" onClick={()=>setSelected(o)}><span><b>#{String(o.daily_number).padStart(3,'0')}</b><small>{o.items.reduce((n,i)=>n+i.quantity,0)} items · {statusName(o.status)}</small></span><strong>{clock(o.revised_at||o.promised_at)}</strong></button>)}{!nextDue.length&&<p>No orders waiting to be prepared.</p>}</section><section className="orders-party-callout"><span className="eyebrow">A BIGGER TABLE</span><h2>{pending} party {pending===1?'request':'requests'}</h2><p>{pending?'Waiting for your confirmation.':'New catering requests will appear here.'}</p><button onClick={()=>setView('party')}>Open party desk <ArrowRight size={16}/></button></section></aside>}
  </div>}
  {selectedOrder&&<Modal title={'Order #'+String(selectedOrder.daily_number).padStart(3,'0')} close={()=>setSelected(null)} wide><ErrorBox message={error}/>{notice&&<p className="orders-notice" role="status">{notice}</p>}<OrderInspector order={selectedOrder} busy={!!busy} act={act}/></Modal>}
 </main>;
}

function OrderInspector({order,busy,act}:{order:Order;busy:boolean;act:(o:Order,path:string,body:object)=>Promise<void>}){
 const [cancelling,setCancelling]=useState(false),[reason,setReason]=useState('Item unavailable');const action=actions[order.status];
 return <section className="order-inspector"><div className="order-inspector-meta"><span className={'status-pill '+order.status}>{statusName(order.status)}</span><code>{order.id}</code></div><div className="order-inspector-times"><span>Placed<b>{clock(order.placed_at)} IST</b></span><span>Ready promise<b>{clock(order.revised_at||order.promised_at)} IST</b></span><span>Payment<b>{order.payment_method} · Test</b></span></div><div className="order-inspector-items">{order.items.map((line,i)=><div key={i}><b>{line.quantity}×</b><span>{line.name}<small>{[line.choices.portion,...line.choices.addons].join(' · ')}</small></span><strong>{money(line.unit_paise*line.quantity)}</strong></div>)}</div><div className="order-inspector-total"><span>Paid total · includes 5% GST</span><b>{money(order.total_paise)}</b></div>{order.resolution_reason&&<p className="warning">{order.resolution_reason} · Payment reversal recorded.</p>}{action&&<button className="primary full" disabled={busy} onClick={()=>void act(order,'status',{status:action.status})}>{action.label}<ArrowRight size={17}/></button>}{['new','preparing'].includes(order.status)&&<><div className="order-time-adjust"><span>Adjust preparation<small>Updates the customer’s estimate</small></span><button disabled={busy} onClick={()=>void act(order,'adjust-time',{delta_minutes:-5})}>−5 min</button><button disabled={busy} onClick={()=>void act(order,'adjust-time',{delta_minutes:5})}>+5 min</button></div>{!cancelling?<button className="order-cancel-link" onClick={()=>setCancelling(true)}>Cancel this order</button>:<div className="order-cancel-panel"><h3>Why are you cancelling?</h3><TouchChoices label="Cancellation reason" value={reason} options={reasons.map(name=>({id:name,name}))} onChange={setReason}/><div><button className="secondary" disabled={busy} onClick={()=>setCancelling(false)}>Keep order</button><button className="primary danger" disabled={busy} onClick={()=>void act(order,'status',{status:'cancelled',reason})}>Cancel & refund</button></div></div>}</>}</section>;
}
