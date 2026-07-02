const state = {
  activeView: "todayView",
  topFilter: "all",
  events: [],
  settings: null,
  rules: [],
  tracking: { paused: false },
  health: null
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
    const [health, events, settings, privacy, tracking] = await Promise.all([
      api("/health"),
      api("/events?limit=500&order=desc"),
      api("/settings"),
      api("/privacy/rules"),
      api("/tracking/status")
    ]);
    state.health = health;
    state.events = events.events || [];
    state.settings = settings.settings;
    state.rules = privacy.rules;
    state.tracking = tracking;
    renderAll();
    setStatus("Ready");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function renderAll() {
  renderShell();
  renderToday();
  renderHealth(state.health);
  renderSettings(state.settings);
  renderRules(state.rules);
  renderTracking(state.tracking);
}

function renderShell() {
  for (const button of document.querySelectorAll(".nav-item")) {
    const active = button.dataset.view === state.activeView;
    button.classList.toggle("active", active);
  }
  for (const view of document.querySelectorAll(".view")) {
    view.hidden = view.id !== state.activeView;
  }
  $("pageTitle").textContent =
    state.activeView === "settingsPanel" ? "Settings" : "Today";
}

function renderToday() {
  const model = buildTodayModel(state.events, state.settings);
  renderNow(model);
  renderSummary(model);
  renderTop(model);
  renderTimeline(model);
  renderEvents(model.todayEvents);
}

function buildTodayModel(events, settings) {
  const now = new Date();
  const todayEvents = events
    .filter((event) => isSameLocalDay(parseDate(event.observed_at), now))
    .sort(compareEventsDesc);
  const ascending = [...todayEvents].sort(compareEventsAsc);
  const idleSeconds =
    settings?.capture?.idle_cutoff_seconds &&
    Number.isFinite(settings.capture.idle_cutoff_seconds)
      ? settings.capture.idle_cutoff_seconds
      : 300;

  const focusSegments = buildFocusSegments(ascending, idleSeconds, now);
  const audioSegments = buildAudioSegments(ascending, idleSeconds, now);
  const segments = [...focusSegments, ...audioSegments].sort(
    (a, b) => a.start - b.start
  );
  const topItems = buildTopItems(segments);
  const latestFocus = todayEvents.find(isFocusEvent) || null;
  const latestTab = todayEvents.find(
    (event) => event.source === "browser_extension" && isFocusEvent(event)
  );
  const latestAudio = latestActiveAudioEvent(todayEvents);

  return {
    now,
    todayEvents,
    focusSegments,
    audioSegments,
    segments,
    topItems,
    latestFocus,
    latestTab: latestTab || null,
    latestAudio,
    focusSeconds: sumSeconds(focusSegments),
    audioSeconds: sumSeconds(audioSegments),
    focusSwitches: focusSegments.length
  };
}

function buildFocusSegments(events, idleSeconds, now) {
  const focusEvents = events.filter(isFocusEvent);
  return focusEvents.flatMap((event, index) => {
    const start = parseDate(event.observed_at);
    const next = focusEvents[index + 1]
      ? parseDate(focusEvents[index + 1].observed_at)
      : now;
    return segmentFromEvent(event, start, next, idleSeconds, false);
  });
}

function buildAudioSegments(events, idleSeconds, now) {
  const audioEvents = events.filter(isAudioBoundaryEvent);
  const segments = [];
  for (let index = 0; index < audioEvents.length; index += 1) {
    const event = audioEvents[index];
    if (!isAudioStartEvent(event)) continue;
    const start = parseDate(event.observed_at);
    const stop = nextAudioStop(audioEvents, index, event);
    const next = stop
      ? parseDate(stop.observed_at)
      : nextAudioBoundary(audioEvents, index, event, now);
    segments.push(...segmentFromEvent(event, start, next, idleSeconds, true));
  }
  return segments;
}

function segmentFromEvent(event, start, next, idleSeconds, audio) {
  if (!start || !next) return [];
  const maxEnd = new Date(start.getTime() + idleSeconds * 1000);
  const end = new Date(Math.min(next.getTime(), maxEnd.getTime()));
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds <= 0) return [];
  return [
    {
      source: event.source,
      kind: event.entity_type || "app",
      entity: event.entity || "unknown",
      label: displayEntity(event),
      subtitle: event.title || "",
      activity: audio ? "audio" : "focus",
      audio,
      start,
      end,
      seconds
    }
  ];
}

