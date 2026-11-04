import {notFound} from 'next/navigation';
import App from '@/components/App';
import type {Menu} from '@/lib/types';

const views = new Set([
  '', 'checkout', 'orders', 'party', 'kitchen',
  'ops', 'ops/login', 'ops/orders', 'ops/menu', 'ops/kitchen',
]);

async function initialMenu(): Promise<Menu | null> {
  const origin = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010';
  try {
    const response = await fetch(origin+'/menu', {cache:'no-store',signal:AbortSignal.timeout(1500)});
    return response.ok ? await response.json() as Menu : null;
  } catch {
    // The live client request supplies retry controls if the API is starting.
    return null;
  }
}

export default async function Page({params}: {params:Promise<{path?:string[]}>}) {
  const {path = []} = await params;
  const route = path.join('/');
  const tracking = path.length === 2 && ['orders','party'].includes(path[0]) && /^[A-Za-z0-9_-]{32,64}$/.test(path[1]);
  if (!views.has(route) && !tracking) notFound();
  return <App initialMenu={route === '' ? await initialMenu() : null}/>;
}
