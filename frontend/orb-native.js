/* Small pointer and microphone reactions for the native voice orb. */
(() => {
  "use strict";

  const orb = document.querySelector("#assistantNativeOrb");
  const stage = orb?.closest(".assistant-orb-stage");
  if (!orb || !stage) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let pointerFrame = 0;
  let audioFrame = 0;
  let pointer = null;
  let audioLevel = 0;

  function paintPointer() {
    pointerFrame = 0;
    if (!pointer || reducedMotion.matches) return;

    const rect = stage.getBoundingClientRect();
    const x = Math.max(-.5, Math.min(.5, (pointer.clientX - rect.left) / Math.max(rect.width, 1) - .5));
    const y = Math.max(-.5, Math.min(.5, (pointer.clientY - rect.top) / Math.max(rect.height, 1) - .5));
    orb.style.setProperty("--orb-shift-x", `${(x * 12).toFixed(1)}px`);
    orb.style.setProperty("--orb-shift-y", `${(y * 12).toFixed(1)}px`);
    orb.style.setProperty("--orb-tilt", `${(x * 8).toFixed(1)}deg`);
  }

  function resetPointer() {
    pointer = null;
    if (pointerFrame) window.cancelAnimationFrame(pointerFrame);
    pointerFrame = 0;
    orb.style.setProperty("--orb-shift-x", "0px");
    orb.style.setProperty("--orb-shift-y", "0px");
    orb.style.setProperty("--orb-tilt", "0deg");
  }

  stage.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch" || reducedMotion.matches) return;
    pointer = event;
    if (!pointerFrame) pointerFrame = window.requestAnimationFrame(paintPointer);
  }, { passive: true });
  stage.addEventListener("pointerleave", resetPointer, { passive: true });
  reducedMotion.addEventListener?.("change", (event) => {
    if (event.matches) resetPointer();
  });

  document.addEventListener("varshaguard:orb-audio-level", (event) => {
    const value = Number(event.detail?.level);
    audioLevel = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
    if (audioFrame) return;

    audioFrame = window.requestAnimationFrame(() => {
      audioFrame = 0;
      const level = ["listening", "speaking"].includes(orb.dataset.state) ? audioLevel : 0;
      if (reducedMotion.matches) {
        orb.style.setProperty("--orb-scale", "1");
        orb.style.setProperty("--orb-glow-size", "36px");
        return;
      }
      orb.style.setProperty("--orb-scale", (1 + level * .055).toFixed(3));
      orb.style.setProperty("--orb-glow-size", `${(36 + level * 48).toFixed(1)}px`);
    });
  });
})();
