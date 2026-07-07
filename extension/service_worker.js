import {
  DEFAULT_SETTINGS,
  buildTabActiveEvent,
  buildTabAudioStopEvent,
  clearPendingSeq,
  endpointFromSettings,
  normalizeSettings,
  reserveSeq,
  safeHostname
} from "./event_builder.mjs";

const STATE = {
  seq: 0,
  pendingKey: null,
  pendingSeq: null,
  lastDomain: null,
  lastTabId: null,
  lastWindowId: null,
  lastActivity: null,
  lastSentAtMs: 0,
  lastFocusDomain: null,
  lastFocusTabId: null,
  lastFocusWindowId: null,
  lastFocusTitle: null,
  lastFocusSentAtMs: 0,
  lastAudioDomain: null,
  lastAudioTabId: null,
  lastAudioWindowId: null,
  lastAudioTitle: null,
  lastAudioSentAtMs: 0,
  lastAttemptAtMs: 0,
  lastOkAtMs: 0,
  consecutiveErrors: 0,
  lastError: null,
  lastErrorAtMs: 0
};

let stateLoaded = false;
let offscreenSyncing = null;
let bootstrapping = null;
let lastOffscreen = {
  supported: false,
  desired: false,
  hasDocument: false,
  checkedAtMs: 0,
  error: null
};

function nowIso() {
  return new Date().toISOString();
}

function msToIso(ms) {
  if (!ms || ms <= 0) return null;
  try {
    return new Date(ms).toISOString();
  } catch {
    return null;
  }
}

async function ensureStateLoaded() {
  if (stateLoaded) return;
  stateLoaded = true;
  try {
    const stored = await chrome.storage.local.get("localtraceExtensionState");
    const storedState = stored?.localtraceExtensionState;
    if (!storedState || typeof storedState !== "object") return;

    for (const key of Object.keys(STATE)) {
      if (storedState[key] !== undefined) {
        STATE[key] = storedState[key];
      }
    }
    migrateLegacyActivityState();
  } catch {
    // Keep defaults when storage is unavailable.
  }
}

function migrateLegacyActivityState() {
  if (!STATE.lastActivity || !STATE.lastDomain) return;
  if (STATE.lastActivity === "audio" && !STATE.lastAudioDomain) {
    STATE.lastAudioDomain = STATE.lastDomain;
    STATE.lastAudioTabId = STATE.lastTabId;
    STATE.lastAudioWindowId = STATE.lastWindowId;
    STATE.lastAudioTitle = null;
    STATE.lastAudioSentAtMs = STATE.lastSentAtMs;
  }
  if (STATE.lastActivity === "focus" && !STATE.lastFocusDomain) {
    STATE.lastFocusDomain = STATE.lastDomain;
    STATE.lastFocusTabId = STATE.lastTabId;
    STATE.lastFocusWindowId = STATE.lastWindowId;
    STATE.lastFocusTitle = null;
    STATE.lastFocusSentAtMs = STATE.lastSentAtMs;
  }
}

async function persistState() {
  try {
    await chrome.storage.local.set({
      localtraceExtensionState: { ...STATE }
    });
  } catch {
    // Status persistence is best effort only.
  }
}

async function getSettings() {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS));
  const settings = normalizeSettings(stored);
  const patch = {};
  for (const [key, value] of Object.entries(settings)) {
    if (stored[key] !== value) {
      patch[key] = value;
    }
  }
  if (Object.keys(patch).length > 0) {
    await chrome.storage.local.set(patch);
  }
  return settings;
}

async function ensureDefaultSettings() {
  await getSettings();
}

function detectBrowser() {
  const userAgent = self.navigator?.userAgent || "";
  if (userAgent.includes("Edg/")) return "edge";
  if (userAgent.includes("Firefox/")) return "firefox";
  if (userAgent.includes("Chrome/")) return "chrome";
  return "unknown";
}

function getLastFocusedWindow() {
  return new Promise((resolve) => {
    try {
      chrome.windows.getLastFocused({ populate: false }, (windowInfo) => {
        resolve(windowInfo ?? null);
      });
    } catch {
      resolve(null);
    }
  });
}

async function isBrowserFocused() {
  const windowInfo = await getLastFocusedWindow();
  return windowInfo == null ? true : Boolean(windowInfo.focused);
}