function buildTopItems(segments) {
  const map = new Map();
  for (const segment of segments) {
    const key = `${segment.kind}:${segment.entity}:${segment.activity}`;
    const current =
      map.get(key) ||
      {
        kind: segment.kind,
        entity: segment.entity,
        label: segment.label,
        subtitle: segment.subtitle,
        activity: segment.activity,
        audio: segment.audio,
        seconds: 0
      };
    current.seconds += segment.seconds;
    if (!current.subtitle && segment.subtitle) current.subtitle = segment.subtitle;
    map.set(key, current);
  }
  return [...map.values()].sort(
    (a, b) => b.seconds - a.seconds || a.label.localeCompare(b.label)
  );
}

function buildTimelineModel(model) {
  const lanes = new Map();
  for (const segment of model.segments) {
    const key = `${segment.kind}:${segment.entity}`;
    const lane =
      lanes.get(key) ||
      {
        kind: segment.kind,
        entity: segment.entity,
        label: segment.label,
        subtitle: segment.subtitle,
        totalSeconds: 0,
        bars: []
      };
    lane.totalSeconds += segment.seconds;
    lane.bars.push({
      audio: segment.audio,
      startMinute: minuteOfDay(segment.start),
      endMinute: minuteOfDay(segment.end),
      title: `${segment.label} - ${formatDuration(segment.seconds)}`
    });
    lanes.set(key, lane);
  }
  return [...lanes.values()]
    .sort((a, b) => b.totalSeconds - a.totalSeconds || a.label.localeCompare(b.label))
    .slice(0, 12);
}

function renderNow(model) {
  $("nowFreshness").textContent = model.todayEvents.length
    ? `Updated ${formatTime(model.todayEvents[0].observed_at)}`
    : "No data";
  renderNowRow($("nowFocus"), {
    label: "Focus app",
    event: model.latestFocus,
    fallback: "No focus activity"
  });
  renderNowRow($("nowTab"), {
    label: "Using tab",
    event: model.latestTab,
    fallback: "No browser activity"
  });
  renderNowRow($("nowAudio"), {
    label: "Background audio",
    event: model.latestAudio,
    fallback: "No audio activity"
  });
}

function renderNowRow(target, { label, event, fallback }) {
  target.replaceChildren();
  const meta = document.createElement("span");
  meta.className = "row-label";
  meta.textContent = label;
  const value = document.createElement("div");
  value.className = "row-value";
  if (event) {
    value.append(entityAvatar(event.entity_type, event.entity, displayEntity(event)));
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const sub = document.createElement("span");
    title.textContent = displayEntity(event);
    sub.textContent = event.title || formatTime(event.observed_at);
    text.append(title, sub);
    value.append(text);
  } else {
    value.textContent = fallback;
  }
  target.append(meta, value);
}

function renderSummary(model) {
  $("focusTotal").textContent = formatDuration(model.focusSeconds);
  $("audioTotal").textContent = formatDuration(model.audioSeconds);
  $("focusSwitches").textContent = String(model.focusSwitches);
  $("todayEventsCount").textContent = String(model.todayEvents.length);
}

function renderTop(model) {
  for (const button of document.querySelectorAll(".segment")) {
    button.classList.toggle("active", button.dataset.filter === state.topFilter);
  }
  const items = model.topItems
    .filter((item) => state.topFilter === "all" || item.kind === state.topFilter)
    .slice(0, 10);
  $("topMeta").textContent = items.length
    ? `${items.length} lanes by observed duration`
    : "No activity yet";
  $("topList").replaceChildren(...items.map(renderTopItem));
}

function renderTopItem(item, index) {
  const row = document.createElement("div");
  row.className = "top-item";
  const rank = document.createElement("span");
  rank.className = "rank";
  rank.textContent = String(index + 1).padStart(2, "0");
  const body = document.createElement("div");
  body.className = "top-body";
  const title = document.createElement("strong");
  const sub = document.createElement("span");
  title.textContent = item.label;
  sub.textContent = `${item.kind} - ${item.audio ? "audio" : "focus"}`;
  const duration = document.createElement("b");
  duration.textContent = formatDuration(item.seconds);
  body.append(title, sub);
  row.append(rank, entityAvatar(item.kind, item.entity, item.label), body, duration);
  return row;
}

