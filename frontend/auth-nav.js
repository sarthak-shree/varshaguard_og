// Turns the "Log in" link in the top bar into "<name> · Log out" once signed in.
(function () {
  "use strict";
  var link = document.getElementById("authNav");
  if (!link) return;

  fetch("/api/auth/me", { credentials: "same-origin" })
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (me) {
      if (!me || !me.success) return;
      var chip = document.createElement("span");
      chip.className = "auth-nav auth-nav-user";
      var label = document.createElement("span");
      label.className = "auth-nav-name";
      label.textContent = me.name || "Signed in";
      label.title = me.phone || "";
      var out = document.createElement("button");
      out.type = "button";
      out.className = "auth-nav-out";
      out.textContent = "Log out";
      out.addEventListener("click", function () {
        out.disabled = true;
        fetch("/api/auth/logout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: "{}",
        }).finally(function () { window.location.reload(); });
      });
      chip.appendChild(label);
      chip.appendChild(out);
      link.replaceWith(chip);
    })
    .catch(function () { /* stay on "Log in" */ });
})();
