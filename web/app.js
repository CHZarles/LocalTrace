const state = {
  events: [],
  settings: null,
  rules: [],
  tracking: { paused: false },
  health: null,
  view: "dashboard"
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
    renderDashboard(state);
  } catch (error) {
    console.error(error);
  } finally {
    setBusy(false);
  }
}

function renderDashboard(state) {
  const model = buildDashboardModel(state.events, state.settings);
  renderKpis(model);
  renderTimeline(model);
  renderRightNow(model);
  renderRecentFlow(state.events);
  renderStatusBar(model, state.health);
  renderTracking(state.tracking);
  renderSettings(state.settings);
  renderRules(state.rules);
}

function buildDashboardModel(events, settings) {
  const now = new Date();
  const todayEvents = events
    .filter((event) => isSameLocalDay(parseDate(event.observed_at), now))
    .sort(compareEventsDesc);
  const ascending = [...todayEvents].sort(compareEventsAsc);
  const idleSeconds =
    settings?.capture?.idle_cutoff_seconds && Number.isFinite(settings.capture.idle_cutoff_seconds)
      ? settings.capture.idle_cutoff_seconds
      : 300;
  const audioFreshnessSeconds = currentAudioFreshnessSeconds(settings);

  const focusSegments = buildFocusSegments(ascending, idleSeconds, now);
  const audioSegments = buildAudioSegments(ascending, idleSeconds, now);
  const focusSeconds = sumSeconds(focusSegments);
  const audioSeconds = sumSeconds(audioSegments);

  const latestFocus = todayEvents.find(isFocusEvent) || null;
  const latestTab = todayEvents.find(
    (event) => event.source === "browser_extension" && isFocusEvent(event)
  );
  const latestAudio = latestActiveAudioEvent(todayEvents, audioFreshnessSeconds, now);

  const timelineBuckets = buildTimelineBuckets(focusSegments, audioSegments, now);

  const latestObservedAt =
    state.events.length > 0
      ? parseDate(state.events.slice().sort(compareEventsAsc).slice(-1)[0]?.observed_at)
      : null;

  return {
    now,
    todayEvents,
    focusSegments,
    audioSegments,
    focusSeconds,
    audioSeconds,
    focusSwitches: focusSegments.length,
    todayEventsCount: todayEvents.length,
    timelineBuckets,
    latestFocus,
    latestTab,
    latestAudio,
    latestObservedAt
  };
}

function buildTimelineBuckets(focusSegments, audioSegments, now) {
  const HOURS = 24;
  const bucketMs = (60 * 60 * 1000) / 2; // 30-min slots
  const buckets = [];
  for (let i = 0; i < HOURS; i += 1) {
    buckets.push({ index: i, start: null, end: null, focus: false, audio: false, idle: true });
  }
  const mark = (segment) => {
    if (!segment.start || !segment.end) return;
    let s = segment.start.getTime();
    const e = segment.end.getTime();
    while (s < e) {
      const hour = s.getUTCHours ? s : new Date(s).getUTCHours();
      // hour-of-day in UTC for placement; clamped into 0..HOURS-1
      const hourOfDay = new Date(s).getUTCHours();
      const idx = Math.min(HOURS - 1, Math.max(0, hourOfDay));
      const b = buckets[idx];
      if (segment.audio) b.audio = true; else b.focus = true;
      b.idle = !(b.focus || b.audio);
      s += bucketMs;
    }
  };
  for (const seg of focusSegments) mark(seg);
  for (const seg of audioSegments) mark(seg);
  return buckets;
}

