import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'OrderDesk · A little more Hyderabad',description:'Direct ordering and kitchen operations for the Company A demonstration.',referrer:'no-referrer'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
