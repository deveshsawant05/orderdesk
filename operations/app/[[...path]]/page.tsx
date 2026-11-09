import {notFound} from 'next/navigation';
import QRCode from 'qrcode';
import App from '@/components/App';
export default async function Page({params}:{params:Promise<{path?:string[]}>}){const {path=[]}=await params;if(!['','login','orders','dashboard','kitchen','menu','display'].includes(path.join('/')))notFound();const origin=process.env.CUSTOMER_SITE_URL;const url=origin?URL.parse('/',origin):null;const menuCode=url&&['http:','https:'].includes(url.protocol)?{url:url.href,image:await QRCode.toDataURL(url.href,{width:224,margin:4})}:undefined;return <App menuCode={menuCode}/>;}
