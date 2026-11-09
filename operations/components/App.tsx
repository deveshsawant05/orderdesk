'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {usePathname,useRouter} from 'next/navigation';
import {api,useLive,useResource} from '@/lib/api';
import {Outlet,User} from '@/lib/types';
import {ErrorBox,Loading} from './ui';
import Auth from '@/screens/Auth';
import Kitchen from '@/screens/Kitchen';
import ControlRoom from '@/screens/ControlRoom';
import Admin from '@/screens/Admin';
import MenuDisplay from '@/screens/MenuDisplay';
import Dashboard from '@/screens/Dashboard';
export default function App({menuCode}:{menuCode?:{url:string;image:string}}){
 const path=usePathname(),router=useRouter();const [user,setUser]=useState<User|null>(null),[ready,setReady]=useState(false),[error,setError]=useState('');
 const outlets=useResource<Outlet[]>('/outlets');const outlet=outlets.data?.find(o=>o.id===user?.outlet_id)??outlets.data?.[0];
 const live=useLive(user&&outlet?'/events?scope=staff&outlet_id='+outlet.id:null);
 useEffect(()=>{api<User>('/auth/me').then(setUser).catch(()=>{}).finally(()=>setReady(true));},[]);
 if(!ready)return <Loading/>;if(!user)return <Auth onLogin={person=>{setUser(person);router.push(person.role==='kitchen'?'/kitchen':'/orders');}}/>;
 const fixed=user.outlet_id?user:{...user,outlet_id:outlet?.id??null};
 if(!outlet||!outlets.data)return <Loading/>;
 if(path==='/display')return <MenuDisplay outlet={outlet} revision={live.revision} menuCode={menuCode}/>;
 if(path==='/kitchen'||user.role==='kitchen')return <div className="app kitchen-app kds-shell"><Kitchen user={fixed} outlet={outlet} outlets={outlets.data} selectOutlet={()=>{}} revision={live.revision}/></div>;
 return <div className="app operations-app"><header className="topbar"><Link className="ops-brand" href="/orders">OrderDesk <small>OPERATIONS</small></Link><nav aria-label="Operations navigation"><Link href="/dashboard">Dashboard</Link><Link href="/orders">Orders</Link><Link href="/menu">Menu & stock</Link><Link href="/kitchen" onClick={()=>{void document.documentElement.requestFullscreen?.().catch(()=>{});}}>Kitchen mode</Link><Link href="/display">Menu display</Link></nav><button className="text-button" onClick={async()=>{try{await api('/auth/logout','POST');setUser(null);}catch(e){setError((e as Error).message);}}}>Sign out</button></header><ErrorBox message={error}/>{path==='/dashboard'?<Dashboard outletId={outlet.id} outletName={outlet.name} revision={live.revision}/>:path==='/menu'?<Admin user={fixed} outlets={outlets.data} outlet={outlet} selectOutlet={()=>{}} revision={live.revision}/>:<ControlRoom user={fixed} outlets={outlets.data} outlet={outlet} selectOutlet={()=>{}} revision={live.revision}/>}</div>;
}
