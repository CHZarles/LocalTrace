const state = {
  settings: null,
  rules: [],
  tracking: { paused: false }
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  const body = await response.json();
  if (!response.ok || body.ok === false) {
    throw new Error(body.error || `HTTP ${response.status}`);
  }
  return body;
}

async function loadAll() {
  setBusy(true);
  try {
    const [health, settings, privacy, tracking] = await Promise.all([
      api("/health"),
      api("/settings"),
      api("/privacy/rules"),
      api("/tracking/status")
    ]);
    state.settings = settings.settings;
    state.rules = privacy.rules;
    state.tracking = tracking;
    renderHealth(health);
    renderSettings(settings.settings);
    renderRules(privacy.rules);
    renderTracking(tracking);
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function renderHealth(health) {
  const source = health.sources || {};
  const metrics = [
    ["Service", health.service || "unknown"],
    ["Bind", `${health.bind?.host || "127.0.0.1"}:${health.bind?.port || ""}`],
    ["Database", health.database?.exists ? "exists" : "missing"],
    ["DB path", health.database?.path || ""],
    ["Recent events", String(health.events?.recent_count ?? 0)],
    ["Tracking", health.tracking?.paused ? "paused" : "active"],
    ["Windows probe", source.windows_probe?.last_observed_at || "unknown"],
    ["Browser extension", source.browser_extension?.last_observed_at || "unknown"]
  ];
  $("healthMetrics").replaceChildren(
    ...metrics.map(([label, value]) => {
      const item = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = value;
      item.append(dt, dd);
      return item;
    })
  );
}

function renderSettings(settings) {
  $("apiPort").value = settings.api.port;
  $("pollMs").value = settings.capture.poll_ms;
  $("heartbeatSeconds").value = settings.capture.heartbeat_seconds;
  $("idleCutoffSeconds").value = settings.capture.idle_cutoff_seconds;
  $("storeTitles").checked = settings.capture.store_titles;
  $("storeExePath").checked = settings.capture.store_exe_path;
  $("trackBrowser").checked = settings.capture.track_browser;
  $("trackAudio").checked = settings.capture.track_audio;
  $("defaultTitleStorage").checked = settings.privacy.default_title_storage;
}

function renderRules(rules) {
  const rows = rules.map((rule) => {
    const tr = document.createElement("tr");
    tr.append(
      cell(String(rule.id)),
      cell(rule.entity_type),
      cell(rule.pattern),
      cell(rule.action),
      actionCell(rule.id)
    );
    return tr;
  });
  $("rulesTable").replaceChildren(...rows);
}

function renderTracking(tracking) {
  $("pauseButton").disabled = tracking.paused;
  $("resumeButton").disabled = !tracking.paused;
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function actionCell(id) {
  const td = document.createElement("td");
  const button = document.createElement("button");
  button.className = "danger";
  button.type = "button";
  button.textContent = "Delete";
  button.addEventListener("click", () => deleteRule(id));
  td.append(button);
  return td;
}

function settingsFromForm() {
  return {
    api: {
      port: Number.parseInt($("apiPort").value, 10)
    },
    capture: {
      poll_ms: Number.parseInt($("pollMs").value, 10),
      heartbeat_seconds: Number.parseInt($("heartbeatSeconds").value, 10),
      idle_cutoff_seconds: Number.parseInt($("idleCutoffSeconds").value, 10),
      store_titles: $("storeTitles").checked,
      store_exe_path: $("storeExePath").checked,
      track_browser: $("trackBrowser").checked,
      track_audio: $("trackAudio").checked
    },
    privacy: {
      default_title_storage: $("defaultTitleStorage").checked
    }
  };
}

async function saveSettings() {
  setBusy(true);
  try {
    const body = await api("/settings", {
      method: "POST",
      body: JSON.stringify(settingsFromForm())
    });
    state.settings = body.settings;
    renderSettings(body.settings);
    setStatus("Saved");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function addRule() {
  const pattern = $("rulePattern").value.trim();
  if (!pattern) return;
  setBusy(true);
  try {
    await api("/privacy/rules", {
      method: "POST",
      body: JSON.stringify({
        entity_type: $("ruleEntityType").value,
        pattern,
        action: $("ruleAction").value
      })
    });
    $("rulePattern").value = "";
    await loadAll();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function deleteRule(id) {
  setBusy(true);
  try {
    await api(`/privacy/rules/${id}`, { method: "DELETE" });
    await loadAll();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function setTracking(path) {
  setBusy(true);
  try {
    const tracking = await api(path, { method: "POST" });
    state.tracking = tracking;
    renderTracking(tracking);
    await loadAll();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function setStatus(text) {
  $("statusLine").textContent = text;
}

function setBusy(busy) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = busy;
  }
  if (!busy) renderTracking(state.tracking);
}

$("refreshButton").addEventListener("click", loadAll);
$("saveSettings").addEventListener("click", saveSettings);
$("addRule").addEventListener("click", addRule);
$("pauseButton").addEventListener("click", () => setTracking("/tracking/pause"));
$("resumeButton").addEventListener("click", () => setTracking("/tracking/resume"));

loadAll();
