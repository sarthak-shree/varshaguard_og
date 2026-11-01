const $ = (selector) => document.querySelector(selector);
const statusEl = $("#authStatus");
const loginPage = location.pathname.endsWith("/login.html") || location.pathname === "/login.html";
const nextPath = () => {
  const next = new URLSearchParams(location.search).get("next") || "/";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login.html") ? next : "/";
};
function status(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.dataset.error = String(isError);
}
async function api(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST", credentials: "same-origin",
    headers: {"Content-Type":"application/json", "Accept":"application/json"},
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.success) throw new Error(data.error || "Request failed. Please try again.");
  return data;
}
function setBusy(form, busy) {
  form.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
}
function showTab(tabName) {
  document.querySelectorAll("[data-tab]").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.tab === tabName)));
  document.querySelectorAll(".form-panel").forEach((panel) => panel.classList.toggle("active", panel.id === "panel-" + tabName));
  status("");
}
if (!loginPage) {
  fetch("/api/auth/me", {credentials:"same-origin", headers:{"Accept":"application/json"}})
    .then(async (response) => {
      if (!response.ok) throw new Error("not signed in");
      return response.json();
    })
    .then((data) => {
      const actions = document.querySelector(".topbar-actions") || document.querySelector(".topbar") || document.querySelector("header");
      if (!actions || document.querySelector("#varshaLogoutButton")) return;
      const button = document.createElement("button");
      button.id = "varshaLogoutButton"; button.type = "button";
      button.className = "assistant-open-btn"; button.textContent = "Log out";
      button.title = "Signed in as " + data.username;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try { await api("/api/auth/logout"); location.replace("/login.html"); }
        catch (error) { button.disabled = false; window.alert(error.message); }
      });
      actions.append(button);
    })
    .catch(() => location.replace("/login.html?next=" + encodeURIComponent(location.pathname + location.search)));
} else {
  fetch("/api/auth/me", {credentials:"same-origin"})
    .then((response) => { if (response.ok) location.replace(nextPath()); })
    .catch(() => {});
  document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));

  const signupForm = $("#signupForm");
  const signupVerifyForm = $("#signupVerifyForm");
  const forgotForm = $("#forgotForm");
  const forgotVerifyForm = $("#forgotVerifyForm");
  let signupPhone = "";
  let forgotPhone = "";

  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault(); const form = event.currentTarget; setBusy(form, true);
    try {
      await api("/api/auth/login", {username: $("#loginUsername").value.trim(), password: $("#loginPassword").value});
      location.replace(nextPath());
    } catch (error) { status(error.message, true); }
    finally { setBusy(form, false); }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault(); setBusy(signupForm, true);
    signupPhone = $("#signupPhone").value.trim();
    try {
      await api("/api/auth/signup/start", {username: $("#signupUsername").value.trim(), password: $("#signupPassword").value, phone: signupPhone});
      signupForm.classList.add("hidden"); signupVerifyForm.classList.remove("hidden");
      status("WhatsApp OTP sent. Enter the code to finish creating your account.");
      $("#signupCode").focus();
    } catch (error) { status(error.message, true); }
    finally { setBusy(signupForm, false); }
  });

  signupVerifyForm.addEventListener("submit", async (event) => {
    event.preventDefault(); setBusy(signupVerifyForm, true);
    try {
      await api("/api/auth/signup/verify", {phone: signupPhone, code: $("#signupCode").value.trim()});
      status("Account created. Opening your dashboard…"); location.replace(nextPath());
    } catch (error) { status(error.message, true); }
    finally { setBusy(signupVerifyForm, false); }
  });
  $("#signupBack").addEventListener("click", () => {
    signupVerifyForm.classList.add("hidden"); signupForm.classList.remove("hidden");
    $("#signupCode").value = ""; status("Update your details, then request a new OTP.");
  });

  forgotForm.addEventListener("submit", async (event) => {
    event.preventDefault(); setBusy(forgotForm, true); forgotPhone = $("#forgotPhone").value.trim();
    try {
      await api("/api/auth/forgot/start", {phone: forgotPhone});
      forgotForm.classList.add("hidden"); forgotVerifyForm.classList.remove("hidden");
      status("If the number is registered, a WhatsApp OTP has been sent. Enter it below.");
      $("#forgotCode").focus();
    } catch (error) { status(error.message, true); }
    finally { setBusy(forgotForm, false); }
  });
  forgotVerifyForm.addEventListener("submit", async (event) => {
    event.preventDefault(); setBusy(forgotVerifyForm, true);
    try {
      await api("/api/auth/forgot/verify", {phone: forgotPhone, code: $("#forgotCode").value.trim(), new_password: $("#newPassword").value});
      status("Password reset. Opening your dashboard…"); location.replace(nextPath());
    } catch (error) { status(error.message, true); }
    finally { setBusy(forgotVerifyForm, false); }
  });
  status("Sign in, create an account, or reset your password.");
}