function currentAudioFreshnessSeconds(settings) {
  const heartbeatSeconds = Number(settings?.capture?.heartbeat_seconds);
  const heartbeat = Number.isFinite(heartbeatSeconds) && heartbeatSeconds > 0
    ? heartbeatSeconds
    : 60;
  return Math.max(90, heartbeat * 3);
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

function renderKpis(model) {
  $("kpiFocusNum").innerHTML = `${formatHm(model.focusSeconds)}<span class="unit">h:m</span>`;
  $("kpiFocusFoot").textContent = model.focusSeconds > 0
    ? `Goal 5:00 · ${minutesToGo(5 * 3600 - model.focusSeconds)} to go`
    : "No focus yet";

  $("kpiAudioNum").innerHTML = `${Math.max(0, Math.round(model.audioSeconds / 60))}<span class="unit">m</span>`;
  $("kpiAudioFoot").textContent = model.audioSegments.length
    ? `${model.audioSegments.length} session${model.audioSegments.length === 1 ? "" : "s"}`
    : "No audio captured";

  $("kpiSwitchesNum").textContent = String(model.focusSwitches);
  $("kpiSwitchesFoot").textContent = model.todayEventsCount
    ? `${model.todayEventsCount} events today`
    : "No activity yet";

  $("kpiEventsNum").textContent = String(model.todayEventsCount);
  $("kpiEventsFoot").textContent = model.todayEventsCount
    ? `${Math.round(model.todayEventsCount / Math.max(1, hoursElapsed(model.now)))} / hr · db synced`
    : "— / hr · db synced";
}

function renderTimeline(model) {
  const focusMinutes = Math.round(model.focusSeconds / 60);
  const totalMinutes = focusMinutes + Math.round(model.audioSeconds / 60);
  $("timelineTitle").textContent = `${formatHm(model.focusSeconds)} / ${totalMinutes}m`;

  const bars = $("timelineBars");
  bars.replaceChildren();
  const now = model.now;
  const nowHourIdx = computeNowIndex(model.now);
  for (let i = 0; i < 24; i += 1) {
    const cell = document.createElement("span");
    cell.className = "timeline-bar";
    const bucket = model.timelineBuckets[i];
    if (i === nowHourIdx) {
      cell.classList.add("now");
    } else if (bucket?.audio && !bucket?.focus) {
      cell.classList.add("audio");
    } else if (bucket?.focus) {
      cell.classList.add("focus");
    } else {
      cell.classList.add("idle");
    }
    bars.append(cell);
  }

  $("timelineMeta").textContent =
    `12h window · focus ${formatHm(model.focusSeconds)} · audio ${Math.round(model.audioSeconds / 60)}m`;

  const axis = $("timelineAxis");
  axis.replaceChildren();
  const ticks = [
    { label: "02", at: 2 },
    { label: "06", at: 6 },
    { label: "10", at: 10 },
    { label: "14", at: 14 },
    { label: "18", at: 18 },
    { label: "22", at: 22 },
    { label: "NOW", at: 24 }
  ];
  for (const t of ticks) {
    const span = document.createElement("span");
    span.textContent = t.label;
    axis.append(span);
  }
}

function computeNowIndex(now) {
  const h = now.getHours();
  return Math.min(23, Math.max(0, h));
}

function renderRightNow(model) {
  const rows = [
    { label: "Focus app", event: model.latestFocus, fallback: "No focus activity" },
    { label: "Using tab", event: model.latestTab, fallback: "No browser activity" },
    { label: "Background audio", event: model.latestAudio, fallback: "No audio activity" }
  ];
  const list = $("nowList");
  list.replaceChildren();
  for (const row of rows) list.append(rightNowRow(row));

  let active = 0;
  for (const row of rows) if (row.event) active += 1;
  $("nowCount").textContent = `${active} active`;

  const latestAt =
    model.latestAudio?.observed_at ||
    model.latestTab?.observed_at ||
    model.latestFocus?.observed_at;
  $("nowFoot").textContent = latestAt
    ? `Updated ${formatTime(latestAt)}`
    : "Waiting for activity";
}

function rightNowRow({ label, event, fallback }) {
  const row = document.createElement("div");
  row.className = "now-row";

  const entity = document.createElement("div");
  entity.className = "row-entity";
  if (event) {
    entity.append(
      entityAvatar(
        event.entity_type,
        event.entity,
        displayEntity(event),
        isAudioStartEvent(event) ? "audio" : "focus"
      )
    );
    const text = document.createElement("div");
    text.className = "text";
    const title = document.createElement("div");
    title.className = "now-name";
    title.textContent = displayEntity(event);
    const ctx = document.createElement("span");
    ctx.className = "ctx";
    ctx.textContent = event.title || formatTime(event.observed_at);
    text.append(title, ctx);
    entity.append(text);
  } else {
    entity.append(document.createTextNode(fallback));
  }
  row.append(entity);

  const time = document.createElement("div");
  time.className = "now-time";
  if (event) {
    if (isAudioStartEvent(event)) {
      time.innerHTML = `<span class="v">playing</span>`;
    } else if (isAudioStopEvent(event)) {
      time.innerHTML = `<span class="v">stopped</span>`;
    } else {
      const recentMinutes = sinceMinutes(event.observed_at, new Date());
      time.innerHTML = `<span class="v">${recentMinutes}m</span> ago`;
    }
  }
  row.append(time);
  return row;
}

function renderRecentFlow(events) {
  const body = $("flowBody");
  body.replaceChildren();
  const items = [...events].sort(compareEventsDesc).slice(0, 10);
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.style.padding = "14px 18px";
    empty.style.color = "var(--text-2)";
    empty.textContent = "No recent activity";
    body.append(empty);
    return;
  }
  for (const event of items) body.append(appendFlowRow(event));
}

