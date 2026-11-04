'use client';

import {useState} from 'react';
import {api, useResource} from '@/lib/api';
import {PartyRecord, partyDate} from './Party';
import {ErrorBox, Loading} from './ui';

type Report = {
  days:number; orders:number; cancelled:number; median_prep_minutes:number|null; repeat_verified_customers:number;
};

export function OutletReport({outletId, revision}: {outletId:string;revision:number}) {
  const [days, setDays] = useState(7);
  const report = useResource<Report>(`/staff/report?outlet_id=${outletId}&days=${days}`,revision);
  return <section className="paper service-pane">
    <label>Reporting window<select value={days} onChange={event => setDays(Number(event.target.value))}>
      {[7,30,90].map(value => <option key={value} value={value}>Last {value} days</option>)}
    </select></label>
    <ErrorBox message={report.error} retry={report.reload}/>
    {report.loading && !report.data && <Loading/>}
    {report.data && <dl className="report-list">
      <div><dt>Paid orders</dt><dd>{report.data.orders}</dd></div>
      <div><dt>Cancelled orders</dt><dd>{report.data.cancelled}</dd></div>
      <div><dt>Median prep · acceptance to ready</dt><dd>{report.data.median_prep_minutes === null ? '—' : report.data.median_prep_minutes+' min'}</dd></div>
      <div><dt>Verified customers with 2+ handoffs in this window</dt><dd>{report.data.repeat_verified_customers}</dd></div>
    </dl>}
    <small>Scope is the selected outlet and rolling order placement window. Client snapshots are excluded.</small>
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
          <label>Decision<select value={decision} onChange={event => setDecision(event.target.value as 'accepted'|'rejected')}>
            <option value="accepted">Confirm capacity</option><option value="rejected">Reject request</option>
          </select></label>
          <label>Message to customer<input value={reason} onChange={event => setReason(event.target.value)}
            maxLength={300} minLength={decision==='rejected'?3:0} required={decision==='rejected'} list={'party-reasons-'+entry.id}/></label>
          <datalist id={'party-reasons-'+entry.id}>
            {['Item unavailable','Insufficient notice','Kitchen capacity','Outside service area'].map(text => <option value={text} key={text}/>)}
          </datalist>
        </div>
        <ErrorBox message={error}/>
        <button className="secondary" disabled={busy}>Record decision</button>
      </form>}
    </>}
  </article>;
}
