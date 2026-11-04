'use client';

import {useState} from 'react';
import {ArrowRight} from 'lucide-react';
import {api} from '@/lib/api';
import {User} from '@/lib/types';
import {ErrorBox} from './ui';

export default function Auth({onLogin}: {onLogin: (user: User) => void}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <div className="auth-page staff-login">
    <section className="auth-story">
      <span className="ops-brand">OrderDesk <small>OPERATIONS</small></span>
      <div><span className="eyebrow">COMPANY A · HYDERABAD</span><h1>On the pass.</h1>
      <p>Live orders, kitchen tickets and outlet stock.</p></div>
      <small>Staff workspace · Company A demonstration</small>
    </section>
    <section className="auth-panel">
      <span className="eyebrow">STAFF ACCESS</span><h2>Sign in to your outlet.</h2>
      <p>Use your assigned manager or kitchen account.</p>
      <ErrorBox message={error}/>
      <form onSubmit={async event => {
        event.preventDefault();
        setBusy(true);
        setError('');
        const fields = new FormData(event.currentTarget);
        try {
          const user = await api<User>('/auth/login', 'POST', {email:fields.get('email'), password:fields.get('password')});
          if (user.role === 'customer') throw new Error('Use a staff account for operations.');
          onLogin(user);
        } catch (failure) {
          setError((failure as Error).message);
        } finally {
          setBusy(false);
        }
      }}>
        <label>Staff email<input type="email" name="email" required autoComplete="username"/></label>
        <label>Password<input type="password" name="password" required autoComplete="current-password"/></label>
        <button className="primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={18}/></button>
      </form>
    </section>
  </div>;
}