function appendFlowRow(event) {
  const row = document.createElement("div");
  row.className = "flow-row";

  const t = document.createElement("span");
  t.className = "t";
  t.textContent = formatTime(event.observed_at);
  row.append(t);

  const app = document.createElement("span");
  app.className = "app";
  const title = document.createElement("strong");
  title.textContent = displayEntity(event);
  const ctx = document.createElement("span");
  ctx.className = "ctx";
  ctx.textContent = event.title || eventKindLabel(event);
  app.append(title, ctx);
  row.append(app);

  const dur = document.createElement("span");
  dur.className = "num";
  // approximate duration by suffix we cannot reliably compute, but for flow show the related recent period
  dur.textContent = computeEventDurationLabel(event);
  row.append(dur);

  const src = document.createElement("span");
  src.className = "src";
  const chip = document.createElement("span");
  chip.className = "flow-chip";
  chip.dataset.source = event.source || "system";
  chip.textContent = sourceLabel(event.source);
  src.append(chip);
  row.append(src);

  return row;
}

function computeEventDurationLabel(event) {
  if (event.kind?.endsWith("_stop")) return "stop";
  if (isAudioStartEvent(event) || isAudioStopEvent(event)) return "audio";
  const at = parseDate(event.observed_at);
  if (!at) return "—";
  const minutes = Math.max(0, Math.round((Date.now() - at.getTime()) / 60000));
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes}m`;
}

function sourceLabel(source) {
  if (source === "windows_probe") return "win";
  if (source === "browser_extension") return "browser";
  if (source === "system") return "system";
  return source || "system";
}

function eventKindLabel(event) {
  switch (event.kind) {
    case "app_active":
      return "App focus";
    case "tab_active":
      return isAudioStartEvent(event) ? "Tab audio" : "Tab focus";
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

function renderStatusBar(model, health) {
  const dots = document.querySelectorAll(".status-bar .dot");
  const dbExists = health?.database?.exists;
  const wLast = health?.sources?.windows_probe?.last_observed_at;
  const bLast = health?.sources?.browser_extension?.last_observed_at;
  for (const dot of dots) {
    const kind = dot.dataset.health;
    dot.classList.remove("red", "green");
    if (kind === "db") {
      dot.classList.add(dbExists ? "green" : "red");
    } else if (kind === "browser") {
      dot.classList.add(bLast ? "green" : "red");
    } else if (kind === "winprobe") {
      dot.classList.add(wLast ? "green" : "red");
    }
  }
  const upd = $("statusUpdated");
  if (upd) {
    const latest = state.events
      .slice()
      .sort(compareEventsAsc)
      .slice(-1)[0];
    if (latest) {
      upd.textContent = `${sinceSeconds(latest.observed_at, new Date())}s ago`;
    } else {
      upd.textContent = "—";
    }
  }
  const counts = $("statusCounts");
  if (counts) {
    counts.textContent = `${model.todayEventsCount} events · ${formatHm(model.focusSeconds)} focused`;
  }
}

function renderTracking(tracking) {
  if (!tracking) return;
  const pill = $("trackingPill");
  if (pill) {
    pill.textContent = tracking.paused ? "Paused" : "Tracking";
  }
}

function renderSettings(settings) {
  if (!settings) return;
  if ($("apiPort")) $("apiPort").value = settings.api.port;
  if ($("pollMs")) $("pollMs").value = settings.capture.poll_ms;
  if ($("heartbeatSeconds")) $("heartbeatSeconds").value = settings.capture.heartbeat_seconds;
  if ($("idleCutoffSeconds")) $("idleCutoffSeconds").value = settings.capture.idle_cutoff_seconds;
  if ($("storeTitles")) $("storeTitles").checked = settings.capture.store_titles;
  if ($("storeExePath")) $("storeExePath").checked = settings.capture.store_exe_path;
  if ($("trackBrowser")) $("trackBrowser").checked = settings.capture.track_browser;
  if ($("trackAudio")) $("trackAudio").checked = settings.capture.track_audio;
}

function renderRules(rules) {
  const tbody = $("rulesTable");
  if (!tbody) return;
  tbody.replaceChildren(
    ...rules.map((rule) => {
      const tr = document.createElement("tr");
      tr.append(
        cell(String(rule.id)),
        cell(rule.entity_type),
        cell(rule.pattern),
        cell(rule.action),
        actionCell(rule.id)
      );
      return tr;
    })
  );
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
  avatar.append(iconForEntity(kind, activity));
  return avatar;
}

function iconForEntity(kind, activity) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("entity-icon");
  let paths;
  if (activity === "audio") {
    paths = ["M4 14a8 8 0 0 1 16 0", "M6 14h2v6H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2Z", "M16 14h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2v-6Z"];
  } else if (kind === "domain") {
    paths = ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M3.6 9h16.8", "M3.6 15h16.8", "M12 3a13 13 0 0 1 0 18", "M12 3a13 13 0 0 0 0 18"];
  } else {
    paths = ["M4 5h16v11H4Z", "M8 20h8", "M10 16v4", "M14 16v4"];
  }
  for (const d of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function settingsFromForm() {
  return {
    api: { port: Number.parseInt($("apiPort").value, 10) },
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
    renderDashboard(state);
    if (body.restart_required?.includes("api.port")) {
      console.info("restart required for port");
    }
  } catch (error) {
    console.error(error);
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
    console.error(error);
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
    console.error(error);
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
    console.error(error);
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
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function compareEventsAsc(a, b) {
  const ta = parseDate(a.observed_at)?.getTime() ?? 0;
  const tb = parseDate(b.observed_at)?.getTime() ?? 0;
  return ta - tb || (Number(a.id || 0) - Number(b.id || 0));
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

function sumSeconds(segments) {
  return segments.reduce((sum, item) => sum + item.seconds, 0);
}

function displayEntity(event) {
  const entity = event?.entity || "";
  if (!entity) return "unknown";
  return entity;
}

function formatDuration(seconds) {
  if (seconds > 0 && seconds < 60) return "<1m";
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatHm(seconds) {
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

function formatTime(value) {
  const date = parseDate(value);
  if (!date) return value || "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(date);
}

function minutesToGo(seconds) {
  const total = Math.max(0, Math.round(seconds / 60));
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h`;
  return `${minutes}m`;
}

