'use client';

import Link from 'next/link';
import {useEffect, useState} from 'react';
import {usePathname, useRouter} from 'next/navigation';
import {ArrowRight, ChefHat, LogOut, MapPin, ShoppingBag} from 'lucide-react';
import {api, ApiError, useLive, useResource} from '@/lib/api';
import {Cart, Menu, Outlet, User} from '@/lib/types';
import {Brand, ErrorBox, Loading} from './ui';
import Auth from './Auth';
import MenuView from './MenuView';
import Checkout from './Checkout';
import OrdersView from './OrdersView';
import Kitchen from './Kitchen';
import Admin from './Admin';
import ControlRoom from './ControlRoom';
import Party from './Party';

const emptyCart: Cart = {
  id:'', outlet_id:null, lines:[], address:'', lat:null, lng:null,
  coupon:'', version:1, quote:null, validation_error:null,
};

export default function App({initialMenu}: {initialMenu:Menu|null}) {
  const router = useRouter();
  const path = usePathname();
  const staff = path === '/kitchen' || path.startsWith('/ops');
  const kitchen = path === '/kitchen' || path === '/ops/kitchen';
  const trackingToken = path.startsWith('/orders/') ? path.split('/')[2] : '';
  const [user, setUser] = useState<User | null>(null);
  const [initial, setInitial] = useState(true);
  const [authError, setAuthError] = useState('');
  const [selectedOutlet, setSelectedOutlet] = useState('');
  const outlets = useResource<Outlet[]>(trackingToken ? null : '/outlets');
  const cart = useResource<Cart>(!staff && !trackingToken && user?.role === 'customer' ? '/cart' : null);
  const activeCart = cart.data ?? emptyCart;
  const reloadCart = cart.reload;
  const outletId = staff
    ? user?.outlet_id || (outlets.data?.some(entry => entry.id === selectedOutlet) ? selectedOutlet : outlets.data?.[0]?.id)
    : activeCart.outlet_id;
  const outlet = outlets.data?.find(entry => entry.id === outletId);
  const live = useLive(staff
    ? user ? '/events?scope=staff'+(outletId ? '&outlet_id='+outletId : '') : null
    : trackingToken ? '/tracking/'+trackingToken+'/events' : '/events/menu'+(outletId ? '?outlet_id='+outletId : ''));
  useEffect(() => {
    let active = true;
    if (trackingToken) return;
    void api<User>('/auth/me').then(person => {
      if (active) {
        setUser(person);
        if (staff) setSelectedOutlet(new URLSearchParams(window.location.search).get('outlet') || '');
      }
    }).catch(error => {
      if (!active) return;
      setUser(null);
      if (!(error instanceof ApiError && error.status === 401)) setAuthError(error.message);
    }).finally(() => { if (active) setInitial(false); });
    return () => { active = false; };
  }, [staff, trackingToken]);
  useEffect(() => {
    if (!staff && live.revision && user?.role === 'customer') void reloadCart();
  }, [live.revision, staff, user?.role, reloadCart]);

  const saveCart = async (change: Partial<Cart> | ((current: Cart) => Partial<Cart>)) => {
    let current = activeCart;
    let guest: User | null = null;
    if (!current.id) {
      guest = await api<User>('/auth/guest', 'POST');
      current = await api<Cart>('/cart');
    }
    const {outlet_id, lines, address, lat, lng, coupon, version} = {...current, ...(typeof change === 'function' ? change(current) : change)};
    const saved = await api<Cart>('/cart', 'PUT', {outlet_id, lines, address, lat, lng, coupon, version});
    cart.setData(saved);
    if (guest) setUser(guest);
    return saved;
  };
  const selectOutlet = (id: string) => {
    setSelectedOutlet(id);
    const url = new URL(window.location.href);
    url.searchParams.set('outlet', id);
    window.history.replaceState(null, '', url);
  };
  const signOut = async () => {
    try {
      await api('/auth/logout', 'POST');
      setUser(null);
      setSelectedOutlet('');
      router.replace('/ops/login');
    } catch (error) {
      setAuthError((error as Error).message);
    }
  };

  if (staff && initial) return <Loading/>;
  if (staff && (!user || user.role === 'customer' || path === '/ops/login')) {
    return <><ErrorBox message={authError}/><Auth onLogin={person => {
      setUser(person);
      router.push(person.role === 'kitchen' || kitchen ? '/ops/kitchen' : '/ops/orders');
    }}/></>;
  }

  const count = activeCart.lines.reduce((n, line) => n + line.quantity, 0);
  return <div className={kitchen ? 'app kitchen-app' : 'app'}>
    <header className="topbar">
      {staff ? <Link className="ops-brand" href={user?.role === 'manager' ? '/ops/orders' : '/ops/kitchen'}>OrderDesk <small>OPERATIONS</small></Link> : <Brand/>}
      <nav aria-label={staff ? 'Staff navigation' : 'Customer navigation'}>
        {staff ? <>
          {user?.role === 'manager' && <><Link href="/ops/orders" className={path === '/ops/orders' ? 'active' : ''}>Control Room</Link><Link href="/ops/menu" className={path === '/ops/menu' ? 'active' : ''}>Menu & stock</Link></>}
          <Link href={kitchen ? user?.role === 'manager' ? '/ops/orders' : '/ops' : '/ops/kitchen'} className={kitchen ? 'active' : ''}><ChefHat size={17}/>{kitchen ? 'Exit Kitchen Mode' : 'Kitchen'}</Link>
        </> : <>
          <Link href="/" className={path === '/' ? 'active' : ''}>Menu</Link>
          <Link href="/party" className={path.startsWith('/party') ? 'active' : ''}>Party orders</Link>
          <Link href="/orders" className={path.startsWith('/orders') ? 'active' : ''}>Your orders</Link>
        </>}
      </nav>
      <div className="header-actions">
        {staff ? <button className="icon-button" aria-label="Sign out" onClick={signOut}><LogOut size={19}/></button>
          : <Link className="bag-button" href="/checkout"><ShoppingBag size={19}/><span>Your bag</span><b>{count}</b></Link>}
      </div>
    </header>
    <div className="contextbar">
      <span><MapPin size={14}/>{outlet?.name || (staff ? 'Operations' : 'Hyderabad')} <span className="context-muted"> · Company A</span></span>
      <span className="connection"><i className={live.connected ? 'online' : ''}/>{live.connected ? 'Live connection' : 'Connecting · refresh recovery'}</span>
      <span className="demo-tag">DEMO · TEST PAYMENTS</span>
    </div>
    <ErrorBox message={authError || outlets.error || cart.error} retry={() => { void outlets.reload(); void cart.reload(); }}/>
    {staff ? user && outlet && outlets.data ? (
      user.role === 'kitchen' && !kitchen
        ? <main className="narrow empty"><ChefHat size={42}/><h1>{outlet.name}</h1><p>Your kitchen’s live service board.</p><Link href="/ops/kitchen" className="primary">Enter Kitchen Mode <ArrowRight size={18}/></Link></main>
        : kitchen
        ? <Kitchen key={outlet.id} user={user} outlets={outlets.data} outlet={outlet} selectOutlet={selectOutlet} revision={live.revision}/>
        : path === '/ops/menu'
          ? <Admin key={outlet.id} user={user} outlets={outlets.data} outlet={outlet} selectOutlet={selectOutlet} revision={live.revision}/>
          : <ControlRoom key={outlet.id} user={user} outlets={outlets.data} outlet={outlet} selectOutlet={selectOutlet} revision={live.revision}/>
    ) : !outlets.error && <Loading/>
      : path.startsWith('/party') ? <Party token={path.split('/')[2] || ''} outlets={outlets.data ?? []}/>
        : path.startsWith('/orders')
        ? <OrdersView revision={live.revision} signedIn={user?.role === 'customer'} token={trackingToken}/>
        : path === '/checkout'
          ? initial || (user && cart.loading && !cart.data) ? <Loading/> : <Checkout cart={activeCart} setCart={cart.setData} saveCart={saveCart} outlets={outlets.data ?? []} outlet={outlet}/>
          : <MenuView initialMenu={initialMenu} cart={activeCart} saveCart={saveCart} outlets={outlets.data ?? []} outlet={outlet} revision={live.revision}/>
    }
    {!staff && <footer><Brand/><p>Hyderabad, served directly.<br/><small>Company A demonstration · Synthetic outlet and food information.<br/>Prices include 5% GST. Generated food imagery.</small></p></footer>}
  </div>;
}
