'use client';
import Link from 'next/link';
import {useEffect,useRef} from 'react';
import {X,AlertCircle,LoaderCircle,UtensilsCrossed} from 'lucide-react';
export function Brand(){return <Link className="brand" href="/" aria-label="OrderDesk home"><span className="brand-icon"><UtensilsCrossed size={22}/></span><span>OrderDesk<span className="brand-sub">DIRECT FROM THE KITCHEN</span></span></Link>;}
export function ErrorBox({message,retry}:{message:string;retry?:()=>void}){return message?<div className="error" role="alert"><AlertCircle size={19}/><span>{message}</span>{retry&&<button onClick={retry}>Retry</button>}</div>:null;}
export function Loading(){return <div className="loading" role="status"><LoaderCircle className="spin"/> Connecting to your kitchen…</div>;}
export function Modal({title,close,children,wide=false}:{title:string;close:()=>void;children:React.ReactNode;wide?:boolean}){
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const d=ref.current;const overflow=document.body.style.overflow;d?.showModal();document.body.style.overflow='hidden';return()=>{d?.close();document.body.style.overflow=overflow;};},[]);
  return <dialog ref={ref} className={wide?'modal wide':'modal'} onCancel={event=>{event.preventDefault();close();}} onClick={e=>{if(e.target===ref.current)close();}} aria-label={title}><header><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={close}><X/></button></header>{children}</dialog>;
}
export function FoodMark({veg}:{veg:boolean}){return <span className={`food-mark ${veg?'veg':'nonveg'}`} aria-label={veg?'Vegetarian':'Non-vegetarian'}><i/></span>;}
