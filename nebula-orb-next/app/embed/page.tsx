'use client';

import { useEffect, useState } from 'react';
import { NebulaOrb } from '@/registry/orbe/nebula-orb/nebula-orb';
import type { OrbState } from '@/registry/lib/orb-state';

const ORB_STATES = new Set<OrbState>([
  'idle', 'connecting', 'listening', 'thinking', 'speaking', 'error', 'disabled',
]);

export default function EmbedOrbPage() {
  const [state, setState] = useState<OrbState>('disabled');

  useEffect(() => {
    document.documentElement.dataset.orbEmbed = 'true';
    document.body.dataset.orbEmbed = 'true';

    const queryState = new URLSearchParams(window.location.search).get('state') as OrbState | null;
    if (queryState && ORB_STATES.has(queryState)) setState(queryState);

    const receiveState = (event: MessageEvent) => {
      // This iframe only accepts a restricted visual state from its parent.
      if (event.source !== window.parent || !event.data || typeof event.data !== 'object') return;
      if (event.data.type === 'varshaguard:orb-state' && ORB_STATES.has(event.data.state)) {
        setState(event.data.state as OrbState);
      }
      if (event.data.type === 'varshaguard:orb-ping') {
        window.parent.postMessage({ type: 'varshaguard:orb-ready' }, event.origin);
      }
    };

    window.addEventListener('message', receiveState);
    window.parent.postMessage({ type: 'varshaguard:orb-ready' }, '*');

    return () => {
      window.removeEventListener('message', receiveState);
      delete document.documentElement.dataset.orbEmbed;
      delete document.body.dataset.orbEmbed;
    };
  }, []);

  return (
    <main className="orb-embed-stage" aria-label="VarshaGuard AI visual status">
      <NebulaOrb
        state={state}
        size={184}
        speed={1}
        colorFrom="#818cf8"
        colorTo="#22d3ee"
        label={`VarshaGuard AI ${state}`}
      />
    </main>
  );
}
