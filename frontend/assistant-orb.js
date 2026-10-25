/* Bridges VarshaGuard's existing voice lifecycle to the actual Next.js NebulaOrb iframe. */
(() => {
  "use strict";

  const STATES = new Set(["idle", "connecting", "listening", "thinking", "speaking", "error", "disabled"]);
  const ORB_ORIGIN = "https://varshaguard-nebula-orb.vercel.app";
  let currentState = "disabled";

  const LABELS = {
    idle: "Ready to listen",
    connecting: "Connecting…",
    listening: "Listening to you…",
    thinking: "Thinking through the dashboard…",
    speaking: "Speaking response",
    error: "Something went wrong",
    disabled: "Voice mode ready"
  };

  function sendStateToNebula() {
    const frame = document.getElementById("assistantNebulaFrame");
    if (!frame?.contentWindow) return;
    frame.contentWindow.postMessage(
      { type: "varshaguard:orb-state", state: currentState },
      ORB_ORIGIN
    );
  }

  function setState(state) {
    currentState = STATES.has(state) ? state : "idle";
    const dialog = document.querySelector(".assistant-dialog");
    if (dialog) dialog.dataset.assistantState = currentState;

    const label = document.getElementById("assistantOrbState");
    if (label) label.textContent = LABELS[currentState];

    document.querySelectorAll(".ai-hero-card .ai-orb").forEach((orb) => {
      orb.dataset.state = currentState;
      orb.setAttribute("aria-label", currentState === "idle"
        ? "Open VarshaGuard AI assistant"
        : "VarshaGuard AI " + currentState);
    });

    sendStateToNebula();
  }

  function openAssistant() {
    document.getElementById("assistantModal")?.classList.remove("hidden");
    window.VarshaGuardOrb?.setState("idle");
    document.getElementById("assistantInput")?.focus();
  }

  function init() {
    document.querySelectorAll(".ai-hero-card .ai-orb").forEach((button) => {
      button.addEventListener("click", openAssistant);
    });

    const frame = document.getElementById("assistantNebulaFrame");
    frame?.addEventListener("load", sendStateToNebula);

    window.addEventListener("message", (event) => {
      if (event.source !== frame?.contentWindow || event.origin !== ORB_ORIGIN) return;
      if (event.data?.type === "varshaguard:orb-ready") sendStateToNebula();
    });

    document.addEventListener("varshaguard:assistant-state", (event) => {
      setState(event.detail?.state || "idle");
    });

    document.getElementById("assistantVoiceMode")?.addEventListener("click", () => {
      window.setTimeout(sendStateToNebula, 80);
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
