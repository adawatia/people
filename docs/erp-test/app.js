/* ERP CRUD Test Console — core logic. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const CONFIG_KEY = "erpTest.config";
  const SECRET_KEY = "erpTest.secrets";

  const state = {
    config: {
      baseUrl: "http://localhost:8000",
      authMode: "hmac",
      clientId: "",
      clientSecret: "",
      apiKey: "",
      rememberSecret: false,
      loginPath: "/api/v1/auth/employee/login",
      loginUsername: "",
    },
    selected: null,
    pathValue: "",
    params: {},
    query: {},
    form: { values: {}, rows: [] },
    token: null,
    lookups: {},
    history: [],
  };

  /* ── Helpers ───────────────────────────────────────────────────────────── */

  const pretty = (value) => (typeof value === "string" ? value : JSON.stringify(value, null, 2));

  function baseUrl() {
    return state.config.baseUrl.replace(/\/+$/, "");
  }

  function statusClass(status) {
    if (status >= 200 && status < 300) return "ok";
    if (status >= 400) return "err";
    return "";
  }

  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      el.hidden = true;
    }, 1800);
  }

  function setStatus(el, message, kind) {
    el.textContent = message || "";
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
  }

  function randomHex(bytes) {
    const buffer = new Uint8Array(bytes);
    crypto.getRandomValues(buffer);
    return Array.from(buffer, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function sha256Hex(text) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function hmacHex(secret, message) {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
    return Array.from(new Uint8Array(signature), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  /* ── Config persistence ────────────────────────────────────────────────── */

  function loadConfig() {
    try {
      const saved = JSON.parse(localStorage.getItem(CONFIG_KEY) || "{}");
      Object.assign(state.config, saved);
    } catch (_) {
      /* ignore malformed storage */
    }
    try {
      const secrets = JSON.parse(localStorage.getItem(SECRET_KEY) || sessionStorage.getItem(SECRET_KEY) || "{}");
      if (state.config.rememberSecret) {
        state.config.clientSecret = secrets.clientSecret || "";
        state.config.apiKey = secrets.apiKey || "";
      }
    } catch (_) {
      /* ignore */
    }
  }

  function saveConfig() {
    const { baseUrl: url, authMode, clientId, rememberSecret, loginPath, loginUsername } = state.config;
    localStorage.setItem(
      CONFIG_KEY,
      JSON.stringify({ baseUrl: url, authMode, clientId, rememberSecret, loginPath, loginUsername }),
    );
    if (rememberSecret) {
      localStorage.setItem(
        SECRET_KEY,
        JSON.stringify({ clientSecret: state.config.clientSecret, apiKey: state.config.apiKey }),
      );
    } else {
      localStorage.removeItem(SECRET_KEY);
      sessionStorage.removeItem(SECRET_KEY);
    }
  }

  /* ── Catalog ───────────────────────────────────────────────────────────── */

  function renderCatalog() {
    const container = $("catalog");
    container.innerHTML = "";
    const groups = [];
    ENDPOINTS.forEach((ep) => {
      let group = groups.find((g) => g.name === ep.group);
      if (!group) {
        group = { name: ep.group, items: [] };
        groups.push(group);
      }
      group.items.push(ep);
    });

    groups.forEach((group) => {
      const wrap = document.createElement("div");
      wrap.className = "catalog-group";
      const heading = document.createElement("h3");
      heading.textContent = group.name;
      wrap.appendChild(heading);
      group.items.forEach((ep) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "catalog-item";
        button.dataset.id = ep.id;
        button.innerHTML = `<span class="verb verb-${ep.method}">${ep.method}</span><span>${ep.label}</span>`;
        button.addEventListener("click", () => selectEndpoint(ep));
        wrap.appendChild(button);
      });
      container.appendChild(wrap);
    });
  }

  function highlightCatalog() {
    document.querySelectorAll(".catalog-item").forEach((item) => {
      item.classList.toggle("active", !!state.selected && item.dataset.id === state.selected.id);
    });
  }

  /* ── Request editor ────────────────────────────────────────────────────── */

  function buildPath(ep) {
    return ep.path.replace(/\{(\w+)\}/g, (_, name) => encodeURIComponent(state.params[name] ?? ""));
  }

  function selectEndpoint(ep, snapshot) {
    state.selected = ep;
    state.params = {};
    (ep.pathParams || []).forEach((param) => {
      state.params[param.name] = param.sample || "";
    });
    state.query = {};
    (ep.queryParams || []).forEach((q) => {
      state.query[q.name] = q.value || "";
    });
    state.pathValue = buildPath(ep);

    if (snapshot) {
      Object.assign(state.params, snapshot.params || {});
      Object.assign(state.query, snapshot.query || {});
      state.pathValue = snapshot.pathValue || buildPath(ep);
    }

    state.form = snapshot && snapshot.form ? snapshot.form : ErpForm.initState(ep);
    renderRequest();
    highlightCatalog();
  }

  function renderRequest() {
    const ep = state.selected;
    const methodEl = $("reqMethod");
    const sendEl = $("sendBtn");
    if (!ep) {
      methodEl.textContent = "—";
      $("reqScope").textContent = "—";
      $("reqHint").textContent = "Pick an endpoint from the catalog to begin.";
      $("pathParamsWrap").innerHTML = "";
      $("queryParamsWrap").innerHTML = "";
      $("bodyWrap").hidden = true;
      sendEl.disabled = true;
      return;
    }

    methodEl.textContent = ep.method;
    methodEl.className = "method";
    $("reqScope").textContent = ep.scope;
    $("reqScope").className = `badge badge-${ep.method === "DELETE" ? "err" : "ok"}`;
    $("reqHint").textContent = ep.notes || `${ep.group} · requires scope "${ep.scope}"`;
    $("reqPath").value = state.pathValue;
    sendEl.disabled = false;

    renderParams($("pathParamsWrap"), ep.pathParams || [], "params");
    renderParams($("queryParamsWrap"), ep.queryParams || [], "query");
    const hasBody = !!ep.body && ep.body.shape !== "none";
    $("bodyWrap").hidden = !hasBody;
    if (hasBody) renderBody();
    renderPayloadPreview();
  }

  function renderBody() {
    ErpForm.render($("bodyForm"), state.selected, state.form, renderPayloadPreview, state.lookups);
  }

  function renderPayloadPreview() {
    const ep = state.selected;
    const pre = $("payloadPreview");
    if (!ep || !ep.body || ep.body.shape === "none") {
      pre.textContent = "(no body)";
      return;
    }
    const payload = ErpForm.build(ep, state.form);
    pre.textContent = payload === undefined ? "{}" : pretty(payload);
  }

  function renderParams(container, params, target) {
    container.innerHTML = "";
    if (!params.length) return;

    params.forEach((param) => {
      const cell = document.createElement("div");
      cell.className = "param";
      const label = document.createElement("label");
      label.textContent = param.name;
      cell.appendChild(label);

      const options = target === "params" && param.lookup ? state.lookups[param.lookup] : null;
      if (options && options.length) {
        const select = document.createElement("select");
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = `— select ${param.lookup} —`;
        select.appendChild(blank);
        options.forEach((opt) => {
          const option = document.createElement("option");
          option.value = String(opt.value);
          option.textContent = opt.label;
          select.appendChild(option);
        });
        select.value = String(state.params[param.name] ?? "");
        select.addEventListener("change", () => {
          state.params[param.name] = select.value;
          state.pathValue = buildPath(state.selected);
          $("reqPath").value = state.pathValue;
        });
        cell.appendChild(select);
      } else {
        const input = document.createElement("input");
        input.type = "text";
        input.value = target === "params" ? state.params[param.name] ?? "" : state.query[param.name] ?? "";
        if (target === "params" && param.lookup) input.placeholder = "sign in + load reference data for a dropdown";
        input.addEventListener("input", () => {
          if (target === "params") {
            state.params[param.name] = input.value;
            state.pathValue = buildPath(state.selected);
            $("reqPath").value = state.pathValue;
          } else {
            state.query[param.name] = input.value;
          }
        });
        cell.appendChild(input);
        if (target === "params" && param.lookup && !options) {
          const note = document.createElement("div");
          note.className = "param-note";
          note.textContent = "loaded from reference data";
          cell.appendChild(note);
        }
      }
      container.appendChild(cell);
    });
  }

  function queryString() {
    const qs = new URLSearchParams();
    Object.entries(state.query).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) qs.append(key, value);
    });
    const text = qs.toString();
    return text ? `?${text}` : "";
  }

  /* ── Auth headers ──────────────────────────────────────────────────────── */

  async function erpHeaders(method, url, bodyText) {
    const headers = { Accept: "application/json" };
    if (bodyText !== undefined && bodyText !== null) headers["Content-Type"] = "application/json";

    if (state.config.authMode === "key") {
      if (!state.config.apiKey) throw new Error("Set the development API key (ERP_API_KEY) or switch to HMAC mode.");
      headers["X-API-Key"] = state.config.apiKey;
      return headers;
    }

    if (!crypto.subtle) {
      throw new Error("Web Crypto is unavailable. Open the page over http://localhost (not file://).");
    }
    if (!state.config.clientId || !state.config.clientSecret) {
      throw new Error("Set the ERP client ID and secret, or switch to dev API key mode.");
    }
    if (state.config.clientSecret.length < 32) {
      throw new Error("ERP client secrets must be at least 32 characters (matches API validation).");
    }

    const parsed = new URL(url);
    const target = parsed.pathname + parsed.search;
    const timestamp = String(Math.floor(Date.now() / 1000));
    const nonce = randomHex(16);
    const bodyHash = await sha256Hex(bodyText || "");
    const canonical = `${method.toUpperCase()}\n${target}\n${timestamp}\n${nonce}\n${bodyHash}`;
    headers["X-ERP-Client-ID"] = state.config.clientId;
    headers["X-ERP-Timestamp"] = timestamp;
    headers["X-ERP-Nonce"] = nonce;
    headers["X-ERP-Signature"] = await hmacHex(state.config.clientSecret, canonical);
    return headers;
  }

  /* ── Fetch wrapper ─────────────────────────────────────────────────────── */

  async function rawFetch(url, options) {
    const started = performance.now();
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      return { networkError: String(error && error.message ? error.message : error), ms: performance.now() - started, url };
    }
    const text = await response.text();
    let data = text;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (_) {
        /* keep raw text */
      }
    } else {
      data = null;
    }
    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      data,
      ms: performance.now() - started,
      requestId: response.headers.get("x-request-id"),
      contentType: response.headers.get("content-type"),
      url,
    };
  }

  function renderResponse(result) {
    const badge = $("respStatus");
    const meta = $("respMeta");
    const body = $("respBody");

    if (result.networkError) {
      badge.textContent = "network error";
      badge.className = "badge err";
      meta.textContent =
        "Request did not reach the API. Check the base URL, that the API is running, and that you opened this page on http://localhost (CORS).";
      body.textContent = result.networkError;
      return;
    }

    const kind = statusClass(result.status);
    badge.textContent = `${result.status} ${result.statusText || ""}`.trim();
    badge.className = `badge ${kind}`;
    const bits = [`${result.ms.toFixed(0)} ms`];
    if (result.requestId) bits.push(`request-id ${result.requestId}`);
    meta.textContent = bits.join(" · ");
    body.textContent = result.data === null ? "(empty response body)" : pretty(result.data);
  }

  /* ── Send ──────────────────────────────────────────────────────────────── */

  async function sendRequest() {
    const ep = state.selected;
    if (!ep) return;
    const sendBtn = $("sendBtn");
    sendBtn.disabled = true;
    setStatus($("sendStatus"), "Sending…");

    const url = baseUrl() + state.pathValue + queryString();
    const hasBody = !!ep.body && ep.body.shape !== "none";
    let bodyText;
    if (hasBody) {
      const errors = ErpForm.validate(ep, state.form);
      if (errors.length) {
        setStatus($("sendStatus"), errors.join("; "), "err");
        sendBtn.disabled = false;
        return;
      }
      const payload = ErpForm.build(ep, state.form);
      if (payload !== undefined) bodyText = JSON.stringify(payload);
    }

    try {
      const headers = await erpHeaders(ep.method, url, bodyText);
      const options = { method: ep.method, headers };
      if (hasBody && bodyText) options.body = bodyText;
      const result = await rawFetch(url, options);
      renderResponse(result);
      addHistory(ep, result);
      if (result.networkError) {
        setStatus($("sendStatus"), result.networkError, "err");
      } else if (result.ok) {
        setStatus($("sendStatus"), `${result.status} OK`, "ok");
      } else {
        const detail = result.data && result.data.detail ? JSON.stringify(result.data.detail) : "see response";
        setStatus($("sendStatus"), `${result.status} — ${detail}`, "err");
      }
    } catch (error) {
      setStatus($("sendStatus"), error.message, "err");
      renderResponse({ networkError: error.message });
    } finally {
      sendBtn.disabled = false;
    }
  }

  /* ── History ───────────────────────────────────────────────────────────── */

  function addHistory(ep, result) {
    state.history.unshift({
      id: ep.id,
      label: ep.label,
      method: ep.method,
      path: state.pathValue,
      status: result.networkError ? "ERR" : result.status,
      ms: result.ms,
      snapshot: {
        params: { ...state.params },
        query: { ...state.query },
        pathValue: state.pathValue,
        form: JSON.parse(JSON.stringify(state.form)),
      },
    });
    state.history = state.history.slice(0, 30);
    renderHistory();
  }

  function renderHistory() {
    const container = $("historyList");
    container.innerHTML = "";
    if (!state.history.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No requests sent yet.";
      container.appendChild(empty);
      return;
    }
    state.history.forEach((entry, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "history-item";
      const ok = typeof entry.status === "number" && entry.status >= 200 && entry.status < 300;
      button.innerHTML =
        `<span class="verb verb-${entry.method}">${entry.method}</span>` +
        `<span class="hist-path">${entry.path}</span>` +
        `<span class="badge ${ok ? "ok" : "err"}">${entry.status}</span>`;
      button.addEventListener("click", () => {
        const ep = ENDPOINTS.find((item) => item.id === entry.id);
        if (!ep) return;
        selectEndpoint(ep, entry.snapshot);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
      container.appendChild(button);
      void index;
    });
  }

  /* ── Lookup login + reference data ─────────────────────────────────────── */

  function renderLoginOptions() {
    const select = $("loginPath");
    select.innerHTML = "";
    LOGIN_ENDPOINTS.forEach((option) => {
      const item = document.createElement("option");
      item.value = option.path;
      item.textContent = option.label;
      select.appendChild(item);
    });
    const known = LOGIN_ENDPOINTS.some((option) => option.path === state.config.loginPath);
    if (!known) state.config.loginPath = LOGIN_ENDPOINTS[0].path;
    select.value = state.config.loginPath;
  }

  async function login() {
    const path = $("loginPath").value;
    const username = $("loginUsername").value.trim();
    const password = $("loginPassword").value;
    if (!username || !password) {
      setStatus($("loginStatus"), "Enter a username and password.", "err");
      return;
    }
    setStatus($("loginStatus"), "Signing in…");
    const url = baseUrl() + path;
    const result = await rawFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ username, password }).toString(),
    });

    if (result.networkError) {
      setStatus($("loginStatus"), result.networkError, "err");
      return;
    }
    const data = result.data || {};
    if (data.access_token) {
      state.token = data.access_token;
      state.config.loginUsername = username;
      saveConfig();
      $("loadRefsBtn").disabled = false;
      $("pwChangeWrap").hidden = !data.must_change_password;
      if (data.must_change_password) {
        $("loadRefsBtn").disabled = true;
        setStatus(
          $("loginStatus"),
          `Signed in as ${username}, but this account must change its temporary password before workforce data can be read.`,
          "err",
        );
        return;
      }
      if (path.includes("super-admin")) {
        setStatus(
          $("loginStatus"),
          `Signed in as ${username}, but a technical Super Admin cannot read workforce data — lookups will return 403. Use a business user instead.`,
          "err",
        );
        return;
      }
      setStatus($("loginStatus"), `Signed in as ${username}.`, "ok");
    } else if (data.mfa_required) {
      state.token = null;
      $("loadRefsBtn").disabled = true;
      setStatus($("loginStatus"), "MFA is required for this account; this test tool cannot complete the challenge.", "err");
    } else {
      state.token = null;
      $("loadRefsBtn").disabled = true;
      const detail = data.detail ? JSON.stringify(data.detail) : `HTTP ${result.status}`;
      setStatus($("loginStatus"), `Sign-in failed: ${detail}`, "err");
    }
  }

  async function changePasswordAndRelogin() {
    if (!state.token) {
      setStatus($("loginStatus"), "Sign in first.", "err");
      return;
    }
    const newPassword = $("newPassword").value;
    if (!newPassword) {
      setStatus($("loginStatus"), "Enter a new password.", "err");
      return;
    }
    setStatus($("loginStatus"), "Changing password…");
    const result = await rawFetch(baseUrl() + "/api/v1/auth/change-password", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ current_password: $("loginPassword").value, new_password: newPassword }),
    });
    if (result.networkError || !result.ok) {
      const detail = result.networkError || JSON.stringify(result.data && result.data.detail);
      setStatus($("loginStatus"), `Password change failed: ${detail}`, "err");
      return;
    }
    // Every session was revoked by the change, so sign in again with the new password.
    $("loginPassword").value = newPassword;
    $("newPassword").value = "";
    setStatus($("loginStatus"), "Password changed. Signing in again…", "ok");
    await login();
  }

  async function loadReferenceData() {
    if (!state.token) {
      setStatus($("loginStatus"), "Sign in first.", "err");
      return;
    }
    const button = $("loadRefsBtn");
    button.disabled = true;
    const entries = Object.entries(LOOKUP_SOURCES);
    let loaded = 0;
    const failures = [];

    for (const [key, source] of entries) {
      setStatus($("loginStatus"), `Loading reference data… (${loaded + 1}/${entries.length}) ${source.label}`);
      const result = await rawFetch(baseUrl() + source.path, {
        headers: { Accept: "application/json", Authorization: `Bearer ${state.token}` },
      });
      if (result.networkError || !result.ok) {
        const reason = result.networkError || `HTTP ${result.status}`;
        failures.push(`${source.label}: ${reason}`);
        continue;
      }
      state.lookups[key] = extractOptions(source, result.data);
      loaded += 1;
    }

    renderRequest();
    renderRefIds();
    button.disabled = false;
    if (failures.length) {
      const allForbidden = loaded === 0 && failures.every((line) => line.includes("403"));
      const suffix = allForbidden
        ? " Hint: a technical Super Admin cannot read workforce data. Sign in as a business user (for example an ORGANIZATION_OWNER) instead."
        : "";
      setStatus($("loginStatus"), `Loaded ${loaded} lists. Failed → ${failures.join("; ")}.${suffix}`, "err");
    } else {
      setStatus($("loginStatus"), `Loaded ${loaded} reference lists and populated dropdowns.`, "ok");
    }
  }

  function renderRefIds() {
    const container = $("refIds");
    container.innerHTML = "";
    const keys = Object.keys(state.lookups).filter((key) => state.lookups[key].length);
    if (!keys.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No reference data loaded.";
      container.appendChild(empty);
      return;
    }
    keys.forEach((key) => {
      const source = LOOKUP_SOURCES[key];
      const group = document.createElement("div");
      group.className = "ref-group";
      const heading = document.createElement("h3");
      heading.textContent = `${source ? source.label : key} (${state.lookups[key].length})`;
      group.appendChild(heading);
      state.lookups[key].forEach((option) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "ref-chip";
        chip.textContent = `${option.value} · ${option.label}`;
        chip.title = "Click to copy the ID";
        chip.addEventListener("click", () => {
          navigator.clipboard.writeText(String(option.value)).then(
            () => toast(`Copied ${option.value}`),
            () => toast(`ID ${option.value}`),
          );
        });
        group.appendChild(chip);
      });
      container.appendChild(group);
    });
  }

  /* ── Wiring ────────────────────────────────────────────────────────────── */

  function syncAuthVisibility() {
    const mode = $("authMode").value;
    $("hmacFields").hidden = mode !== "hmac";
    $("keyFields").hidden = mode !== "key";
    $("authHint").textContent =
      mode === "hmac"
        ? "Requests are signed with HMAC-SHA256 in the browser. Requires a secure context, so serve this page on http://localhost."
        : "Development-only compatibility key. Only accepted when the API runs with ENVIRONMENT=development and ERP_API_KEY is set.";
  }

  function bindEvents() {
    $("baseUrl").addEventListener("input", (e) => {
      state.config.baseUrl = e.target.value;
      saveConfig();
    });
    $("authMode").addEventListener("change", (e) => {
      state.config.authMode = e.target.value;
      syncAuthVisibility();
      saveConfig();
    });
    $("clientId").addEventListener("input", (e) => {
      state.config.clientId = e.target.value;
      saveConfig();
    });
    $("clientSecret").addEventListener("input", (e) => {
      state.config.clientSecret = e.target.value;
      saveConfig();
    });
    $("apiKey").addEventListener("input", (e) => {
      state.config.apiKey = e.target.value;
      saveConfig();
    });
    $("rememberSecret").addEventListener("change", (e) => {
      state.config.rememberSecret = e.target.checked;
      saveConfig();
    });
    $("loginPath").addEventListener("change", (e) => {
      state.config.loginPath = e.target.value;
      saveConfig();
    });
    $("loginUsername").addEventListener("input", (e) => {
      state.config.loginUsername = e.target.value;
      saveConfig();
    });
    $("loginBtn").addEventListener("click", login);
    $("pwChangeBtn").addEventListener("click", changePasswordAndRelogin);
    $("loadRefsBtn").addEventListener("click", loadReferenceData);
    $("sendBtn").addEventListener("click", sendRequest);
    $("reqPath").addEventListener("input", (e) => {
      state.pathValue = e.target.value;
    });
    $("clearHistoryBtn").addEventListener("click", () => {
      state.history = [];
      renderHistory();
    });
  }

  function hydrateConfigInputs() {
    $("baseUrl").value = state.config.baseUrl;
    $("authMode").value = state.config.authMode;
    $("clientId").value = state.config.clientId;
    $("clientSecret").value = state.config.clientSecret;
    $("apiKey").value = state.config.apiKey;
    $("rememberSecret").checked = state.config.rememberSecret;
    $("loginUsername").value = state.config.loginUsername;
  }

  function init() {
    loadConfig();
    hydrateConfigInputs();
    renderLoginOptions();
    syncAuthVisibility();
    renderCatalog();
    renderHistory();
    renderRefIds();
    renderRequest();
    bindEvents();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
