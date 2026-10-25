/* Native HTML/CSS orb adapted from https://github.com/gabrstew/Orb */
(() => {
  "use strict";
  const STATES = new Set(["idle","connecting","listening","thinking","speaking","error","disabled"]);
  let currentState = "disabled";

  const LABELS = {
    idle:"Ready to listen",
    connecting:"Connecting…",
    listening:"Listening to you…",
    thinking:"Thinking through the dashboard…",
    speaking:"Speaking response",
    error:"Something went wrong",
    disabled:"Voice mode ready"
  };

  function setState(next) {
    currentState = STATES.has(next) ? next : "idle";
    const dialog = document.querySelector(".assistant-dialog");
    const orb = document.getElementById("assistantNativeOrb");
    const label = document.getElementById("assistantOrbState");
    if (dialog) dialog.dataset.assistantState = currentState;
    if (orb) orb.dataset.state = currentState;
    if (label) label.textContent = LABELS[currentState];
    document.querySelectorAll(".ai-hero-card .ai-orb").forEach((button) => {
      button.dataset.state = currentState;
    });
  }

  function resetOrbPosition() {
    const orb = document.getElementById("assistantNativeOrb");
    if (orb) orb.style.transform = "translate(0,0) rotate(0) scale(1)";
  }

  function init() {
    const orb = document.getElementById("assistantNativeOrb");
    const stage = orb?.closest(".assistant-orb-stage");
    if (orb && stage) {
      stage.addEventListener("pointermove", (event) => {
        if (event.pointerType === "touch") return;
        const rect = stage.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        orb.style.transform = `translate(${x*20}px,${y*20}px) rotate(${x*12}deg) scale(${1+Math.abs(y)*.06})`;
      });
      stage.addEventListener("pointerleave", resetOrbPosition);
    }

    document.querySelectorAll(".ai-hero-card .ai-orb").forEach((button) => {
      button.addEventListener("click", () => {
        document.getElementById("assistantModal")?.classList.remove("hidden");
        window.VarshaGuardOrb?.setState("idle");
        document.getElementById("assistantInput")?.focus();
      });
    });

    document.addEventListener("varshaguard:assistant-state", (event) => {
      setState(event.detail?.state || "idle");
    });
    document.getElementById("assistantVoiceMode")?.addEventListener("click", () => {
      window.setTimeout(() => setState("idle"), 80);
    });
    setState("disabled");
  }

  window.VarshaGuardOrb = {
    setState(state) {
      document.dispatchEvent(new CustomEvent("varshaguard:assistant-state", {
        detail: { state, global: true }
      }));
    },
    setAudioLevel() {}
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once:true});
  else init();
})();
