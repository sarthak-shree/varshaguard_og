/* Interactive Three.js orb. Fails softly when WebGL/Three.js is unavailable. */
(() => {
  "use strict";
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  const STATES = {
    idle: { color: 0x16b8c5, speed: 0.18, pulse: 0.035 },
    listening: { color: 0x22d3ee, speed: 0.85, pulse: 0.16 },
    thinking: { color: 0xa78bfa, speed: 1.1, pulse: 0.11 },
    speaking: { color: 0x34d399, speed: 0.65, pulse: 0.22 }
  };
  const instances = [];
  function mountOrb(canvas) {
    if (!window.THREE || !canvas || !window.THREE.WebGLRenderer) return null;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    } catch (_error) {
      canvas.hidden = true;
      const fallback = canvas.parentElement?.querySelector(".orb-fallback");
      if (fallback) fallback.hidden = false;
      return null;
    }
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.z = 5;
    const group = new THREE.Group();
    scene.add(group);
    const count = 1500;
    const positions = new Float32Array(count * 3);
    const seed = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2;
      const radius = Math.sqrt(1 - y * y);
      const theta = Math.PI * (3 - Math.sqrt(5)) * i;
      positions[i * 3] = Math.cos(theta) * radius * (1.0 + Math.random() * 0.02);
      positions[i * 3 + 1] = y * (1.0 + Math.random() * 0.02);
      positions[i * 3 + 2] = Math.sin(theta) * radius * (1.0 + Math.random() * 0.02);
      seed[i] = Math.random() * Math.PI * 2;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
    const material = new THREE.PointsMaterial({ color: STATES.idle.color, size: 0.018, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending });
    const points = new THREE.Points(geo, material);
    group.add(points);
    const glow = new THREE.Mesh(new THREE.SphereGeometry(0.74, 32, 32), new THREE.MeshBasicMaterial({ color: STATES.idle.color, transparent: true, opacity: 0.035, side: THREE.BackSide }));
    group.add(glow);
    const ringMaterial = new THREE.MeshBasicMaterial({ color: STATES.idle.color, transparent: true, opacity: 0.32, wireframe: true });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.18, 0.004, 8, 140), ringMaterial);
    ring.rotation.x = 1.1;
    group.add(ring);
    let state = "idle", active = true, hovered = false, start = performance.now();
    let targetSpeed = STATES.idle.speed, targetPulse = STATES.idle.pulse, targetColor = new THREE.Color(STATES.idle.color);
    let audioLevel = 0;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const w = Math.max(1, rect.width || 180), h = Math.max(1, rect.height || 180);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
    };
    const setState = next => {
      if (!STATES[next]) return;
      state = next;
      targetSpeed = STATES[next].speed;
      targetPulse = STATES[next].pulse;
      targetColor.setHex(STATES[next].color);
    };
    canvas.addEventListener("pointermove", event => {
      const r = canvas.getBoundingClientRect();
      group.rotation.y = ((event.clientX - r.left) / r.width - 0.5) * 0.7;
      group.rotation.x = ((event.clientY - r.top) / r.height - 0.5) * 0.35;
    });
    canvas.addEventListener("pointerleave", () => { hovered = false; });
    canvas.addEventListener("pointerenter", () => { hovered = true; });
    canvas.addEventListener("click", () => {
      const modal = document.getElementById("assistantModal");
      modal?.classList.remove("hidden");
      document.getElementById("assistantInput")?.focus();
    });
    const observer = new IntersectionObserver(entries => { active = entries[0]?.isIntersecting ?? true; });
    observer.observe(canvas);
    const frame = now => {
      if (active) {
        const t = (now - start) / 1000;
        material.color.lerp(targetColor, 0.04); ringMaterial.color.lerp(targetColor, 0.04); glow.material.color.lerp(targetColor, 0.04);
        const pulse = 1 + targetPulse * (0.5 + 0.5 * Math.sin(t * (state === "idle" ? 1.2 : 4.8) + audioLevel));
        group.scale.setScalar(pulse + (hovered ? 0.035 : 0));
        points.rotation.y += (reducedMotion ? 0.0005 : 0.002 + targetSpeed * 0.004);
        ring.rotation.z += (reducedMotion ? 0.0004 : 0.002 + targetSpeed * 0.003);
        glow.material.opacity = 0.025 + targetPulse * 0.18;
        renderer.render(scene, camera);
      }
      requestAnimationFrame(frame);
    };
    resize();
    window.addEventListener("resize", resize);
    requestAnimationFrame(frame);
    return { setState, setAudioLevel: level => { audioLevel = Math.max(0, Math.min(1, level || 0)); } };
  }
  function init() {
    document.querySelectorAll("canvas.ai-orb-canvas").forEach(canvas => {
      const instance = mountOrb(canvas);
      if (instance) instances.push({ canvas, instance });
    });
    document.addEventListener("varshaguard:assistant-state", event => {
      instances.forEach(({ canvas, instance }) => {
        const section = canvas.closest(".ai-hero-card,.assistant-dialog");
        if (!section || section.contains(event.target) || event.detail?.global) instance.setState(event.detail?.state || "idle");
      });
    });
    document.querySelectorAll(".assistant-mic-btn").forEach(button => {
      button.addEventListener("click", () => {
        // The voice module dispatches the actual listening/thinking/speaking states.
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
  window.VarshaGuardOrb = {
    setState(state, global = true) {
      document.dispatchEvent(new CustomEvent("varshaguard:assistant-state", { detail: { state, global } }));
    }
  };
})();
