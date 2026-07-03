export const LOOPBACK_HOST = "127.0.0.1";
export const DEFAULT_PORT = 8765;

export const DEFAULT_SETTINGS = {
  enabled: true,
  port: DEFAULT_PORT,
  sendTitle: true,
  trackBackgroundAudio: true,
  keepAlive: true,
  heartbeatSeconds: 60
};

export function endpointFromSettings(settings = {}) {
  const port = normalizePort(settings.port);
  return `http://${LOOPBACK_HOST}:${port}/events`;
}

export function healthEndpointFromSettings(settings = {}) {
  const port = normalizePort(settings.port);
  return `http://${LOOPBACK_HOST}:${port}/health`;
}

export function normalizePort(value) {
  const parsed = Number.parseInt(String(value ?? DEFAULT_PORT), 10);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    return DEFAULT_PORT;
  }
  return parsed;
}

export function safeHostname(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.hostname || null;
  } catch {
    return null;
  }
}

export function buildTabActiveEvent({
  observedAt,
  seq,
  activity,
  browser,
  tab,
  settings = DEFAULT_SETTINGS
}) {
  const domain = safeHostname(tab?.url || "");
  if (!domain) return null;

  const payload = {
    activity,
    browser,
    window_id: tab.windowId,
    tab_id: tab.id
  };

  const title =
    settings.sendTitle !== false && typeof tab.title === "string" && tab.title.trim()
      ? tab.title
      : null;

  return {
    observed_at: observedAt,
    source: "browser_extension",
    seq,
    kind: "tab_active",
    entity_type: "domain",
    entity: domain,
    title,
    payload
  };
}

export function buildTabAudioStopEvent({
  observedAt,
  seq,
  browser,
  domain,
  tabId,
  windowId,
  reason
}) {
  return {
    observed_at: observedAt,
    source: "browser_extension",
    seq,
    kind: "tab_audio_stop",
    entity_type: "domain",
    entity: domain,
    title: null,
    payload: {
      activity: "audio",
      browser,
      reason,
      window_id: windowId,
      tab_id: tabId
    }
  };
}

export function reserveSeq(state, pendingKey) {
  if (state.pendingKey === pendingKey && Number.isInteger(state.pendingSeq)) {
    return state.pendingSeq;
  }
  const nextSeq = Number.isInteger(state.seq) ? state.seq + 1 : 1;
  state.seq = nextSeq;
  state.pendingKey = pendingKey;
  state.pendingSeq = nextSeq;
  return nextSeq;
}

export function clearPendingSeq(state) {
  state.pendingKey = null;
  state.pendingSeq = null;
}
