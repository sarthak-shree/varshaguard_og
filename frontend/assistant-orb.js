/* Lightweight ring-only visual for VarshaGuard AI; no WebGL or 3D rendering. */
(() => {
  "use strict";

  const validStates = new Set(["idle", "listening", "thinking", "speaking"]);

  function setState(state, global = true) {
    const next = validStates.has(state) ? state : "idle";
    document.querySelectorAll(".ai-orb").forEach(button => {
      const section = button.closest(".ai-hero-card, .assistant-dialog");
      if (global || !section || section.classList.contains("assistant-dialog")) {
        button.dataset.state = next;
        button.setAttribute("aria-label", next === "listening" ? "VarshaGuard AI is listening" :
          next === "thinking" ? "VarshaGuard AI is thinking" :
          next === "speaking" ? "VarshaGuard AI is speaking" : "Open VarshaGuard AI assistant");
      }
    });
    const dialog = document.querySelector(".assistant-dialog");
    if (dialog) dialog.dataset.assistantState = next;
    const stateLabel = document.getElementById("assistantOrbState");
    if (stateLabel) {
      stateLabel.textContent = ({idle:"Ready to help",listening:"Listening…",thinking:"Thinking…",speaking:"Speaking…"})[next];
    }
  }

  function openAssistant() {
    document.getElementById("assistantModal")?.classList.remove("hidden");
    setState("idle");
    document.getElementById("assistantInput")?.focus();
  }

  function init() {
    document.querySelectorAll(".ai-hero-card .ai-orb").forEach(button => {
      button.addEventListener("click", openAssistant);
    });
    document.querySelectorAll(".assistant-dialog .ai-orb").forEach(button => {
      button.addEventListener("click", () => document.getElementById("assistantInput")?.focus());
    });
    document.addEventListener("varshaguard:assistant-state", event => {
      setState(event.detail?.state || "idle", event.detail?.global !== false);
    });
    setState("idle");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  window.VarshaGuardOrb = {
    setState(state, global = true) {
      document.dispatchEvent(new CustomEvent("varshaguard:assistant-state", { detail: { state, global } }));
    },
    setAudioLevel() {}
  };
})();