async function setStatus(partial) {
  const status = {
    ts: nowIso(),
    lastAttemptTs: msToIso(STATE.lastAttemptAtMs),
    lastOkTs: msToIso(STATE.lastOkAtMs),
    lastErrorTs: msToIso(STATE.lastErrorAtMs),
    consecutiveErrors: STATE.consecutiveErrors,
    lastError: STATE.lastError,
    offscreen: lastOffscreen,
    ...partial
  };

  try {
    await chrome.storage.local.set({ status });
  } catch {
    // Status is diagnostic only.
  }
}

async function checkOffscreen(settings) {
  const supported =
    !!chrome.offscreen && typeof chrome.offscreen.hasDocument === "function";
  const desired = settings.enabled !== false && settings.keepAlive !== false;
  let hasDocument = false;
  let error = null;

  if (supported) {
    try {
      hasDocument = await chrome.offscreen.hasDocument();
    } catch (caught) {
      error = String(caught);
      hasDocument = false;
    }
  }

  lastOffscreen = {
    supported,
    desired,
    hasDocument,
    checkedAtMs: Date.now(),
    error
  };
  return lastOffscreen;
}

async function syncOffscreenDocument(settings) {
  if (!chrome.offscreen || typeof chrome.offscreen.hasDocument !== "function") return;

  const desired = settings.enabled !== false && settings.keepAlive !== false;
  if (offscreenSyncing) return offscreenSyncing;

  offscreenSyncing = (async () => {
    let hasDocument = false;
    try {
      hasDocument = await chrome.offscreen.hasDocument();
    } catch {
      hasDocument = false;
    }

    lastOffscreen = {
      supported: true,
      desired,
      hasDocument,
      checkedAtMs: Date.now(),
      error: null
    };

    if (!desired) {
      if (!hasDocument) return;
      try {
        await chrome.offscreen.closeDocument();
      } catch {
        // Ignore browser-specific offscreen errors.
      }
      return;
    }

    if (hasDocument) return;

    try {
      const reason = chrome.offscreen?.Reason?.DOM_PARSER ?? "DOM_PARSER";
      await chrome.offscreen.createDocument({
        url: "offscreen.html",
        reasons: [reason],
        justification:
          "Keep the service worker responsive for reliable LocalTrace tab tracking."
      });
      lastOffscreen = {
        supported: true,
        desired,
        hasDocument: true,
        checkedAtMs: Date.now(),
        error: null
      };
    } catch (caught) {
      lastOffscreen = {
        supported: true,
        desired,
        hasDocument: false,
        checkedAtMs: Date.now(),
        error: String(caught)
      };
    }
  })().finally(() => {
    offscreenSyncing = null;
  });

  return offscreenSyncing;
}

async function postEvent(settings, event) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5500);
  try {
    const response = await fetch(endpointFromSettings(settings), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(event),
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(`http_${response.status}`);
    }
  } catch (caught) {
    if (caught && typeof caught === "object" && caught.name === "AbortError") {
      throw new Error("timeout");
    }
    throw caught;
  } finally {
    clearTimeout(timeout);
  }
}

async function ensureHeartbeatAlarm() {
  try {
    await chrome.alarms.create("heartbeat", { periodInMinutes: 1 });
  } catch {
    // Alarms are best effort.
  }
}

function titleForActivityState(tab, settings) {
  if (settings.sendTitle === false) return null;
  return typeof tab.title === "string" && tab.title.trim() ? tab.title : null;
}

function eventKey(activity, domain, tab, title) {
  return `${activity}:${domain}:${tab.windowId}:${tab.id}:${title || ""}`;
}

async function sendEvent(settings, event, updateState) {
  try {
    STATE.lastAttemptAtMs = Date.now();
    await postEvent(settings, event);
    const sentAtMs = Date.now();
    updateState(sentAtMs);
    STATE.lastSentAtMs = sentAtMs;
    STATE.lastOkAtMs = sentAtMs;
    STATE.consecutiveErrors = 0;
    STATE.lastError = null;
    STATE.lastErrorAtMs = 0;
    clearPendingSeq(STATE);
    await persistState();
    await setStatus({ ok: true, lastSent: event, error: null });
  } catch (caught) {
    STATE.consecutiveErrors += 1;
    STATE.lastError = String(caught);
    STATE.lastErrorAtMs = Date.now();
    await persistState();
    await setStatus({ ok: false, error: String(caught) });
  }
}

