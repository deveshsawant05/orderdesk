'use client';

import {useState} from 'react';
import {api, useResource} from '@/lib/api';
import {ErrorBox} from '@/components/ui';

export type LoyaltyStatus = {
  phone: string | null; balance: number; value_paise: number; cap_percent: number; demo_enabled: boolean;
};

export function useLoyalty(enabled: boolean) {
  return useResource<LoyaltyStatus>(enabled ? '/auth/loyalty' : null);
}

export default function Loyalty({phone, loyalty, points, setPoints, maxPoints}: {
  phone: string; loyalty: ReturnType<typeof useLoyalty>; points: number; setPoints: (points: number) => void; maxPoints: number;
}) {
  const [requestedFor, setRequestedFor] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try { await action(); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  const verified = !!loyalty.data?.phone && loyalty.data.phone === phone;
  if (!loyalty.data?.demo_enabled) return null;
  return <div className="loyalty-panel">
    <h3>Direct-order rewards</h3>
    <p>Earn one point for every ₹100 paid when your order is handed off. Each point is worth ₹1.</p>
    {verified ? <>
      <p role="status">Mobile verified · <b>{loyalty.data.balance} points</b></p>
      {maxPoints > 0 ? <label>Points to redeem<input type="number" min="0" max={maxPoints} step="1"
        value={points} onChange={event => setPoints(Number(event.target.value))}/></label>
        : <small>Earn points on this order. Redemption requires a balance and cannot be combined with a coupon.</small>}
    </> : <>
      <small>Test verification accepts numbers 6000000000–6000000099. Orders can also be placed without rewards.</small>
      <button type="button" className="secondary" disabled={busy || !(/^60000000[0-9]{2}$/).test(phone)}
        onClick={() => run(async () => {
          await api('/auth/loyalty/challenge', 'POST', {phone});
          setRequestedFor(phone);
          setCode('');
        })}>Send verification code</button>
      {requestedFor === phone && requestedFor && <>
        <p role="status">Mock SMS queued. Read the code from the local test inbox.</p>
        <label>Six-digit verification code<input value={code} inputMode="numeric" maxLength={6}
          autoComplete="one-time-code" onChange={event => setCode(event.target.value)}/></label>
        <button type="button" className="secondary" disabled={busy || !(/^[0-9]{6}$/).test(code)}
          onClick={() => run(async () => {
            loyalty.setData(await api<LoyaltyStatus>('/auth/loyalty/verify','POST',{phone,code}));
            setCode('');
          })}>Verify mobile</button>
      </>}
    </>}
    <ErrorBox message={error}/>
  </div>;
}
