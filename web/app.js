const state = {
  events: [],
  settings: null,
  health: null,
  lastRefreshAt: null,
  refreshInFlight: false,
  autoRefreshTimer: null
};

const $ = (id) => document.getElementById(id);
const METRICS_AUTO_REFRESH_MS = 2500;
const SOURCE_STALE_SECONDS = 300;

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
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  try {
    const [health, events, settings] = await Promise.all([
      api("/health"),
      api("/events?limit=500&order=desc"),
      api("/settings")
    ]);
    state.health = health;
    state.events = events.events || [];
    state.settings = settings.settings;
    state.lastRefreshAt = new Date();
    const m = buildModel(state.events, state.settings, state.health);
    renderHero(m);
    renderDataGrid(m);
    renderTimeline(m);
    renderNow(m);
    renderRecentFlow(m);
    renderHealth(m);
    renderCommandBar(m);
    renderTopBar(m);
  } catch (error) {
    setStatus(error.message);
    console.error(error);
  } finally {
    state.refreshInFlight = false;
  }
}

/* ====== Model ====== */

function buildModel(events, settings, health) {
  const now = new Date();
  const todayEvents = (events || [])
    .filter((e) => isSameLocalDay(parseDate(e.observed_at), now))
    .sort(compareEventsDesc);
  const ascending = [...todayEvents].sort(compareEventsAsc);
  const idleSeconds = settings?.capture?.idle_cutoff_seconds || 300;
  const focusSegments = buildFocusSegments(ascending, idleSeconds, now);
  const audioSegments = buildAudioSegments(ascending, idleSeconds, now);
  const focusSeconds = sumSeconds(focusSegments);
  const audioSeconds = sumSeconds(audioSegments);
  const focusSwitches = focusSegments.length;
  const todayEventsCount = todayEvents.length;

  const heroNumber =
    focusSeconds >= 60
      ? formatHm(focusSeconds)
      : focusSeconds > 0
        ? `${Math.round(focusSeconds / 60)}m`
        : "0:00";

  const heroAnnotation =
    focusSeconds === 0
      ? "— waiting for activity"
      : focusSeconds < 60 * 60
        ? "— a steady start"
        : focusSeconds < 4 * 60 * 60
          ? "— a quieter day"
          : "— a deep day";

  const apps = uniqueEntities(todayEvents, "app", "windows_probe");
  const sites = uniqueEntities(todayEvents, "domain", "browser_extension");
  const heroMeta =
    focusSeconds === 0
      ? "Once activity starts, it will appear here."
      : `across ${apps} apps and ${sites} sites. ${focusSwitches} focus switches. ${Math.round(audioSeconds / 60)}m of background audio.`;

  const dataGrid = [
    {
      label: "Today focus",
      value: focusSeconds >= 60 ? formatHm(focusSeconds) : "0m",
      sub: "hours focused",
      serif: false
    },
    {
      label: "Today audio",
      value: `${Math.round(audioSeconds / 60)}m`,
      sub: "background audio",
      serif: false
    },
    {
      label: "Today switches",
      value: String(focusSwitches),
      sub: "app / tab changes",
      serif: false
    },
    {
      label: "Today events",
      value: String(todayEventsCount),
      sub: "captured events",
      serif: false
    },
    {
      label: "Top app",
      value: topEntity(todayEvents, "windows_probe"),
      sub: "longest focus",
      serif: true
    },
    {
      label: "Top site",
      value: topEntity(todayEvents, "browser_extension"),
      sub: "longest focus",
      serif: true
    },
    {
      label: "Peak",
      value: peakHourLabel(focusSegments),
      sub: "busiest hour",
      serif: false
    },
    {
      label: "Avg focus",
      value: avgFocusLabel(focusSegments),
      sub: "per session",
      serif: false
    }
  ];

  const lanes = buildAppLanes(todayEvents, focusSegments, audioSegments);

  const latestFocus = todayEvents.find(isFocusEvent) || null;
  const latestTab =
    todayEvents.find((e) => e.source === "browser_extension" && isFocusEvent(e)) ||
    null;
  const latestAudio =
    todayEvents.find((e) => isAudioStartEvent(e) || isAudioStopEvent(e)) || null;

  const recentFlow = todayEvents.slice(0, 5);

  const sources = health?.sources || {};
  const healthItems = [
    { label: "db", ok: health?.database?.exists === true },
    {
      label: sourceHealthLabel("browser", sources.browser_extension, now),
      ok: !!sources.browser_extension?.last_observed_at
    },
    {
      label: sourceHealthLabel("winprobe", sources.windows_probe, now, {
        missing: "winprobe not seen"
      }),
      ok: !!sources.windows_probe?.last_observed_at
    }
  ];

  return {
    now,
    todayEvents,
    focusSeconds,
    audioSeconds,
    focusSwitches,
    todayEventsCount,
    heroNumber,
    heroAnnotation,
    heroMeta,
    dataGrid,
    lanes,
    latestFocus,
    latestTab,
    latestAudio,
    recentFlow,
    healthItems
  };
}

