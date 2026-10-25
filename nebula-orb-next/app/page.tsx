'use client';
import { useState } from 'react';
import { NebulaOrb } from '@/registry/orbe/nebula-orb/nebula-orb';
import type { OrbState } from '@/lib/orb-state';
const states: OrbState[] = ['idle','listening','thinking','speaking','disabled'];
export default function Home() {
 const [state,setState] = useState<OrbState>('disabled');
 return <main className="demo"><h1>VarshaGuard AI</h1><p>NebulaOrb — supplied React component</p><NebulaOrb state={state} size={184} speed={1} colorFrom="#818cf8" colorTo="#22d3ee" label="VarshaGuard AI voice assistant" /><div className="controls">{states.map(s=><button key={s} onClick={()=>setState(s)} aria-pressed={state===s}>{s}</button>)}</div><p className="status">State: {state}</p></main>;
}
