'use client';

import Link from 'next/link';
import {useState} from 'react';
import {AlertTriangle, ArrowRight, Clock, Minus, Plus} from 'lucide-react';
import {api, clock, money, statusName, useResource} from '@/lib/api';
import {Menu, Order, Outlet, User} from '@/lib/types';
import {ErrorBox, Loading} from './ui';
import {OutletReport, PartyDesk} from './ServiceTabs';

const rejectionReasons = ['Item unavailable', 'Kitchen capacity', 'Outside service area', 'Customer requested cancellation'];

export default function ControlRoom({user, outlets, outlet, selectOutlet, revision}: {
  user: User; outlets: Outlet[]; outlet: Outlet; selectOutlet: (id: string) => void; revision: number;
}) {
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState<'live'|'samples'|'party'|'report'>('live');
  const orderTab = tab === 'live' || tab === 'samples';
  const orders = useResource<Order[]>(orderTab ? `/orders?outlet_id=${outlet.id}&snapshots=${tab === 'samples'}` : null, revision);
  const menu = useResource<Menu>(orderTab ? '/menu?outlet_id='+outlet.id : null, revision);
  const order = orders.data?.find(entry => entry.id === selected) ?? orders.data?.[0];
  return <main className="control-room">
    <header className="control-heading">
      <div><span className="eyebrow">OUTLET OPERATIONS / {user.can_manage ? 'CENTRAL ACCESS' : 'MANAGER'}</span>
      <h1>Control Room<span>.</span></h1><p className="muted">Review arrivals, confirm stock and keep the kitchen moving.</p></div>
      <Link href={'/ops/kitchen?outlet='+outlet.id} className="secondary">Enter Kitchen Mode <ArrowRight size={18}/></Link>
    </header>
    <div className="control-toolbar">
      <div className="tabs">
        <button className={tab === 'live' ? 'selected' : ''} onClick={() => setTab('live')}>Live orders</button>
        <button className={tab === 'samples' ? 'selected' : ''} onClick={() => setTab('samples')}>Client samples</button>
        <button className={tab === 'party' ? 'selected' : ''} onClick={() => setTab('party')}>Party requests</button>
        <button className={tab === 'report' ? 'selected' : ''} onClick={() => setTab('report')}>Reporting</button>
      </div>
      {user.can_manage ? <label>Outlet<select value={outlet.id} onChange={event => selectOutlet(event.target.value)}>
        {outlets.map(entry => <option value={entry.id} key={entry.id}>{entry.name}</option>)}
      </select></label> : <strong>{outlet.name}</strong>}
    </div>
    {tab === 'report' && <OutletReport outletId={outlet.id} revision={revision}/>}
    {tab === 'party' && <PartyDesk outletId={outlet.id} revision={revision}/>}
    {orderTab && <><ErrorBox message={orders.error || menu.error} retry={orders.reload}/>
    <div className="control-layout">
      <section className="ledger" aria-label="Order ledger">
        <div className="ledger-head"><span>ORDER / ARRIVAL</span><span>STAGE</span></div>
        {orders.loading && !orders.data && <Loading/>}
        {orders.data?.map(entry => <button key={entry.id} className={entry.id === order?.id ? 'ledger-row selected' : 'ledger-row'}
          aria-pressed={entry.id === order?.id} onClick={() => setSelected(entry.id)}>
          <span><strong>#{String(entry.daily_number).padStart(3, '0')}</strong> <small>{entry.id}</small><br/>
          <span>{clock(entry.placed_at)} IST · {entry.service_date}</span></span>
          <span className={'status-pill '+entry.status}>{statusName(entry.status)}</span>
        </button>)}
        {orders.data?.length === 0 && <p className="ledger-empty">Orders for {outlet.name} will appear here.</p>}
      </section>
      {order ? <Inspector key={order.id} order={order} menu={menu.data} reload={orders.reload}/>
        : <div className="inspector empty"><Clock size={32}/><h2>Waiting for orders</h2><p>Paid orders arrive here automatically.</p></div>}
    </div></>}
  </main>;
}

