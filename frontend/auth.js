(function () {
  "use strict";

  var holder = document.getElementById("googleButton");
  var msg = document.getElementById("authMsg");
  var clientId = null;
  var scriptReady = false;
  var started = false;

  // After signing in, go back to where the person came from (same site only).
  function nextUrl() {
    var next = new URLSearchParams(window.location.search).get("next") || "/";
    return /^\/(?!\/|\\)/.test(next) ? next : "/";
  }

  function setMsg(text, kind) {
    msg.textContent = text || "";
    msg.className = "auth-msg" + (kind ? " is-" + kind : "");
  }

  function sendToServer(response) {
    setMsg("Signing you in…");
    fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ credential: response.credential }),
    })
      .then(function (res) { return res.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.success) {
          setMsg("Welcome, " + (data.name || "") + "! Taking you in…", "ok");
          window.location.href = nextUrl();
        } else {
          setMsg(data.error || "Could not sign you in. Please try again.", "error");
        }
      })
      .catch(function () {
        setMsg("Network problem. Check your connection and try again.", "error");
      });
  }

  function showButton() {
    if (started || !clientId || !scriptReady || !window.google || !google.accounts) return;
    started = true;
    google.accounts.id.initialize({
      client_id: clientId,
      callback: sendToServer,
      ux_mode: "popup",
      auto_select: false,
      cancel_on_tap_outside: true,
    });
    holder.textContent = "";
    var width = Math.max(200, Math.min(340, holder.clientWidth || 320));
    google.accounts.id.renderButton(holder, {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "continue_with",
      shape: "rectangular",
      logo_alignment: "left",
      width: width,
    });
  }

  // Called by the Google script tag once it has loaded.
  window.vgGoogleReady = function () { scriptReady = true; showButton(); };
  if (window.google && window.google.accounts) { scriptReady = true; }

  // If already signed in, continue to the requested same-site destination.
  fetch("/api/auth/me", { credentials: "same-origin" })
    .then(function (res) { if (res.ok) window.location.replace(nextUrl()); })
    .catch(function () {});

  // Which Google client ID does this server use?
  fetch("/api/auth/config", { credentials: "same-origin" })
    .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
    .then(function (r) {
      if (!r.ok || !r.d.google_client_id) {
        holder.textContent = "";
        setMsg(r.d.error || "Google sign-in is not available right now.", "error");
        return;
      }
      clientId = r.d.google_client_id;
      showButton();
      // The Google script can be blocked (ad blocker, offline): tell the person.
      setTimeout(function () {
        if (!started) {
          holder.textContent = "";
          setMsg("Could not load Google sign-in. Check your connection or disable content blockers, then reload.", "error");
        }
      }, 8000);
    })
    .catch(function () {
      holder.textContent = "";
      setMsg("Could not reach the server. Please try again.", "error");
    });
})();
