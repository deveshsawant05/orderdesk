'use client';
import TouchChoices from './TouchChoices';

import {useState} from 'react';
import {api, useResource} from '@/lib/api';
import {PartyRecord, partyDate} from '@/lib/party';
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

export function PartyDesk({outletId, revision, kitchen=false}: {outletId:string;revision:number;kitchen?:boolean}) {
  const requests = useResource<PartyRecord[]>('/staff/party?outlet_id='+outletId,revision);
  if (kitchen && !requests.data?.length) return requests.error ? <ErrorBox message={requests.error} retry={requests.reload}/> : null;
  return <section className={'service-pane'+(kitchen?' kitchen-party':' paper')}>
    <h2>{kitchen ? 'Confirmed party schedule' : 'Party requests'}</h2>
    <ErrorBox message={requests.error} retry={requests.reload}/>
    {requests.loading && !requests.data && <Loading/>}
    {requests.data?.length === 0 && <p className="muted">New catering requests will appear here.</p>}
    {requests.data?.map(entry => <PartyRow key={entry.id} entry={entry} kitchen={kitchen} reload={requests.reload}/>)}
  </section>;
}

function PartyRow({entry, kitchen, reload}: {entry:PartyRecord;kitchen:boolean;reload:()=>Promise<void>}) {
  const [decision, setDecision] = useState<'accepted'|'rejected'>('accepted');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <article className="party-record">
    <strong>{partyDate(entry.scheduled_at)}</strong>
    <p>{entry.items.map(line => line.quantity+' × '+line.name).join(' · ')}</p>
    {!kitchen && <>
      <p>{entry.name} · {entry.address}</p>
      {entry.notes && <p>{entry.notes}</p>}
      <span className="status-pill">{entry.status}</span>
      {entry.reason && <p>{entry.reason}</p>}
      {entry.status === 'pending' && <form onSubmit={async event => {
        event.preventDefault();
        setBusy(true);
        setError('');
        try {
          await api('/staff/party/'+entry.id,'POST',{status:decision,reason});
          await reload();
        } catch (failure) {setError((failure as Error).message);}
        finally {setBusy(false);}
      }}>
        <div className="form-grid">
          <TouchChoices label="Decision" value={decision} options={[{id:"accepted",name:"Confirm capacity"},{id:"rejected",name:"Decline request"}]} onChange={value=>setDecision(value as "accepted"|"rejected")}/>
          <TouchChoices label="Message to customer" value={reason} options={["Confirmed with the kitchen","Item unavailable","Insufficient notice","Kitchen capacity","Outside service area"].map(name=>({id:name,name}))} onChange={setReason}/>
        </div>
        <ErrorBox message={error}/>
        <button className="secondary" disabled={busy||(decision==="rejected"&&!reason)}>Record decision</button>
      </form>}
    </>}
  </article>;
}
