'use client';

import { NebulaOrb } from '@/registry/orbe/nebula-orb/nebula-orb';

export const Assistant = () => (
  <NebulaOrb
    state="disabled"
    size={184}
    speed={1}
    colorFrom="#818cf8"
    colorTo="#22d3ee"
  />
);

export default function Home() {
  return (
    <main className="demo">
      <p className="eyebrow">VOICEORBS COMPONENT INTEGRATION</p>
      <h1>VarshaGuard AI</h1>
      <p className="description">NebulaOrb powered by Three.js, React Three Fiber, and the original VoiceOrbs shader scene.</p>
      <Assistant />
      <p className="status">Initial state: disabled</p>
      <a href="/embed" className="embed-link">Open the embeddable orb</a>
    </main>
  );
}