function renderTimeline(model) {
  const lanes = buildTimelineModel(model);
  $("timelineEmpty").hidden = lanes.length !== 0;
  $("timelineGrid").hidden = lanes.length === 0;
  $("timelineMeta").textContent = lanes.length
    ? `${lanes.length} top lanes from raw events`
    : "No timeline activity yet";
  $("timelineAxis").replaceChildren(...renderAxisTicks());
  $("timelineLanes").replaceChildren(...lanes.map(renderTimelineLane));
}

function renderAxisTicks() {
  return [0, 360, 720, 1080, 1440].map((minute) => {
    const tick = document.createElement("span");
    tick.style.left = `${(minute / 1440) * 100}%`;
    tick.textContent = minute === 1440 ? "24:00" : `${String(minute / 60).padStart(2, "0")}:00`;
    return tick;
  });
}

function renderTimelineLane(lane) {
  const row = document.createElement("div");
  row.className = "timeline-row";
  const label = document.createElement("div");
  label.className = "timeline-lane-label";
  const text = document.createElement("div");
  const title = document.createElement("strong");
  const sub = document.createElement("span");
  title.textContent = lane.label;
  sub.textContent = formatDuration(lane.totalSeconds);
  text.append(title, sub);
  label.append(entityAvatar(lane.kind, lane.entity, lane.label), text);

  const track = document.createElement("div");
  track.className = "timeline-track";
  for (const bar of lane.bars) {
    const item = document.createElement("span");
    item.className = bar.audio ? "timeline-bar audio" : "timeline-bar focus";
    item.title = bar.title;
    item.style.left = `${(bar.startMinute / 1440) * 100}%`;
    item.style.width = `${Math.max(0.3, ((bar.endMinute - bar.startMinute) / 1440) * 100)}%`;
    track.append(item);
  }
  row.append(label, track);
  return row;
}

function renderEvents(events) {
  const latest = events.slice(0, 40);
  $("eventsCount").textContent = latest.length
    ? `${latest.length} latest events`
    : "No events";
  $("eventsEmpty").hidden = latest.length !== 0;
  $("eventsTable").replaceChildren(
    ...latest.map((event) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(formatTime(event.observed_at)),
        entityCell(event),
        cell(event.kind || ""),
        cell(event.payload?.activity || ""),
        cell(sourceLabel(event.source))
      );
      return tr;
    })
  );
}

