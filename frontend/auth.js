import { initializeApp } from "https://www.gstatic.com/firebasejs/11.10.0/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithPhoneNumber,
  RecaptchaVerifier, onAuthStateChanged, signOut, setPersistence,
  browserLocalPersistence
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-auth.js";
import { firebaseConfig } from "/firebase-config.js";

const statusEl = document.querySelector("#authStatus");
const loginPage = location.pathname.endsWith("/login.html") || location.pathname === "/login.html";
const configReady = firebaseConfig.apiKey && !firebaseConfig.apiKey.startsWith("REPLACE_") &&
  firebaseConfig.projectId && !firebaseConfig.projectId.startsWith("REPLACE_") &&
  firebaseConfig.appId && !firebaseConfig.appId.startsWith("REPLACE_");

function showStatus(message, error = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.dataset.error = error ? "true" : "false";
}
function safeNextPath() {
  const next = new URLSearchParams(location.search).get("next") || "/";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login.html") ? next : "/";
}

if (!configReady) {
  showStatus("Authentication setup is incomplete. Add your Firebase web config in firebase-config.js.", true);
} else {
  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  const googleProvider = new GoogleAuthProvider();
  await setPersistence(auth, browserLocalPersistence);

  onAuthStateChanged(auth, (user) => {
    if (loginPage) {
      if (user) location.replace(safeNextPath());
      return;
    }
    if (!user) {
      location.replace("/login.html?next=" + encodeURIComponent(location.pathname + location.search));
      return;
    }
    const actions = document.querySelector(".topbar-actions") || document.querySelector(".topbar") || document.querySelector("header");
    if (actions && !document.querySelector("#varshaLogoutButton")) {
      const button = document.createElement("button");
      button.id = "varshaLogoutButton";
      button.type = "button";
      button.className = "assistant-open-btn";
      button.textContent = "Log out";
      button.addEventListener("click", async () => {
        button.disabled = true;
        try { await signOut(auth); location.replace("/login.html"); }
        catch (error) { button.disabled = false; showStatus(error.message || "Could not log out.", true); }
      });
      actions.append(button);
    }
  });

  document.querySelector("#googleLogin")?.addEventListener("click", async () => {
    showStatus("Opening Google sign-in…");
    try { await signInWithPopup(auth, googleProvider); }
    catch (error) { showStatus(error.message || "Google sign-in failed.", true); }
  });

  let confirmationResult = null;
  let recaptchaVerifier = null;
  const sendOtpButton = document.querySelector("#sendOtp");
  const verifyOtpButton = document.querySelector("#verifyOtp");
  const phoneInput = document.querySelector("#phoneNumber");
  const otpInput = document.querySelector("#otpCode");

  if (sendOtpButton && phoneInput) {
    sendOtpButton.addEventListener("click", async () => {
      const phone = phoneInput.value.trim();
      if (!/^\+[1-9]\d{7,14}$/.test(phone)) {
        showStatus("Enter a valid phone number in international format, e.g. +919876543210.", true);
        return;
      }
      sendOtpButton.disabled = true;
      try {
        if (recaptchaVerifier) { recaptchaVerifier.clear(); recaptchaVerifier = null; }
        recaptchaVerifier = new RecaptchaVerifier(auth, "recaptcha-container", { size: "invisible" });
        confirmationResult = await signInWithPhoneNumber(auth, phone, recaptchaVerifier);
        otpInput.hidden = false;
        verifyOtpButton.hidden = false;
        showStatus("OTP sent by SMS. Check your messages.");
      } catch (error) {
        if (recaptchaVerifier) { recaptchaVerifier.clear(); recaptchaVerifier = null; }
        showStatus(error.message || "Could not send OTP. Check Firebase phone-auth settings and SMS quota.", true);
      } finally { sendOtpButton.disabled = false; }
    });
  }
  verifyOtpButton?.addEventListener("click", async () => {
    const code = otpInput.value.trim();
    if (!confirmationResult || !/^\d{6}$/.test(code)) {
      showStatus("Enter the six-digit OTP sent to your phone.", true);
      return;
    }
    verifyOtpButton.disabled = true;
    try { await confirmationResult.confirm(code); }
    catch (error) { showStatus(error.message || "OTP verification failed.", true); }
    finally { verifyOtpButton.disabled = false; }
  });
}
