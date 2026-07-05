import {
  DEFAULT_SETTINGS,
  endpointFromSettings,
  healthEndpointFromSettings,
  normalizeSettings,
  normalizePort
} from "./event_builder.mjs";

function byId(id) {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing_${id}`);
  return element;
}

async function load() {
  const settings = normalizeSettings(
    await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS))
  );
  byId("enabled").checked = settings.enabled !== false;
  byId("sendTitle").checked = settings.sendTitle === true;
  byId("trackBgAudio").checked = settings.trackBackgroundAudio !== false;
  byId("keepAlive").checked = settings.keepAlive !== false;
  byId("port").value = String(normalizePort(settings.port));
  renderEndpoint();

  const { status } = await chrome.storage.local.get("status");
  renderStatus(status);
}

function settingsFromForm() {
  return {
    enabled: byId("enabled").checked,
    sendTitle: byId("sendTitle").checked,
    trackBackgroundAudio: byId("trackBgAudio").checked,
    keepAlive: byId("keepAlive").checked,
    port: normalizePort(byId("port").value),
    settingsSchemaVersion: DEFAULT_SETTINGS.settingsSchemaVersion
  };
}

function renderEndpoint() {
  byId("endpointText").textContent = endpointFromSettings(settingsFromForm());
}

function renderStatus(status) {
  const line = byId("statusLine");
  const diag = byId("diagLine");

  if (!status) {
    line.textContent = "(no data yet)";
    diag.textContent = "";
    return;
  }

  const lastOk = typeof status.lastOkTs === "string" ? status.lastOkTs : "";
  const lastAttempt =
    typeof status.lastAttemptTs === "string" ? status.lastAttemptTs : "";
  const consecutiveErrors =
    typeof status.consecutiveErrors === "number" && Number.isFinite(status.consecutiveErrors)
      ? status.consecutiveErrors
      : 0;

  if (status.ok) {
    const last = status.lastSent || {};
    const parts = [];
    if (last.kind) parts.push(`kind=${last.kind}`);
    if (last.payload?.activity) parts.push(`activity=${last.payload.activity}`);
    if (last.entity) parts.push(`domain=${last.entity}`);
    if (last.title) parts.push(`title=${trim(last.title)}`);
    if (lastOk) parts.push(`last_ok=${lastOk}`);
    if (consecutiveErrors > 0) parts.push(`errors=${consecutiveErrors}`);
    line.textContent = `${status.ts} | sent | ${parts.length ? parts.join("  ") : "ok"}`;
  } else {
    const parts = [status.error || status.lastError || "unknown"];
    if (consecutiveErrors > 0) parts.push(`errors=${consecutiveErrors}`);
    if (lastAttempt) parts.push(`last_try=${lastAttempt}`);
    if (lastOk) parts.push(`last_ok=${lastOk}`);
    line.textContent = `${status.ts} | error | ${parts.join("  ")}`;
  }

  const offscreen = status.offscreen || {};
  if (typeof offscreen.supported === "boolean") {
    if (!offscreen.supported) {
      diag.textContent = "offscreen=unsupported";
      return;
    }
    const desired = offscreen.desired === true ? "on" : "off";
    const active = offscreen.hasDocument === true ? "active" : "inactive";
    diag.textContent = `offscreen=${desired}/${active}`;
    return;
  }
  diag.textContent = "";
}

function trim(value) {
  const text = String(value).trim();
  return text.length > 48 ? `${text.slice(0, 45)}...` : text;
}

async function save() {
  const settings = settingsFromForm();
  byId("port").value = String(settings.port);
  renderEndpoint();
  await chrome.storage.local.set(settings);
}

async function testHealth() {
  const result = byId("healthResult");
  result.textContent = "...";
  try {
    const response = await fetch(healthEndpointFromSettings(settingsFromForm()));
    if (!response.ok) {
      result.textContent = `HTTP ${response.status}`;
      return;
    }
    const body = await response.json().catch(() => ({}));
    result.textContent = body?.service === "localtrace" || body?.ok === true ? "OK" : "OK";
  } catch {
    result.textContent = "ERR";
  }
}

for (const id of ["enabled", "sendTitle", "trackBgAudio", "keepAlive", "port"]) {
  byId(id).addEventListener("change", save);
}

byId("testHealth").addEventListener("click", testHealth);

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes.status) {
    renderStatus(changes.status.newValue);
  }
});

load();