function renderHealth(health) {
  if (!health) return;
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
  if (!settings) return;
  $("apiPort").value = settings.api.port;
  $("pollMs").value = settings.capture.poll_ms;
  $("heartbeatSeconds").value = settings.capture.heartbeat_seconds;
  $("idleCutoffSeconds").value = settings.capture.idle_cutoff_seconds;
  $("storeTitles").checked = settings.capture.store_titles;
  $("storeExePath").checked = settings.capture.store_exe_path;
  $("trackBrowser").checked = settings.capture.track_browser;
  $("trackAudio").checked = settings.capture.track_audio;
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
  $("trackingPill").textContent = tracking.paused ? "Paused" : "Tracking";
  $("trackingPill").classList.toggle("paused", tracking.paused);
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function entityCell(event) {
  const td = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "entity-cell";
  wrap.append(entityAvatar(event.entity_type, event.entity, displayEntity(event)));
  const text = document.createElement("div");
  const title = document.createElement("strong");
  const sub = document.createElement("span");
  title.textContent = displayEntity(event);
  sub.textContent = event.title || event.entity_type || "";
  text.append(title, sub);
  wrap.append(text);
  td.append(wrap);
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

function entityAvatar(kind, entity, label) {
  const avatar = document.createElement("span");
  avatar.className = "entity-avatar";
  avatar.dataset.kind = kind || "app";
  avatar.textContent = firstGlyph(kind === "domain" ? entity : label);
  avatar.style.setProperty("--avatar-hue", String(hashHue(`${kind}:${entity}`)));
  return avatar;
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
    renderToday();
    if (body.restart_required?.includes("api.port")) {
      setStatus("Saved; restart required for port");
    } else {
      setStatus("Saved");
    }
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

function isFocusEvent(event) {
  if (!event || event.kind?.endsWith("_stop")) return false;
  const activity = event.payload?.activity || "focus";
  if (activity === "audio") return false;
  return event.kind === "app_active" || event.kind === "tab_active";
}

function isAudioStartEvent(event) {
  if (!event || event.kind?.endsWith("_stop")) return false;
  return event.kind === "app_audio" || event.payload?.activity === "audio";
}

function isAudioStopEvent(event) {
  return event?.kind === "app_audio_stop" || event?.kind === "tab_audio_stop";
}

function isAudioBoundaryEvent(event) {
  return isAudioStartEvent(event) || isAudioStopEvent(event);
}

function nextAudioStop(audioEvents, index, event) {
  for (let i = index + 1; i < audioEvents.length; i += 1) {
    const candidate = audioEvents[i];
    if (
      candidate.source === event.source &&
      candidate.entity_type === event.entity_type &&
      candidate.entity === event.entity &&
      isAudioStopEvent(candidate)
    ) {
      return candidate;
    }
    if (
      candidate.source === event.source &&
      candidate.entity_type === event.entity_type &&
      candidate.entity === event.entity &&
      isAudioStartEvent(candidate)
    ) {
      return null;
    }
  }
  return null;
}

function nextAudioBoundary(audioEvents, index, event, now) {
  for (let i = index + 1; i < audioEvents.length; i += 1) {
    const candidate = audioEvents[i];
    if (
      candidate.source === event.source &&
      candidate.entity_type === event.entity_type &&
      candidate.entity === event.entity
    ) {
      return parseDate(candidate.observed_at);
    }
  }
  return now;
}

function latestActiveAudioEvent(eventsDesc) {
  const latestStopByKey = new Map();
  for (const event of eventsDesc) {
    const key = `${event.source}:${event.entity_type}:${event.entity}`;
    if (isAudioStopEvent(event) && !latestStopByKey.has(key)) {
      latestStopByKey.set(key, parseDate(event.observed_at));
      continue;
    }
    if (!isAudioStartEvent(event)) continue;
    const observedAt = parseDate(event.observed_at);
    const stopAt = latestStopByKey.get(key);
    if (!stopAt || observedAt > stopAt) return event;
  }
  return null;
}

function parseDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function compareEventsAsc(a, b) {
  return (
    parseDate(a.observed_at).getTime() - parseDate(b.observed_at).getTime() ||
    Number(a.id || 0) - Number(b.id || 0)
  );
}

function compareEventsDesc(a, b) {
  return -compareEventsAsc(a, b);
}

function isSameLocalDay(a, b) {
  if (!a || !b) return false;
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function minuteOfDay(date) {
  return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
}

function sumSeconds(segments) {
  return segments.reduce((sum, item) => sum + item.seconds, 0);
}

function displayEntity(event) {
  const entity = event?.entity || "";
  if (!entity) return "unknown";
  return entity;
}

function firstGlyph(value) {
  const text = String(value || "?").trim();
  return (text[0] || "?").toUpperCase();
}

function hashHue(input) {
  let hash = 0x811c9dc5;
  for (const char of input) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash % 360;
}

function formatDuration(seconds) {
  if (seconds > 0 && seconds < 60) return "<1m";
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatTime(value) {
  const date = parseDate(value);
  if (!date) return value || "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(date);
}

function sourceLabel(source) {
  if (source === "windows_probe") return "Windows";
  if (source === "browser_extension") return "Browser";
  return source || "";
}

function setView(viewId) {
  state.activeView = viewId;
  renderShell();
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

for (const button of document.querySelectorAll(".nav-item")) {
  button.addEventListener("click", () => setView(button.dataset.view));
}
for (const button of document.querySelectorAll(".segment")) {
  button.addEventListener("click", () => {
    state.topFilter = button.dataset.filter || "all";
    renderToday();
  });
}

$("refreshButton").addEventListener("click", loadAll);
$("saveSettings").addEventListener("click", saveSettings);
$("addRule").addEventListener("click", addRule);
$("pauseButton").addEventListener("click", () => setTracking("/tracking/pause"));
$("resumeButton").addEventListener("click", () => setTracking("/tracking/resume"));

loadAll();
