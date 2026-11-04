'use client';

import {useEffect, useState} from 'react';
import {AlertTriangle, ArrowRight, Clock, PackageCheck} from 'lucide-react';
import {api, clock, statusName, useResource} from '@/lib/api';
import {Order, Outlet, User} from '@/lib/types';
import {ErrorBox, Loading} from './ui';
import {PartyDesk} from './ServiceTabs';

const stages = ['new', 'preparing', 'ready'];
const labels: Record<string,string> = {new:'Awaiting acceptance', preparing:'Preparing', ready:'Ready for pickup'};
const dueAt = (order: Order) => Date.parse(order.revised_at || order.promised_at);

export default function Kitchen({user, outlets, outlet, selectOutlet, revision}: {
  user: User; outlets: Outlet[]; outlet: Outlet; selectOutlet: (id: string) => void; revision: number;
}) {
  const [snapshots, setSnapshots] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const orders = useResource<Order[]>(`/orders?outlet_id=${outlet.id}&snapshots=${snapshots}&queue=true`, revision);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const change = async (order: Order, status: string) => {
    setBusy(order.id);
    setError('');
    try {
      await api('/orders/'+order.id+'/status', 'POST', {status,version:order.version});
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      await orders.reload();
      setBusy('');
    }
  };
  return <main className="kitchen-page">
    <div className="kitchen-heading">
      <div><span className="eyebrow">KITCHEN MODE · {new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium'}).format(now)}</span>
      <h1>{outlet.name}</h1></div>
      <div className="kitchen-tools">
        <span className="kitchen-clock">{clock(new Date(now).toISOString())}<small> IST</small></span>
        {user.can_manage && <select aria-label="Kitchen outlet" value={outlet.id} onChange={event => selectOutlet(event.target.value)}>
          {outlets.map(entry => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
        </select>}
        <button className="secondary" onClick={async () => {
          try {
            if (document.fullscreenElement) await document.exitFullscreen();
            else await document.documentElement.requestFullscreen();
          } catch { setError('Full screen is unavailable on this device.'); }
        }}>Toggle full screen</button>
      </div>
    </div>
    <div className="kitchen-summary"><span>Service board</span><div className="tabs">
      <button className={!snapshots ? 'selected' : ''} onClick={() => setSnapshots(false)}>Live kitchen</button>
      <button className={snapshots ? 'selected' : ''} onClick={() => setSnapshots(true)}>Client samples</button>
    </div></div>
    {snapshots && <p className="warning">Historical samples · observed 2 November 2026 at 21:20 IST.</p>}
    <ErrorBox message={error || orders.error} retry={orders.reload}/>
    {orders.loading && !orders.data ? <Loading/> : <div className="kitchen-board three-stage">
      {stages.map(stage => {
        const tickets = orders.data?.filter(order => order.status === stage).sort((a,b) => dueAt(a)-dueAt(b)) ?? [];
        return <section className={'kitchen-column '+stage} key={stage}>
          <header><span><i/>{labels[stage]}</span><b>{tickets.length}</b></header>
          <div className="ticket-stack">
            {tickets.map(order => {
              const observed = order.snapshot ? Date.parse(order.snapshot_observed_at!) : now;
              const difference = observed - dueAt(order);
              const late = difference > 0 && stage !== 'ready';
              const duration = late ? Math.floor(difference/60000) : Math.max(0,Math.ceil(-difference/60000));
              return <article className={'ticket'+(late ? ' late' : '')} key={order.id} data-order-id={order.id}>
                <div className="ticket-id"><b>#{String(order.daily_number).padStart(3, '0')}</b>{late && <AlertTriangle size={28}/>}</div>
                <div className="ticket-reference">{order.id} · {order.service_date}</div>
                <div className={'ticket-timer'+(late ? ' late-text' : '')}>
                  <Clock size={20}/>{stage === 'ready' ? statusName(stage) : late ? `Late by ${duration} min` : `${duration} min to promise`}
                </div>
                <div className="ticket-times"><span>IN <b>{clock(order.placed_at)}</b></span><span>READY <b>{clock(new Date(dueAt(order)).toISOString())}</b></span></div>
                <div className="ticket-items">{order.items.map((line,index) => <div key={index}>
                  <b>{line.quantity}<small>×</small></b><span>{line.name}<small>{line.choices.portion}{line.choices.addons.length ? ' + '+line.choices.addons.join(', ') : ''}</small></span>
                </div>)}</div>
                {stage === 'new' && <p className="ticket-waiting">Manager acceptance required</p>}
                {order.notifications.some(notification => notification.kind === 'late') && <p className="manager-alert">Manager alerted</p>}
                {!order.snapshot && stage !== 'new' && <button className="ticket-action" disabled={busy === order.id}
                  onClick={() => change(order, stage === 'preparing' ? 'ready' : 'handed_off')}>
                  {stage === 'preparing' ? 'Mark ready' : 'Confirm handoff'} <ArrowRight size={22}/>
                </button>}
              </article>;
            })}
            {tickets.length === 0 && <div className="column-empty"><PackageCheck size={28}/><p>No tickets in this stage.</p></div>}
          </div>
        </section>;
      })}
    </div>}
    {!snapshots && <PartyDesk outletId={outlet.id} revision={revision} kitchen/>}
  </main>;
}
