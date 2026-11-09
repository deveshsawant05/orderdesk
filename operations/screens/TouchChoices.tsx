'use client';
export default function TouchChoices({label,value,options,onChange}:{label:string;value:string;options:{id:string;name:string}[];onChange:(value:string)=>void}) {
  return <div className="touch-choices" role="group" aria-label={label}>{options.map(option => <button type="button" key={option.id} aria-pressed={value===option.id} className={value===option.id?'selected':''} onClick={()=>onChange(option.id)}>{option.name}</button>)}</div>;
}