/* ====== Renders ====== */

function renderHero(m) {
  $("heroNumber").textContent = m.heroNumber;
  $("heroAnnotation").textContent = m.heroAnnotation;
  $("heroMeta").textContent = m.heroMeta;
}

function renderDataGrid(m) {
  const grid = $("dataGrid");
  grid.replaceChildren();
  for (let i = 0; i < m.dataGrid.length; i += 1) {
    const tile = document.createElement("div");
    tile.className = "data-tile";

    const label = document.createElement("span");
    label.className = "data-tile-label";
    label.textContent = m.dataGrid[i].label;

    const value = document.createElement("span");
    value.className = m.dataGrid[i].serif
      ? "data-tile-value serif"
      : "data-tile-value";
    value.textContent = m.dataGrid[i].value;

    const sub = document.createElement("span");
    sub.className = "data-tile-sub";
    sub.textContent = m.dataGrid[i].sub;

    tile.append(label, value, sub);
    grid.append(tile);
  }
}

function renderTimeline(m) {
  const axis = $("timelineAxis");
  axis.replaceChildren();
  for (const t of [2, 6, 10, 14, 18, 22]) {
    const span = document.createElement("span");
    span.textContent = String(t).padStart(2, "0");
    axis.append(span);
  }
  const nowLabel = document.createElement("span");
  nowLabel.className = "now-label";
  nowLabel.textContent = "NOW";
  axis.append(nowLabel);

  const lanes = $("timelineLanes");
  lanes.replaceChildren();
  for (const lane of m.lanes) {
    lanes.append(renderTimelineLane(lane));
  }

  // Add the NOW line overlay to the last track
  const tracks = lanes.querySelectorAll(".timeline-track");
  if (tracks.length > 0) {
    const now = document.createElement("span");
    now.className = "timeline-now";
    now.style.right = "0px";
    tracks[0].append(now);
  }

  $("timelineStats").textContent =
    `${m.lanes.length} apps · ${m.todayEventsCount} events · ${m.focusSwitches} switches`;
}

function renderTimelineLane(lane) {
  const row = document.createElement("div");
  row.className = "timeline-lane";

  const label = document.createElement("div");
  label.className = "timeline-lane-label";

  const avatar = document.createElement("span");
  avatar.className = "lane-avatar";
  avatar.dataset.kind = lane.kind;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  if (lane.kind === "domain") {
    path.setAttribute("d", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M3.6 9h16.8 M3.6 15h16.8 M12 3a13 13 0 0 1 0 18 M12 3a13 13 0 0 0 0 18");
  } else {
    path.setAttribute("d", "M4 5h16v11H4Z M8 20h8 M10 16v4 M14 16v4");
  }
  svg.append(path);
  avatar.append(svg);

  const text = document.createElement("div");
  text.className = "lane-text";
  const name = document.createElement("span");
  name.className = "lane-name";
  name.textContent = lane.label;
  const dur = document.createElement("span");
  dur.className = "lane-duration";
  dur.textContent = formatDuration(lane.totalSeconds);
  text.append(name, dur);

  label.append(avatar, text);

  const track = document.createElement("div");
  track.className = "timeline-track";
  for (const bar of lane.bars) {
    const block = document.createElement("span");
    block.className = bar.audio ? "timeline-bar audio" : "timeline-bar focus";
    block.style.left = `${(bar.start / 1440) * 100}%`;
    block.style.width = `${Math.max(0.4, ((bar.end - bar.start) / 1440) * 100)}%`;
    track.append(block);
  }

  row.append(label, track);
  return row;
}

function renderNow(m) {
  const list = $("nowList");
  list.replaceChildren();
  const rows = [
    { label: "Focus app", event: m.latestFocus, fallback: "No focus" },
    { label: "Using tab", event: m.latestTab, fallback: "No browser" },
    { label: "Background audio", event: m.latestAudio, fallback: "No audio" }
  ];
  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "now-row";
    if (r.event) row.classList.add("active");

    const meta = document.createElement("span");
    meta.className = "now-row-label";
    meta.textContent = r.label;

    const value = document.createElement("div");
    value.className = "now-row-value";

    if (r.event) {
      const activity =
        r.event.payload?.activity === "audio" ? "audio" : "focus";
      value.append(
        entityAvatar(r.event.entity_type, r.event.entity, displayEntity(r.event), activity)
      );
      const text = document.createElement("div");
      const t = document.createElement("strong");
      t.textContent = displayEntity(r.event);
      const s = document.createElement("span");
      s.textContent = r.event.title || formatTime(r.event.observed_at);
      text.append(t, s);
      value.append(text);
    } else {
      const text = document.createElement("div");
      const t = document.createElement("strong");
      t.textContent = r.fallback;
      text.append(t);
      value.append(text);
    }
    row.append(meta, value);
    list.append(row);
  }
}