async function maybeEmitAudioStop(settings, reason) {
  await ensureStateLoaded();
  if (!STATE.lastAudioDomain) return;

  const key = `tab_audio_stop:${STATE.lastAudioDomain}:${STATE.lastAudioWindowId}:${STATE.lastAudioTabId}:${reason}`;
  const event = buildTabAudioStopEvent({
    observedAt: nowIso(),
    seq: reserveSeq(STATE, key),
    browser: detectBrowser(),
    domain: STATE.lastAudioDomain,
    tabId: STATE.lastAudioTabId,
    windowId: STATE.lastAudioWindowId,
    reason
  });

  await sendEvent(settings, event, () => {
    STATE.lastAudioDomain = null;
    STATE.lastAudioTabId = null;
    STATE.lastAudioWindowId = null;
    STATE.lastAudioTitle = null;
    STATE.lastAudioSentAtMs = 0;
    if (STATE.lastActivity === "audio") {
      STATE.lastDomain = null;
      STATE.lastTabId = null;
      STATE.lastWindowId = null;
      STATE.lastActivity = null;
    }
  });
}

async function chooseAudibleTab() {
  const audibleTabs = await chrome.tabs.query({ audible: true });
  const candidates = (audibleTabs || []).filter((tab) => safeHostname(tab.url || ""));
  if (!candidates.length) return null;

  if (typeof STATE.lastAudioTabId === "number") {
    const sameTab = candidates.find((tab) => tab.id === STATE.lastAudioTabId);
    if (sameTab) return sameTab;
  }

  candidates.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
  return candidates[0];
}

function activityState(activity) {
  if (activity === "audio") {
    return {
      domain: STATE.lastAudioDomain,
      tabId: STATE.lastAudioTabId,
      windowId: STATE.lastAudioWindowId,
      title: STATE.lastAudioTitle,
      sentAtMs: STATE.lastAudioSentAtMs
    };
  }
  return {
    domain: STATE.lastFocusDomain,
    tabId: STATE.lastFocusTabId,
    windowId: STATE.lastFocusWindowId,
    title: STATE.lastFocusTitle,
    sentAtMs: STATE.lastFocusSentAtMs
  };
}

function recordActivityState(activity, domain, tab, title, sentAtMs) {
  if (activity === "audio") {
    STATE.lastAudioDomain = domain;
    STATE.lastAudioTabId = tab.id;
    STATE.lastAudioWindowId = tab.windowId;
    STATE.lastAudioTitle = title;
    STATE.lastAudioSentAtMs = sentAtMs;
  } else {
    STATE.lastFocusDomain = domain;
    STATE.lastFocusTabId = tab.id;
    STATE.lastFocusWindowId = tab.windowId;
    STATE.lastFocusTitle = title;
    STATE.lastFocusSentAtMs = sentAtMs;
  }

  STATE.lastDomain = domain;
  STATE.lastTabId = tab.id;
  STATE.lastWindowId = tab.windowId;
  STATE.lastActivity = activity;
}

async function maybeEmitTabActivity(settings, tab, activity, force) {
  if (!tab || typeof tab.id !== "number" || typeof tab.windowId !== "number") {
    return;
  }

  const domain = safeHostname(tab.url || "");
  if (!domain) return;

  const last = activityState(activity);
  const title = titleForActivityState(tab, settings);
  const changed =
    domain !== last.domain ||
    tab.id !== last.tabId ||
    tab.windowId !== last.windowId ||
    title !== last.title;

  const heartbeatSeconds =
    Number(settings.heartbeatSeconds) || DEFAULT_SETTINGS.heartbeatSeconds;
  const heartbeatDue = Date.now() - last.sentAtMs >= heartbeatSeconds * 1000;

  if (!force && !changed && !heartbeatDue) return;

  const key = eventKey(activity, domain, tab, title);
  const event = buildTabActiveEvent({
    observedAt: nowIso(),
    seq: reserveSeq(STATE, key),
    activity,
    browser: detectBrowser(),
    tab,
    settings
  });
  if (!event) return;

  await sendEvent(settings, event, (sentAtMs) => {
    recordActivityState(activity, domain, tab, title, sentAtMs);
  });
}

