/* Resume IQ shared client library: API calls, CSRF, auth redirects, form helpers, nav menu. */
(function (global) {
  "use strict";

  var RIQ = {};
  var csrfToken = null;

  /* ---------- errors ---------- */
  function ApiError(status, code, message, fields) {
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.message = message;
    this.fields = fields || {};
  }
  ApiError.prototype = Object.create(Error.prototype);
  RIQ.ApiError = ApiError;

  /* ---------- CSRF ---------- */
  function loadCsrf(force) {
    if (csrfToken && !force) return Promise.resolve(csrfToken);
    return fetch("/api/csrf", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { csrfToken = d.csrf_token; return csrfToken; });
  }

  /* ---------- API ---------- */
  /**
   * RIQ.api(path, {method, json, form, redirectOn401})
   * Resolves with parsed JSON; rejects with RIQ.ApiError.
   */
  RIQ.api = function (path, opts, _retried) {
    opts = opts || {};
    var method = (opts.method || "GET").toUpperCase();
    var unsafe = method !== "GET" && method !== "HEAD";
    var prep = unsafe ? loadCsrf() : Promise.resolve();

    return prep.then(function () {
      var headers = { Accept: "application/json" };
      var body;
      if (unsafe) headers["X-CSRFToken"] = csrfToken;
      if (opts.json !== undefined) {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(opts.json);
      } else if (opts.form) {
        body = opts.form; // FormData: browser sets the multipart boundary
      }
      return fetch(path, { method: method, headers: headers, body: body, credentials: "same-origin", signal: opts.signal })
        .catch(function (err) {
          if (err && err.name === "AbortError") throw err;
          throw new ApiError(0, "network", "Cannot reach the server. Check your connection and try again.");
        });
    }).then(function (res) {
      return res.text().then(function (txt) {
        var data = {};
        try { data = txt ? JSON.parse(txt) : {}; } catch (e) { data = {}; }
        if (data && data.csrf_token) csrfToken = data.csrf_token;
        if (res.ok) return data;

        var e = (data && data.error) || {};
        var err = new ApiError(res.status, e.code || "http_" + res.status,
          e.message || "Something went wrong (" + res.status + ").", e.fields);
        if (err.code === "csrf_failed" && !_retried) {
          return loadCsrf(true).then(function () { return RIQ.api(path, opts, true); });
        }
        if (res.status === 401 && opts.redirectOn401 !== false) RIQ.sessionExpired();
        throw err;
      });
    });
  };

  /* ---------- session ---------- */
  function safeNext(value) {
    return /^\/[a-z0-9-]+\.html$/.test(value || "") ? value : "";
  }
  RIQ.safeNext = safeNext;

  RIQ.sessionExpired = function () {
    var here = location.pathname;
    if (/\/(login|create-account|register)\.html$/.test(here)) return;
    var target = "login.html?expired=1" + (safeNext(here) ? "&next=" + encodeURIComponent(here) : "");
    location.href = target;
  };

  /** Resolves with the signed-in user, or redirects to login. */
  RIQ.requireUser = function () {
    return RIQ.api("/api/auth/me").then(function (d) { RIQ.user = d.user; return d.user; });
  };

  RIQ.logout = function () {
    return RIQ.api("/api/auth/logout", { method: "POST", redirectOn401: false })
      .catch(function () {})
      .then(function () { location.href = "login.html"; });
  };

  /* ---------- small helpers ---------- */
  RIQ.escapeHTML = function (v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  RIQ.formatBytes = function (bytes) {
    if (!bytes) return "0 B";
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)) + " " + units[i];
  };

  RIQ.formatDate = function (iso) {
    if (!iso) return "";
    var d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  };

  RIQ.goBack = function (fallback) {
    var sameOrigin = document.referrer && document.referrer.indexOf(location.origin) === 0;
    if (sameOrigin && history.length > 1) history.back();
    else location.href = fallback || "homepage.html";
  };

  RIQ.setBusy = function (btn, busy, busyLabel) {
    if (!btn) return;
    if (busy) {
      btn.dataset.label = btn.innerHTML;
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      if (busyLabel) btn.textContent = busyLabel;
    } else {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      if (btn.dataset.label !== undefined) btn.innerHTML = btn.dataset.label;
    }
  };

  /* ---------- form feedback ---------- */
  RIQ.clearErrors = function (root) {
    (root || document).querySelectorAll(".riq-field-error").forEach(function (n) { n.remove(); });
    (root || document).querySelectorAll("[aria-invalid]").forEach(function (n) { n.removeAttribute("aria-invalid"); });
  };

  RIQ.fieldError = function (input, message) {
    if (!input || !message) return;
    input.setAttribute("aria-invalid", "true");
    var host = input.closest(".input-box, .form-group") || input.parentElement;
    var el = document.createElement("div");
    el.className = "riq-field-error";
    el.setAttribute("role", "alert");
    el.textContent = message;
    host.appendChild(el);
  };

  /** Show server-side `fields` errors next to inputs; returns messages that had no input. */
  RIQ.showFieldErrors = function (fields, inputsByName) {
    var orphans = [];
    Object.keys(fields || {}).forEach(function (name) {
      if (!fields[name]) return;
      var input = inputsByName[name];
      if (input) RIQ.fieldError(input, fields[name]); else orphans.push(fields[name]);
    });
    return orphans;
  };

  /** Banner message inside a container element (id given). kind: "error" | "success" | "info". */
  RIQ.banner = function (el, message, kind) {
    if (typeof el === "string") el = document.getElementById(el);
    if (!el) return;
    el.className = "riq-banner riq-banner-" + (kind || "error");
    el.textContent = message;
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.style.display = message ? "block" : "none";
  };

  /* ---------- nav menu (hamburger + dropdown) ---------- */
  RIQ.initMenu = function () {
    var button = document.getElementById("menuButton");
    var dropdown = document.getElementById("dropdown");
    if (!button || !dropdown) return;

    function setOpen(open) {
      dropdown.style.display = open ? "block" : "none";
      button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    button.setAttribute("aria-haspopup", "true");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(dropdown.style.display !== "block");
    });
    document.addEventListener("click", function (e) {
      if (!dropdown.contains(e.target) && e.target !== button) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { setOpen(false); button.focus(); }
    });

    var profile = document.getElementById("profileButton");
    if (profile) profile.addEventListener("click", function () { location.href = "profile.html"; });
    var logout = document.getElementById("logoutButton");
    if (logout) logout.addEventListener("click", function () {
      if (confirm("Are you sure you want to logout?")) RIQ.logout();
    });
  };

  /* ---------- toast ---------- */
  RIQ.toast = function (message, kind) {
    var el = document.createElement("div");
    el.className = "riq-toast riq-toast-" + (kind || "info");
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  };

  global.RIQ = RIQ;
})(window);
