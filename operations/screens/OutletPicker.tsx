'use client';
import {useState} from 'react';
import {MapPin} from 'lucide-react';
import {Outlet} from '@/lib/types';
import {Modal} from '@/components/ui';
import TouchChoices from './TouchChoices';

export default function OutletPicker({label,value,outlets,onChange}:{label:string;value:string;outlets:Outlet[];onChange:(id:string)=>void}) {
  const [open,setOpen]=useState(false);
  return <><button className="secondary outlet-picker" onClick={()=>setOpen(true)} aria-label={label}><MapPin size={17}/>{outlets.find(outlet=>outlet.id===value)?.name} <small>Change outlet</small></button>{open&&<Modal title="Choose an outlet" close={()=>setOpen(false)} wide><div className="modal-body"><TouchChoices label={label} value={value} options={outlets} onChange={id=>{onChange(id);setOpen(false);}}/></div></Modal>}</>;
}