async function emitActiveTabEvent({ force = false } = {}) {
  await ensureStateLoaded();

  const settings = await getSettings();
  await checkOffscreen(settings);
  await syncOffscreenDocument(settings);
  if (settings.enabled === false) return;

  await ensureHeartbeatAlarm();

  const browserFocused = await isBrowserFocused();

  if (browserFocused) {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const tab = tabs && tabs.length ? tabs[0] : null;
    await maybeEmitTabActivity(settings, tab, "focus", force);
  }

  if (settings.trackBackgroundAudio !== false) {
    const tab = await chooseAudibleTab();
    if (!tab) {
      await maybeEmitAudioStop(settings, "no_audible_tabs");
      return;
    }
    await maybeEmitTabActivity(settings, tab, "audio", force);
  } else {
    await maybeEmitAudioStop(settings, "tracking_disabled");
  }
}

async function emitActiveTabEventSafe(options) {
  try {
    await emitActiveTabEvent(options);
  } catch (caught) {
    try {
      await setStatus({ ok: false, error: String(caught) });
    } catch {
      // Ignore nested diagnostic failures.
    }
  }
}

async function bootstrap() {
  if (bootstrapping) return bootstrapping;
  bootstrapping = (async () => {
    await ensureStateLoaded();
    const settings = await getSettings();
    await checkOffscreen(settings);
    await syncOffscreenDocument(settings);
    await ensureHeartbeatAlarm();
    await setStatus({ ok: true, info: "boot" });
    await emitActiveTabEventSafe({ force: true });
  })()
    .catch(() => {})
    .finally(() => {
      bootstrapping = null;
    });
  return bootstrapping;
}

chrome.runtime.onInstalled.addListener(async () => {
  await ensureStateLoaded();
  await ensureDefaultSettings();
  await ensureHeartbeatAlarm();
  await setStatus({ ok: true, info: "installed" });
  await emitActiveTabEventSafe({ force: true });
});

chrome.runtime.onStartup?.addListener(async () => {
  await ensureStateLoaded();
  await ensureHeartbeatAlarm();
  await emitActiveTabEventSafe({ force: true });
});

chrome.tabs.onActivated.addListener(async () => {
  await emitActiveTabEventSafe();
});

chrome.windows.onFocusChanged.addListener(async () => {
  await emitActiveTabEventSafe({ force: true });
});

chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo) => {
  if (
    changeInfo.status === "complete" ||
    changeInfo.url ||
    changeInfo.title ||
    typeof changeInfo.audible === "boolean"
  ) {
    await emitActiveTabEventSafe();
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  if (typeof STATE.lastAudioTabId !== "number") return;
  if (tabId !== STATE.lastAudioTabId) return;
  await emitActiveTabEventSafe({ force: true });
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "heartbeat") return;
  await emitActiveTabEventSafe();
});

chrome.storage.onChanged.addListener(async (changes, areaName) => {
  if (areaName !== "local") return;
  if (
    changes.enabled ||
    changes.port ||
    changes.sendTitle ||
    changes.trackBackgroundAudio ||
    changes.keepAlive ||
    changes.heartbeatSeconds
  ) {
    await emitActiveTabEventSafe({ force: true });
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const type = message && typeof message === "object" ? message.type : null;

  if (type === "keepAlivePing") {
    ensureHeartbeatAlarm()
      .then(() => emitActiveTabEventSafe())
      .then(() => sendResponse({ ok: true }))
      .catch((caught) => sendResponse({ ok: false, error: String(caught) }));
    return true;
  }

  if (type === "diagnose") {
    (async () => {
      await ensureStateLoaded();
      const settings = await getSettings();
      await checkOffscreen(settings);
      await syncOffscreenDocument(settings);
      return {
        ok: true,
        settings,
        offscreen: lastOffscreen,
        state: { ...STATE }
      };
    })()
      .then((data) => sendResponse(data))
      .catch((caught) => sendResponse({ ok: false, error: String(caught) }));
    return true;
  }

  return false;
});

try {
  chrome.alarms.create("heartbeat", { periodInMinutes: 1 });
} catch {
  // Ignore startup race conditions.
}

bootstrap();
