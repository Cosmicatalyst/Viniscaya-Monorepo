"use client";
import { useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { Cloud, Cpu, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CloudBoxPicker() {
  const [open, setOpen] = useState(false);
  return <div className="cloud-box-picker">
    <label className="sr-only" htmlFor="compute-picker">Compute location</label>
    <select id="compute-picker" value={open ? "box" : "cloud"} onChange={event => setOpen(event.target.value === "box")}>
      <option value="cloud">Vinicaya Cloud</option><option value="box">Vinicaya box</option>
    </select>
    <Cloud size={16} aria-hidden="true"/>
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Backdrop className="box-modal-backdrop"/>
        <Dialog.Popup className="box-modal">
          <Dialog.Close render={<Button variant="ghost" size="icon" className="box-modal-close" aria-label="Close connection dialog"/>}><X size={18}/></Dialog.Close>
          <div className="pi-stage" aria-hidden="true"><svg className="pi-board" viewBox="0 0 260 130">
            <rect x="6" y="6" width="248" height="118" rx="18" fill="#246347"/>
            {[20,240].flatMap(x => [20,110].map(y => <circle key={`${x}-${y}`} cx={x} cy={y} r="6" fill="#e3c76d"/>))}
            <rect x="67" y="15" width="158" height="16" rx="3" fill="#172c24"/>
            {Array.from({length:20},(_,i)=><rect key={i} x={72+i*7.5} y="19" width="3" height="8" fill="#d7c47f"/>)}
            <rect x="102" y="44" width="52" height="52" rx="4" fill="#222a29"/>
            <rect x="32" y="48" width="39" height="39" rx="3" fill="#b7bec1"/>
            <rect x="90" y="108" width="32" height="18" rx="2" fill="#d4d7d7"/>
            <rect x="148" y="108" width="32" height="18" rx="2" fill="#d4d7d7"/>
            <rect x="191" y="61" width="47" height="35" rx="3" fill="#aaaead"/>
            <text x="128" y="67" textAnchor="middle" fill="#dadcdb" fontSize="8">Raspberry Pi</text>
            <text x="128" y="81" textAnchor="middle" fill="#dadcdb" fontSize="8">Zero 2 W</text>
          </svg></div>
          <Dialog.Title>Connecting to the nearest Vinicaya box…</Dialog.Title>
          <Dialog.Description>Raspberry Pi Zero 2 W</Dialog.Description>
          <p className="box-connection-note"><Cpu size={14}/>Hardware discovery is not configured yet.</p>
          <Dialog.Close render={<Button variant="outline"/>}>Use Vinicaya Cloud</Dialog.Close>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  </div>;
}
