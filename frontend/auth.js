(function () {
  "use strict";

  var mode = "login";
  var phone = "";            // number as normalised by the server, e.g. +919876543210
  var timerId = null;
  var verifying = false;

  var $ = function (id) { return document.getElementById(id); };
  var phoneForm = $("phoneForm"), otpForm = $("otpForm");
  var phoneMsg = $("phoneMsg"), otpMsg = $("otpMsg");
  var boxes = Array.prototype.slice.call(document.querySelectorAll("#otpBoxes input"));

  // After signing in, go back to where the person came from (same site only).
  function nextUrl() {
    var next = new URLSearchParams(window.location.search).get("next") || "/";
    return /^\/(?!\/|\\)/.test(next) ? next : "/";
  }

  function setMsg(el, text, kind) {
    el.textContent = text || "";
    el.className = "auth-msg" + (kind ? " is-" + kind : "");
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        data.httpStatus = res.status;
        return data;
      });
    }).catch(function () {
      return { success: false, error: "Network problem. Check your connection and try again." };
    });
  }

  // ----- Log in / Sign up tabs -----
  function setMode(next) {
    mode = next;
    document.querySelectorAll(".auth-tab").forEach(function (tab) {
      var active = tab.dataset.mode === next;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    var signup = next === "signup";
    $("nameField").hidden = !signup;
    $("authTitle").textContent = signup ? "Create your account" : "Welcome back";
    $("authSubtitle").textContent = signup
      ? "Tell us your name and WhatsApp number. We'll check it with a one-time code."
      : "Enter your WhatsApp number and we'll send you a one-time code.";
    setMsg(phoneMsg, "");
  }

  $("authTabs").addEventListener("click", function (e) {
    var tab = e.target.closest(".auth-tab");
    if (tab) setMode(tab.dataset.mode);
  });

  $("authPhone").addEventListener("input", function () {
    this.value = this.value.replace(/\D/g, "").slice(0, 10);
  });

  // ----- step 1: ask for a code -----
  function requestCode() {
    var digits = $("authPhone").value.replace(/\D/g, "");
    if (digits.length !== 10) {
      setMsg(phoneMsg, "Enter a valid 10-digit mobile number.", "error");
      return Promise.resolve(false);
    }
    if (mode === "signup" && $("authName").value.trim().length < 2) {
      setMsg(phoneMsg, "Please enter your name.", "error");
      return Promise.resolve(false);
    }
    $("sendBtn").disabled = true;
    setMsg(phoneMsg, "Sending code…");
    return post("/api/auth/otp/request", {
      purpose: mode, phone: digits, name: $("authName").value,
    }).then(function (data) {
      $("sendBtn").disabled = false;
      if (!data.success) {
        setMsg(phoneMsg, data.error || "Something went wrong.", "error");
        if (data.switch_to) setTimeout(function () { setMode(data.switch_to); }, 1400);
        return false;
      }
      phone = data.phone;
      $("sentTo").textContent = phone.replace(/^(\+91)(\d{5})(\d{5})$/, "$1 $2 $3");
      $("devNote").hidden = !data.dev_mode;
      setMsg(phoneMsg, "");
      startTimer(data.resend_in || 30);
      return true;
    });
  }

  phoneForm.addEventListener("submit", function (e) {
    e.preventDefault();
    requestCode().then(function (sent) {
      if (!sent) return;
      phoneForm.hidden = true;
      otpForm.hidden = false;
      clearBoxes();
      boxes[0].focus();
    });
  });

  // ----- step 2: the six boxes -----
  function clearBoxes() { boxes.forEach(function (b) { b.value = ""; }); }
  function code() { return boxes.map(function (b) { return b.value; }).join(""); }

  boxes.forEach(function (box, i) {
    box.addEventListener("input", function () {
      box.value = box.value.replace(/\D/g, "").slice(-1);
      if (box.value && i < boxes.length - 1) boxes[i + 1].focus();
      if (code().length === boxes.length) otpForm.requestSubmit();
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Backspace" && !box.value && i > 0) boxes[i - 1].focus();
      if (e.key === "ArrowLeft" && i > 0) boxes[i - 1].focus();
      if (e.key === "ArrowRight" && i < boxes.length - 1) boxes[i + 1].focus();
    });
    box.addEventListener("paste", function (e) {
      var text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
      if (!text) return;
      e.preventDefault();
      text.slice(0, boxes.length).split("").forEach(function (ch, k) { boxes[k].value = ch; });
      boxes[Math.min(text.length, boxes.length) - 1].focus();
      if (code().length === boxes.length) otpForm.requestSubmit();
    });
  });

  otpForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (verifying) return;
    if (code().length !== boxes.length) { setMsg(otpMsg, "Enter all 6 digits.", "error"); return; }
    verifying = true;
    $("verifyBtn").disabled = true;
    setMsg(otpMsg, "Checking…");
    post("/api/auth/otp/verify", { phone: phone, code: code() }).then(function (data) {
      verifying = false;
      $("verifyBtn").disabled = false;
      if (data.success) {
        setMsg(otpMsg, "Verified! Taking you in…", "ok");
        window.location.href = nextUrl();
        return;
      }
      setMsg(otpMsg, data.error || "Could not verify the code.", "error");
      var wrap = $("otpBoxes");
      wrap.classList.remove("is-shaking"); void wrap.offsetWidth; wrap.classList.add("is-shaking");
      clearBoxes();
      boxes[0].focus();
      if (data.switch_to) setTimeout(function () { goBack(); setMode(data.switch_to); }, 1400);
    });
  });

  // ----- resend timer -----
  function startTimer(seconds) {
    clearInterval(timerId);
    var left = seconds;
    $("timer").textContent = left;
    $("timerText").hidden = false;
    $("resendBtn").hidden = true;
    timerId = setInterval(function () {
      left -= 1;
      $("timer").textContent = Math.max(left, 0);
      if (left <= 0) {
        clearInterval(timerId);
        $("timerText").hidden = true;
        $("resendBtn").hidden = false;
      }
    }, 1000);
  }

  $("resendBtn").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true;
    setMsg(otpMsg, "Sending a new code…");
    requestCode().then(function (sent) {
      btn.disabled = false;
      if (sent) {
        setMsg(otpMsg, "New code sent on WhatsApp.", "ok");
        clearBoxes();
        boxes[0].focus();
      } else {
        setMsg(otpMsg, phoneMsg.textContent, "error");
      }
    });
  });

  function goBack() {
    clearInterval(timerId);
    otpForm.hidden = true;
    phoneForm.hidden = false;
    setMsg(otpMsg, "");
    $("authPhone").focus();
  }
  $("changeBtn").addEventListener("click", goBack);

  // Already signed in? Skip the form.
  fetch("/api/auth/me", { credentials: "same-origin" })
    .then(function (res) { if (res.ok) window.location.replace(nextUrl()); })
    .catch(function () {});
})();
