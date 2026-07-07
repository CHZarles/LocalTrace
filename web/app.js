const state = {
  activeSection: "metricsView",
  topFilter: "all",
  events: [],
  settings: null,
  rules: [],
  tracking: { paused: false },
  health: null,
  lastRefreshAt: null,
  refreshInFlight: false,
  autoRefreshTimer: null
};

const $ = (id) => document.getElementById(id);
const METRICS_AUTO_REFRESH_MS = 2500;
const SOURCE_STALE_SECONDS = 300;

const SECTION_TITLES = {
  metricsView: "Metrics",
  settingsPanel: "Settings"
};

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

async function loadAll({ showBusy = false } = {}) {
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  if (showBusy) setBusy(true);
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
    state.lastRefreshAt = new Date();
    renderAll();
    setStatus(`Ready - UI refreshed ${formatAgeSince(state.lastRefreshAt, new Date())}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    state.refreshInFlight = false;
    if (showBusy) setBusy(false);
  }
}

function renderAll() {
  renderShell();
  renderToday();
  renderFlow(state.events);
  renderHealth(state.health);
  renderSettings(state.settings);
  renderRules(state.rules);
  renderTracking(state.tracking);
}

function renderShell() {
  for (const button of document.querySelectorAll(".nav-item")) {
    const active = button.dataset.section === state.activeSection;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  }
  for (const section of document.querySelectorAll(".view")) {
    section.classList.toggle("active", section.id === state.activeSection);
  }
  $("pageTitle").textContent = SECTION_TITLES[state.activeSection] || "Metrics";
}

function renderToday() {
  const model = buildTodayModel(state.events, state.settings);
  renderNow(model);
  renderSummary(model);
  renderTop(model);
  renderTimeline(model);
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
  const audioFreshnessSeconds = currentAudioFreshnessSeconds(settings);

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
  const latestAudio = latestActiveAudioEvent(
    todayEvents,
    audioFreshnessSeconds,
    now
  );

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

function currentAudioFreshnessSeconds(settings) {
  const heartbeatSeconds = Number(settings?.capture?.heartbeat_seconds);
  const heartbeat = Number.isFinite(heartbeatSeconds) && heartbeatSeconds > 0
    ? heartbeatSeconds
    : 60;
  return Math.max(90, heartbeat * 3);
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
    value.append(
      entityAvatar(
        event.entity_type,
        event.entity,
        displayEntity(event),
        event.payload?.activity || "focus"
      )
    );
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
  $("summaryMeta").textContent = model.todayEvents.length
    ? `${model.focusSegments.length} focus segments, ${model.audioSegments.length} audio segments`
    : "Waiting for activity";
}

function renderTop(model) {
  for (const button of document.querySelectorAll(".segment")) {
    button.classList.toggle("active", button.dataset.filter === state.topFilter);
  }
  const items = model.topItems
    .filter((item) => state.topFilter === "all" || item.kind === state.topFilter)
    .slice(0, 8);
  const maxSeconds = Math.max(1, ...items.map((item) => item.seconds));
  $("topMeta").textContent = items.length
    ? `${items.length} lanes by observed duration`
    : "No activity yet";
  $("topList").replaceChildren(
    ...items.map((item, index) => renderTopItem(item, index, maxSeconds))
  );
}

function renderTopItem(item, index, maxSeconds) {
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
  const meter = document.createElement("span");
  meter.className = item.audio ? "top-meter audio" : "top-meter focus";
  meter.style.width = `${Math.max(4, (item.seconds / maxSeconds) * 100)}%`;
  body.append(title, sub);
  row.append(
    rank,
    entityAvatar(item.kind, item.entity, item.label, item.activity),
    body,
    duration,
    meter
  );
  return row;
}

function renderTimeline(model) {
  const lanes = buildTimelineModel(model);
  $("timelineEmpty").hidden = lanes.length !== 0;
  $("timelineGrid").hidden = lanes.length === 0;
  $("timelineMeta").textContent = lanes.length
    ? `${lanes.length} top lanes from today`
    : "No timeline activity yet";
  $("timelineAxis").replaceChildren(...renderAxisTicks());
  $("timelineLanes").replaceChildren(...lanes.map(renderTimelineLane));
}

function renderAxisTicks() {
  return [0, 360, 720, 1080, 1440].map((minute) => {
    const tick = document.createElement("span");
    if (minute === 1440) tick.className = "end";
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

function renderFlow(events) {
  const items = [...events].sort(compareEventsDesc).slice(0, 14);
  $("flowEmpty").hidden = items.length !== 0;
  $("flowList").hidden = items.length === 0;
  $("flowMeta").textContent = items.length
    ? `${items.length} latest events`
    : "Latest captured activity";
  $("flowList").replaceChildren(...items.map(renderFlowItem));
}

function renderFlowItem(event) {
  const row = document.createElement("div");
  row.className = "flow-item";

  const time = document.createElement("time");
  time.className = "flow-time";
  time.dateTime = event.observed_at || "";
  time.textContent = formatFlowTime(event.observed_at);

  const body = document.createElement("div");
  body.className = "flow-body";
  const title = document.createElement("strong");
  const sub = document.createElement("span");
  const lag = receiveLagSeconds(event);
  title.textContent = displayEntity(event);
  sub.textContent = lag === null
    ? flowSubtitle(event)
    : `${flowSubtitle(event)} · receive lag ${formatCompactDuration(lag)}`;
  body.append(title, sub);

  const meta = document.createElement("div");
  meta.className = "flow-meta";
  meta.append(
    flowChip(eventKindLabel(event), flowActivity(event)),
    flowChip(event.source || "unknown")
  );

  row.append(
    time,
    entityAvatar(
      event.entity_type,
      event.entity,
      displayEntity(event),
      flowActivity(event)
    ),
    body,
    meta
  );
  return row;
}

function flowChip(text, activity = "focus") {
  const chip = document.createElement("span");
  chip.className = "flow-chip";
  chip.dataset.activity = activity;
  chip.textContent = text;
  return chip;
}

function flowSubtitle(event) {
  if (event.title) return event.title;
  if (event.payload?.reason) return `Reason: ${event.payload.reason}`;
  return event.kind || "";
}

function flowActivity(event) {
  return isAudioStartEvent(event) || isAudioStopEvent(event) ? "audio" : "focus";
}

function eventKindLabel(event) {
  switch (event.kind) {
    case "app_active":
      return "App focus";
    case "tab_active":
      return flowActivity(event) === "audio" ? "Tab audio" : "Tab focus";
    case "app_audio":
      return "App audio";
    case "app_audio_stop":
      return "Audio stopped";
    case "tab_audio_stop":
      return "Tab audio stopped";
    default:
      return event.kind || "Event";
  }
}

function renderHealth(health) {
  if (!health) return;
  const source = health.sources || {};
  const now = new Date();
  const metrics = [
    ["Service", health.service || "unknown"],
    ["Bind", `${health.bind?.host || "127.0.0.1"}:${health.bind?.port || ""}`],
    ["Database", health.database?.exists ? "exists" : "missing"],
    ["DB path", health.database?.path || ""],
    ["Stored events", String(health.events?.recent_count ?? 0)],
    ["Tracking", health.tracking?.paused ? "paused" : "active"],
    [
      "UI refreshed",
      state.lastRefreshAt ? formatAgeSince(state.lastRefreshAt, now) : "unknown"
    ],
    [
      "Windows probe",
      sourceHealthLabel("windows_probe", source.windows_probe, now)
    ],
    [
      "Browser extension",
      sourceHealthLabel("browser_extension", source.browser_extension, now)
    ]
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

function entityAvatar(kind, entity, label, activity = "focus") {
  const avatar = document.createElement("span");
  avatar.className = "entity-avatar";
  avatar.dataset.kind = kind || "app";
  avatar.dataset.activity = activity;
  avatar.style.setProperty("--avatar-hue", String(hashHue(`${kind}:${entity}`)));
  avatar.append(iconForEntity(kind, activity));
  return avatar;
}

function iconForEntity(kind, activity) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("entity-icon");
  const paths =
    activity === "audio"
      ? ["M4 14a8 8 0 0 1 16 0", "M6 14h2v6H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2Z", "M16 14h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2v-6Z"]
      : kind === "domain"
        ? ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M3.6 9h16.8", "M3.6 15h16.8", "M12 3a13 13 0 0 1 0 18", "M12 3a13 13 0 0 0 0 18"]
        : ["M4 5h16v11H4Z", "M8 20h8", "M10 16v4", "M14 16v4"];
  for (const d of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
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

function latestActiveAudioEvent(eventsDesc, idleSeconds, now) {
  const latestStopByKey = new Map();
  const maxAgeMs = Math.max(1, Number(idleSeconds) || 300) * 1000;
  for (const event of eventsDesc) {
    const observedAt = parseDate(event.observed_at);
    if (!observedAt) continue;
    if (now.getTime() - observedAt.getTime() > maxAgeMs) break;

    const key = `${event.source}:${event.entity_type}:${event.entity}`;
    if (isAudioStopEvent(event) && !latestStopByKey.has(key)) {
      latestStopByKey.set(key, observedAt);
      continue;
    }
    if (!isAudioStartEvent(event)) continue;
    const stopAt = latestStopByKey.get(key);
    if (!stopAt || observedAt > stopAt) return event;
  }
  return null;
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function compareEventsAsc(a, b) {
  const ta = parseDate(a.observed_at)?.getTime() ?? 0;
  const tb = parseDate(b.observed_at)?.getTime() ?? 0;
  return ta - tb || Number(a.id || 0) - Number(b.id || 0);
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

function sourceHealthLabel(label, source, now) {
  const observedAt = parseDate(source?.last_observed_at);
  if (!observedAt) return `${label} not seen`;
  const ageSeconds = elapsedSeconds(observedAt, now);
  const freshness = ageSeconds > SOURCE_STALE_SECONDS ? "stale" : "fresh";
  const parts = [
    `${freshness} ${formatCompactDuration(ageSeconds)} ago`
  ];
  const lag = receiveLagSeconds({
    observed_at: source.last_observed_at,
    received_at: source.last_received_at
  });
  if (lag !== null) parts.push(`lag ${formatCompactDuration(lag)}`);
  return parts.join(" · ");
}

function receiveLagSeconds(event) {
  const observedAt = parseDate(event?.observed_at);
  const receivedAt = parseDate(event?.received_at);
  if (!observedAt || !receivedAt) return null;
  return elapsedSeconds(observedAt, receivedAt);
}

function elapsedSeconds(start, end) {
  return Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));
}

function formatAgeSince(value, now) {
  const date = parseDate(value);
  if (!date) return "unknown";
  return `${formatCompactDuration(elapsedSeconds(date, now))} ago`;
}

function formatCompactDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 1) return "<1s";
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function displayEntity(event) {
  const entity = event?.entity || "";
  if (!entity) return "unknown";
  return entity;
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

function formatFlowTime(value) {
  const date = parseDate(value);
  if (!date) return value || "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function setSection(sectionId) {
  state.activeSection = sectionId;
  renderShell();
  $(sectionId)?.scrollIntoView({ block: "start" });
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
  button.addEventListener("click", () => setSection(button.dataset.section));
}
for (const button of document.querySelectorAll(".segment")) {
  button.addEventListener("click", () => {
    state.topFilter = button.dataset.filter || "all";
    renderToday();
  });
}

$("refreshButton").addEventListener("click", () => loadAll({ showBusy: true }));
$("saveSettings").addEventListener("click", saveSettings);
$("addRule").addEventListener("click", addRule);
$("pauseButton").addEventListener("click", () => setTracking("/tracking/pause"));
$("resumeButton").addEventListener("click", () => setTracking("/tracking/resume"));

loadAll({ showBusy: true });
state.autoRefreshTimer = window.setInterval(loadAll, METRICS_AUTO_REFRESH_MS);