function hoursElapsed(now) {
  const seconds = Math.max(1, Math.round((now - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 1000));
  return Math.max(1, seconds / 3600);
}

function sinceSeconds(observed_at, now) {
  const at = parseDate(observed_at);
  if (!at) return 0;
  return Math.max(0, Math.round((now.getTime() - at.getTime()) / 1000));
}

function sinceMinutes(observed_at, now) {
  return Math.floor(sinceSeconds(observed_at, now) / 60);
}

function setBusy(busy) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = busy;
  }
}

// Navigation
function showView(view) {
  state.view = view;
  const dash = $("dashboardView");
  const settings = $("settingsView");
  if (!dash || !settings) return;
  dash.classList.toggle("active", view === "dashboard");
  dash.classList.toggle("hidden", view !== "dashboard");
  settings.classList.toggle("active", view === "settings");
  settings.classList.toggle("hidden", view !== "settings");
  for (const btn of document.querySelectorAll(".icon-rail-btn")) {
    btn.classList.toggle("active", btn.dataset.rail === view);
  }
}

for (const btn of document.querySelectorAll(".icon-rail-btn")) {
  btn.addEventListener("click", () => {
    const target = btn.dataset.rail;
    if (target === "settings") showView("settings");
    else if (target === "dashboard" || target === "activity" || target === "apps" || target === "reports") {
      showView("dashboard");
    }
  });
}

const backBtn = $("backToDashboard");
if (backBtn) backBtn.addEventListener("click", () => showView("dashboard"));

const refreshBtn = $("refreshButton");
if (refreshBtn) refreshBtn.addEventListener("click", loadAll);

const saveBtn = $("saveSettings");
if (saveBtn) saveBtn.addEventListener("click", saveSettings);

const addRuleBtn = $("addRule");
if (addRuleBtn) addRuleBtn.addEventListener("click", addRule);

const pauseBtn = $("pauseButton");
if (pauseBtn) pauseBtn.addEventListener("click", () => setTracking("/tracking/pause"));

const resumeBtn = $("resumeButton");
if (resumeBtn) resumeBtn.addEventListener("click", () => setTracking("/tracking/resume"));

// Update topbar crumb to today on first render
function setTopbarCrumb() {
  const crumb = $("topbarCrumb");
  if (!crumb) return;
  const now = new Date();
  const datestr = new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit"
  }).format(now);
  crumb.textContent = `Today · ${datestr}`;
}

setTopbarCrumb();
showView("dashboard");
loadAll();

// Lightweight auto-refresh
setInterval(loadAll, 30000);
