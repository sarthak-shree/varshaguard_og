/* Native voice-orb state, accessibility labels, and dashboard entry point. */
(() => {
  "use strict";
  const STATES = new Set(["idle", "connecting", "listening", "thinking", "speaking", "error", "disabled"]);

  const LABELS = {
    idle: "Ready when you are",
    connecting: "Connecting…",
    listening: "Listening to you…",
    thinking: "Thinking through the dashboard…",
    speaking: "Speaking response",
    error: "Something went wrong",
    disabled: "Voice mode ready"
  };
  const BUTTON_LABELS = {
    idle: "Tap the orb to ask VarshaGuard a question",
    connecting: "Connecting to the microphone",
    listening: "Listening. Tap the orb again when you are finished",
    thinking: "VarshaGuard is preparing an answer",
    speaking: "VarshaGuard is speaking an answer",
    error: "Voice assistant needs attention. Try again",
    disabled: "Voice mode is ready. Tap to begin"
  };

  function setState(next) {
    const currentState = STATES.has(next) ? next : "idle";
    const dialog = document.querySelector(".assistant-dialog");
    const orb = document.getElementById("assistantNativeOrb");
    const panel = document.getElementById("assistantOrbPanel");
    const label = document.getElementById("assistantOrbState");
    if (dialog) dialog.dataset.assistantState = currentState;
    if (panel) panel.dataset.state = currentState;
    if (orb) {
      orb.dataset.state = currentState;
      orb.setAttribute("aria-label", BUTTON_LABELS[currentState]);
      orb.setAttribute("aria-pressed", String(currentState === "listening"));
    }
    if (label) label.textContent = LABELS[currentState];
    document.querySelectorAll(".ai-hero-card .ai-orb").forEach((button) => {
      button.dataset.state = currentState;
    });
  }

  function init() {
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
    setAudioLevel(level) {
      document.dispatchEvent(new CustomEvent("varshaguard:orb-audio-level", {
        detail: { level }
      }));
    }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
