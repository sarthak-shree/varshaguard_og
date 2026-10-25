/* Mouse-follow movement based on https://github.com/gabrstew/Orb/orb.js */
(() => {
  const orb = document.querySelector("#assistantNativeOrb");
  const stage = orb?.closest(".assistant-orb-stage");
  if (!orb || !stage) return;

  const reset = () => { orb.style.transform = "translate(0,0) rotate(0) scale(1)"; };
  stage.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    const rect = stage.getBoundingClientRect();
    const x = (event.clientX - rect.left) / Math.max(rect.width, 1) - .5;
    const y = (event.clientY - rect.top) / Math.max(rect.height, 1) - .5;
    orb.style.transform = `translate(${x * 20}px,${y * 20}px) rotate(${x * 12}deg) scale(${1 + Math.abs(y) * .06})`;
  });
  stage.addEventListener("pointerleave", reset);
})();
