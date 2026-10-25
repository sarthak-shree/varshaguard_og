import { Assistant } from '@/components/assistant';

export default function Home() {
  return (
    <main className="demo">
      <p className="eyebrow">VOICEORBS COMPONENT INTEGRATION</p>
      <h1>VarshaGuard AI</h1>
      <p className="description">
        NebulaOrb powered by Three.js, React Three Fiber, and the original VoiceOrbs shader scene.
      </p>
      <Assistant />
      <p className="status">Initial state: disabled</p>
      <a href="/embed" className="embed-link">Open the embeddable orb</a>
    </main>
  );
}