function Inspector({order, menu, reload}: {order: Order; menu: Menu | null; reload: () => Promise<void>}) {
  const promise = order.revised_at || order.promised_at;
  const [observed] = useState(() => Date.now());
  const [draft, setDraft] = useState<{promise:string;minutes:number}|null>(null);
  const minutes = draft?.promise === promise ? draft.minutes : Math.max(1, Math.min(180, Math.ceil((Date.parse(promise) - observed) / 60000)));
  const setMinutes = (value:number) => setDraft({promise,minutes:value});
  const [revisionReason, setRevisionReason] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const awaiting = order.status === 'new';
  const active = !order.snapshot && (awaiting || order.status === 'preparing');
  const unavailable = order.items.some(line => menu?.items.find(item => item.id === line.item_id)?.in_stock !== true);
  const mutate = async (action: string, body: object, message: string) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api('/orders/'+order.id+'/'+action, 'POST', {...body,version:order.version});
      setNotice(message);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      await reload();
      setBusy(false);
    }
  };
  return <section className="inspector">
    <span className="eyebrow">{order.outlet_name} / {order.service_date}</span>
    <h2>Ticket #{String(order.daily_number).padStart(3, '0')}</h2>
    <div className="inspect-meta"><code>{order.id}</code><span>{statusName(order.status)} · {order.payment_method} TEST</span></div>
    {order.snapshot && <p className="warning">Historical sample · observed 2 November 2026 at 21:20 IST.</p>}
    {order.notifications.some(notification => notification.kind === 'late') &&
      <p className="warning"><AlertTriangle size={16}/> Late alert recorded. Review the current promise.</p>}
    <div className="inspect-items">
      {order.items.map((line,index) => <div key={index}>
        <b>{line.quantity} × {line.name}</b><small>{line.choices.portion}{line.choices.addons.length > 0 && ' · '+line.choices.addons.join(', ')}</small>
        {awaiting && <small>{menu?.items.find(item => item.id === line.item_id)?.in_stock ? 'In stock' : 'Check stock'}</small>}
      </div>)}
    </div>
    <div className="summary-row total"><span>Paid total · GST included</span><b>{money(order.total_paise)}</b></div>
    <p><Clock size={16}/> Promised ready time <b>{clock(promise)} IST</b></p>
    {order.estimate && <p className="muted">{order.snapshot?'Recorded estimate':'Suggested prep'} {order.estimate.predicted_minutes} min · Outlet minimum {order.estimate.minimum_minutes} min</p>}
    {order.resolution_reason && <p className="warning">{order.resolution_reason} · Simulated reversal recorded.</p>}
    <ErrorBox message={error}/>{notice && <p className="success-banner" role="status">{notice}</p>}
    {active && <>
      {awaiting && <button className="primary full" disabled={busy || unavailable}
        onClick={() => mutate('status',{status:'preparing'},'Accepted. Preparation is now live.')}>
        Accept &amp; Start Preparing <ArrowRight size={18}/>
      </button>}
      {awaiting && unavailable && <p className="warning">Resolve unavailable items in Menu &amp; stock, or reject the order.</p>}
      <form className="inspect-form" onSubmit={event => {
        event.preventDefault();
        void mutate('override',{minutes_from_now:minutes,reason:revisionReason},'Ready time updated.');
      }}>
        <h3>Revise the ready time</h3>
        <div className="eta-controls">
          <button type="button" className="secondary" aria-label="Subtract five minutes" onClick={() => setMinutes(Math.max(1,minutes-5))}><Minus size={16}/> 5</button>
          <label>Minutes from now<input type="number" required min={1} max={180} value={minutes} onChange={event => setMinutes(Number(event.target.value))}/></label>
          <button type="button" className="secondary" aria-label="Add five minutes" onClick={() => setMinutes(Math.min(180,minutes+5))}><Plus size={16}/> 5</button>
        </div>
        <label>Reason for the customer<input value={revisionReason} onChange={event => setRevisionReason(event.target.value)} required minLength={5} maxLength={300}/></label>
        <button className="secondary" disabled={busy}>Save revised ready time</button>
      </form>
      <form className="inspect-form" onSubmit={event => {
        event.preventDefault();
        void mutate('status',{status:'cancelled',reason},'Simulated refund recorded.');
      }}>
        <h3>{awaiting ? 'Reject order' : 'Cancel order'}</h3>
        <label>Reason<input required minLength={3} maxLength={300} list="resolution-reasons" value={reason} onChange={event => setReason(event.target.value)}/></label>
        <datalist id="resolution-reasons">{rejectionReasons.map(entry => <option key={entry} value={entry}/>)}</datalist>
        <button className="secondary danger" disabled={busy}>{awaiting ? 'Reject & refund' : 'Cancel & refund'}</button>
      </form>
    </>}
    {order.overrides.length > 0 && <div className="inspect-form"><h3>Promise history</h3>{order.overrides.map((entry,index) => <p key={index}>{clock(entry.revised_at)} IST · {entry.reason}</p>)}</div>}
  </section>;
}