function renderRecentFlow(m) {
  const list = $("flowList");
  list.replaceChildren();
  for (const ev of m.recentFlow) {
    const row = document.createElement("div");
    row.className = "flow-row";
    row.append(flowCell("time flow-time", formatTime(ev.observed_at)));
    row.append(flowCell("app flow-app", displayEntity(ev)));
    row.append(flowCell("event flow-event", flowEventLabel(ev)));
    row.append(flowCell(`kind flow-kind flow-kind-${kindClass(ev)}`, kindLabel(ev)));
    list.append(row);
  }
}

function flowCell(cls, text) {
  const span = document.createElement("span");
  span.className = `flow-cell ${cls}`;
  span.textContent = text;
  return span;
}

function eventLabel(ev) {
  if (ev.payload?.activity === "audio") return "audio start";
  if (ev.kind === "app_audio_stop" || ev.kind === "tab_audio_stop") {
    return "audio stop";
  }
  if (ev.kind === "app_active" || ev.kind === "tab_active") return "started";
  return ev.kind || "event";
}

function flowEventLabel(ev) {
  const lag = receiveLagSeconds(ev);
  if (lag === null) return eventLabel(ev);
  return `${eventLabel(ev)} · receive lag ${formatCompactDuration(lag)}`;
}

function kindLabel(ev) {
  if (ev.kind === "app_active" || ev.kind === "tab_active") return "focus";
  if (typeof ev.kind === "string" && ev.kind.includes("audio")) return "audio";
  return "switch";
}

function kindClass(ev) {
  if (ev.kind === "app_active" || ev.kind === "tab_active") return "focus";
  if (typeof ev.kind === "string" && ev.kind.includes("audio")) return "audio";
  return "switch";
}

function renderHealth(m) {
  const pills = $("healthPills");
  pills.replaceChildren();
  if (state.lastRefreshAt) {
    const pill = document.createElement("span");
    pill.className = "health-pill ok";
    pill.textContent = `● ui ${formatAgeSince(state.lastRefreshAt, new Date())}`;
    pills.append(pill);
  }
  for (const h of m.healthItems) {
    const pill = document.createElement("span");
    pill.className = `health-pill ${h.ok ? "ok" : "down"}`;
    pill.textContent = `${h.ok ? "●" : "○"} ${h.label}`;
    pills.append(pill);
  }
  const blurb =
    m.focusSwitches < 30
      ? `${m.focusSwitches} switches — lowest this week`
      : `${m.focusSwitches} switches — a busy day`;
  $("healthBlurb").textContent = blurb;
}

function renderCommandBar(m) {
  const bar = $("commandBar");
  const focusText = m.focusSeconds >= 60 ? formatHm(m.focusSeconds) : "0m";
  const audioText = `${Math.round(m.audioSeconds / 60)}m`;
  const apps = uniqueEntities(m.todayEvents, "app", "windows_probe");
  const sites = uniqueEntities(m.todayEvents, "domain", "browser_extension");
  const uiText = state.lastRefreshAt
    ? ` · UI refreshed ${formatAgeSince(state.lastRefreshAt, new Date())}`
    : "";
  bar.textContent =
    `localtrace · today · focus ${focusText} · audio ${audioText} · ` +
    `${m.focusSwitches} switches · ${m.todayEventsCount} events · ` +
    `${apps} apps · ${sites} sites${uiText}`;
}

function renderTopBar(m) {
  const live = document.querySelector(".topbar .live-meta");
  if (!live) return;
  const dateText = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric"
  }).format(m.now);
  live.textContent = `TODAY · ${dateText} · LIVE`;
}

function buildAppLanes(todayEvents, focusSegments, audioSegments) {
  const byEntity = new Map();
  for (const seg of focusSegments) {
    const key = `${seg.kind}:${seg.entity}`;
    if (!byEntity.has(key)) {
      byEntity.set(key, {
        kind: seg.kind,
        entity: seg.entity,
        label: seg.label,
        totalSeconds: 0,
        bars: []
      });
    }
    const lane = byEntity.get(key);
    lane.totalSeconds += seg.seconds;
    lane.bars.push({ start: minuteOfDay(seg.start), end: minuteOfDay(seg.end), audio: false });
  }
  for (const seg of audioSegments) {
    const key = `${seg.kind}:${seg.entity}`;
    if (byEntity.has(key)) {
      byEntity.get(key).bars.push({ start: minuteOfDay(seg.start), end: minuteOfDay(seg.end), audio: true });
    }
  }
  return [...byEntity.values()]
    .sort((a, b) => b.totalSeconds - a.totalSeconds || a.label.localeCompare(b.label))
    .slice(0, 6);
}

