export type PartyRecord = {
  id: string; status: 'pending'|'accepted'|'rejected'; scheduled_at: string;
  outlet_name: string; reason: string | null; fssai: string; name?: string; address?: string; notes?: string;
  items: {item_id:string; name:string; quantity:number}[];
};

export const partyDate = (date: string) => new Intl.DateTimeFormat('en-IN', {
  timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short',
}).format(new Date(date))+' IST';