/* ====== Helpers (kept from the previous app) ====== */

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

function isFocusEvent(event) {
  if (!event || event.kind?.endsWith("_stop")) return false;
  const activity = event.payload?.activity || "focus";
  if (activity === "audio") return false;
  return event.kind === "app_active" || event.kind === "tab_active";
}

function isAudioStartEvent(event) {
  if (!event || event.kind?.endsWith("_stop")) return false;
  return event.kind === "app_audio" || event.kind === "tab_audio";
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

function parseDate(value) {
  if (!value) return null;
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

function sourceHealthLabel(label, source, now, options = {}) {
  const observedAt = parseDate(source?.last_observed_at);
  if (!observedAt) return options.missing || `${label} not seen`;
  const ageSeconds = elapsedSeconds(observedAt, now);
  const freshness = ageSeconds > SOURCE_STALE_SECONDS ? "stale" : "fresh";
  const parts = [
    `${label} ${freshness} ${formatCompactDuration(ageSeconds)} ago`
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

function formatDuration(seconds) {
  if (seconds > 0 && seconds < 60) return "<1m";
  const totalMinutes = Math.max(0, Math.round(seconds / 60));
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function formatHm(seconds) {
  const total = Math.max(0, Math.round(seconds / 60));
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${h}:${String(m).padStart(2, "0")}`;
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

function minuteOfDay(date) {
  return date.getHours() * 60 + date.getMinutes();
}

function hashHue(input) {
  if (!input) return 0;
  let h = 0;
  for (let i = 0; i < input.length; i += 1) {
    h = (h * 31 + input.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

function iconForEntity(kind, activity) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("entity-icon");
  let paths;
  if (activity === "audio") {
    paths = [
      "M4 14a8 8 0 0 1 16 0",
      "M6 14h2v6H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2Z",
      "M16 14h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2v-6Z"
    ];
  } else if (kind === "domain") {
    paths = [
      "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
      "M3.6 9h16.8",
      "M3.6 15h16.8",
      "M12 3a13 13 0 0 1 0 18",
      "M12 3a13 13 0 0 0 0 18"
    ];
  } else {
    paths = [
      "M4 5h16v11H4Z",
      "M8 20h8",
      "M10 16v4",
      "M14 16v4"
    ];
  }
  for (const d of paths) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function entityAvatar(kind, entity, label, activity = "focus") {
  const avatar = document.createElement("span");
  avatar.className = "entity-avatar";
  avatar.dataset.kind = kind || "app";
  avatar.dataset.activity = activity;
  avatar.append(iconForEntity(kind, activity));
  return avatar;
}

/* ====== Model helpers for the data grid ====== */

function uniqueEntities(events, entityType, source) {
  const set = new Set();
  for (const e of events) {
    if (e.entity_type === entityType && e.source === source && isFocusEvent(e)) {
      set.add(e.entity);
    }
  }
  return set.size;
}

function topEntity(events, source) {
  const counts = new Map();
  for (const e of events) {
    if (e.source !== source || !isFocusEvent(e)) continue;
    counts.set(e.entity, (counts.get(e.entity) || 0) + 1);
  }
  let top = "—";
  let max = 0;
  for (const [k, v] of counts) {
    if (v > max) { top = k; max = v; }
  }
  return top;
}

function peakHourLabel(segments) {
  if (!segments.length) return "—";
  const byHour = new Array(24).fill(0);
  for (const s of segments) {
    const h = s.start.getHours();
    byHour[h] += s.seconds;
  }
  let max = 0;
  let peakH = 9;
  for (let h = 0; h < 24; h += 1) {
    if (byHour[h] > max) { max = byHour[h]; peakH = h; }
  }
  if (max === 0) return "—";
  return `${String(peakH).padStart(2, "0")}:00`;
}

function avgFocusLabel(segments) {
  if (!segments.length) return "0m";
  const total = segments.reduce((sum, s) => sum + s.seconds, 0);
  const avg = total / segments.length;
  const mins = Math.round(avg / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

/* ====== Status / busy ====== */

function setStatus(message) {
  const bar = $("commandBar");
  if (!bar) return;
  if (message) bar.textContent = `localtrace · ${message}`;
}

loadAll();
if (!state.autoRefreshTimer) {
  state.autoRefreshTimer = window.setInterval(() => {
    if (document.hidden) return;
    loadAll();
  }, METRICS_AUTO_REFRESH_MS);
}
