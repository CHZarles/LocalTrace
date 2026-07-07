import { expect, test } from "@playwright/test";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const ROOT = path.resolve(new URL("..", import.meta.url).pathname);
const WEB_DIR = path.join(ROOT, "web");

function json(response, body) {
  response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

function valueOf(value) {
  return typeof value === "function" ? value() : value;
}

async function startWebUiServer({
  events = [],
  settings = null,
  health = null,
  delay = null,
  onRequest = null
} = {}) {
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    onRequest?.(url);
    const delayMs = delay?.(url) || 0;
    if (delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
    if (url.pathname === "/") {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end(fs.readFileSync(path.join(WEB_DIR, "index.html")));
      return;
    }
    if (url.pathname === "/web/app.js" || url.pathname === "/web/styles.css") {
      const file = path.basename(url.pathname);
      response.writeHead(200, {
        "content-type": file.endsWith(".css")
          ? "text/css; charset=utf-8"
          : "application/javascript; charset=utf-8"
      });
      response.end(fs.readFileSync(path.join(WEB_DIR, file)));
      return;
    }
    if (url.pathname === "/health") {
      json(response, valueOf(health) || {
        ok: true,
        service: "localtrace",
        bind: { host: "127.0.0.1", port: 8765 },
        database: { path: "%LOCALAPPDATA%\\LocalTrace\\localtrace.db", exists: true },
        events: { recent_count: 0 },
        sources: {
          windows_probe: { last_observed_at: null, last_received_at: null },
          browser_extension: { last_observed_at: null, last_received_at: null }
        },
        tracking: { paused: false }
      });
      return;
    }
    if (url.pathname === "/events") {
      json(response, { ok: true, events: valueOf(events) });
      return;
    }
    if (url.pathname === "/settings") {
      json(response, {
        ok: true,
        settings: settings || {
          api: { host: "127.0.0.1", port: 8765 },
          capture: {
            poll_ms: 1000,
            heartbeat_seconds: 30,
            idle_cutoff_seconds: 300,
            store_titles: false,
            store_exe_path: false,
            track_browser: true,
            track_audio: true
          }
        }
      });
      return;
    }
    if (url.pathname === "/privacy/rules") {
      json(response, { ok: true, rules: [] });
      return;
    }
    if (url.pathname === "/tracking/status") {
      json(response, { ok: true, paused: false });
      return;
    }
    response.writeHead(404, { "content-type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ ok: false, error: "not found" }));
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}/`,
    async close() {
      server.closeIdleConnections?.();
      server.closeAllConnections?.();
      await new Promise((resolve) => server.close(resolve));
    }
  };
}

test("hero number renders serif display value", async ({ page }) => {
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: new Date().toISOString(),
        received_at: new Date().toISOString(),
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        payload: { activity: "focus" }
      }
    ]
  });
  try {
    await page.goto(server.url);
    const heroNum = page.locator("#heroNumber");
    await expect(heroNum).toBeVisible();
    const family = await heroNum.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family.toLowerCase()).not.toContain("mono");
    expect(family.toLowerCase()).toContain("serif");
    const size = await heroNum.evaluate((el) => getComputedStyle(el).fontSize);
    expect(parseInt(size, 10)).toBeGreaterThanOrEqual(200);
  } finally {
    await server.close();
  }
});

test("hero eyebrow has copper underline that grows", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.goto(server.url);
    const eyebrow = page.locator(".hero-eyebrow");
    await expect(eyebrow).toBeVisible();
    const color = await eyebrow.evaluate((el) => getComputedStyle(el).color);
    // copper ~ #a8743a → rgb(168, 116, 58)
    expect(color).toBe("rgb(168, 116, 58)");
    // ::after element exists with copper background and growing underline animation
    const after = await eyebrow.evaluate((el) => {
      const s = getComputedStyle(el, "::after");
      return { bg: s.backgroundColor, anim: s.animationName, height: s.height };
    });
    expect(after.bg).toBe("rgb(168, 116, 58)");
    expect(after.height).toBe("3px");
    expect(after.anim).toContain("underline");
  } finally {
    await server.close();
  }
});

test("data grid renders 8 tiles", async ({ page }) => {
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: new Date().toISOString(),
        received_at: new Date().toISOString(),
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        payload: { activity: "focus" }
      }
    ]
  });
  try {
    await page.goto(server.url);
    const grid = page.locator("#dataGrid");
    await expect(grid).toBeVisible();
    const tiles = page.locator(".data-tile");
    await expect(tiles).toHaveCount(8);
    const labels = await page
      .locator(".data-tile-label")
      .allTextContents();
    expect(labels.map((l) => l.trim().toLowerCase())).toEqual([
      "today focus",
      "today audio",
      "today switches",
      "today events",
      "top app",
      "top site",
      "peak",
      "avg focus"
    ]);
  } finally {
    await server.close();
  }
});

test("command bar shows summary line", async ({ page }) => {
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: new Date().toISOString(),
        received_at: new Date().toISOString(),
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        payload: { activity: "focus" }
      }
    ]
  });
  try {
    await page.goto(server.url);
    const bar = page.locator("#commandBar");
    await expect(bar).toBeVisible();
    await expect(bar).toContainText(/localtrace/);
    await expect(bar).toContainText(/focus/);
    await expect(bar).toContainText(/audio/);
    await expect(bar).toContainText(/switches/);
    await expect(bar).toContainText(/events/);
    await expect(bar).toContainText(/apps/);
    await expect(bar).toContainText(/sites/);
  } finally {
    await server.close();
  }
});

test("stale browser audio is not shown as current background audio", async ({
  page
}) => {
  const staleTitle = "实用干货|今天手把手教你在..";
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: "2026-07-03T09:50:00.000Z",
        received_at: "2026-07-03T09:50:00.000Z",
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "youtube.com",
        title: staleTitle,
        payload: { activity: "audio", browser: "chrome" }
      }
    ]
  });
  try {
    await page.addInitScript(() => {
      const fixedNow = new Date("2026-07-03T10:00:00.000Z").valueOf();
      const RealDate = Date;
      class FixedDate extends RealDate {
        constructor(...args) {
          super(...(args.length ? args : [fixedNow]));
        }
        static now() { return fixedNow; }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    await expect(page.locator("#nowList")).toContainText("No audio");
    await expect(page.locator("#nowList")).not.toContainText(staleTitle);
  } finally {
    await server.close();
  }
});

test("stale browser audio is hidden even when idle cutoff is long", async ({
  page
}) => {
  const staleTitle = "实用干货|今天手把手教你在....";
  const server = await startWebUiServer({
    settings: {
      api: { host: "127.0.0.1", port: 8765 },
      capture: {
        poll_ms: 1000,
        heartbeat_seconds: 60,
        idle_cutoff_seconds: 7200,
        store_titles: false,
        store_exe_path: false,
        track_browser: true,
        track_audio: true
      }
    },
    events: [
      {
        id: 1,
        observed_at: "2026-07-03T09:05:00.000Z",
        received_at: "2026-07-03T09:05:00.000Z",
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "youtube.com",
        title: staleTitle,
        payload: { activity: "audio", browser: "chrome" }
      }
    ]
  });
  try {
    await page.addInitScript(() => {
      const fixedNow = new Date("2026-07-03T10:37:00.000Z").valueOf();
      const RealDate = Date;
      class FixedDate extends RealDate {
        constructor(...args) {
          super(...(args.length ? args : [fixedNow]));
        }
        static now() { return fixedNow; }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    await expect(page.locator("#nowList")).toContainText("No audio");
    await expect(page.locator("#nowList")).not.toContainText(staleTitle);
  } finally {
    await server.close();
  }
});

test("recent flow renders latest events in descending order", async ({ page }) => {
  // Use today's date (via addInitScript) so today's filter surfaces the events
  const today = new Date();
  function iso(offsetMs) {
    return new Date(today.getTime() - offsetMs).toISOString();
  }
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: iso(60 * 60 * 1000),
        received_at: iso(60 * 60 * 1000),
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        title: "LocalTrace - Visual Studio Code",
        payload: { activity: "focus" }
      },
      {
        id: 3,
        observed_at: iso(53 * 60 * 1000),
        received_at: iso(53 * 60 * 1000),
        source: "windows_probe",
        kind: "app_audio_stop",
        entity_type: "app",
        entity: "Spotify.exe",
        title: "",
        payload: { activity: "audio", reason: "session_ended" }
      },
      {
        id: 2,
        observed_at: iso(55 * 60 * 1000),
        received_at: iso(55 * 60 * 1000),
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "docs.python.org",
        title: "datetime - Basic date and time types",
        payload: { activity: "focus", browser: "chrome" }
      },
      {
        id: 4,
        observed_at: iso(51 * 60 * 1000),
        received_at: iso(51 * 60 * 1000),
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "youtube.com",
        title: "Live set",
        payload: { activity: "audio", browser: "chrome" }
      }
    ]
  });
  try {
    await page.goto(server.url);

    const rows = page.locator("#flowList .flow-row");
    await expect(rows).toHaveCount(4);
    const cells = await rows.allTextContents();
    expect(cells[0]).toContain("youtube.com");
    expect(cells[1]).toContain("Spotify.exe");
    expect(cells[2]).toContain("docs.python.org");
    expect(cells[3]).toContain("Code.exe");
  } finally {
    await server.close();
  }
});

test("health and recent flow expose freshness and receive lag", async ({
  page
}) => {
  const server = await startWebUiServer({
    health: {
      ok: true,
      service: "localtrace",
      bind: { host: "127.0.0.1", port: 8765 },
      database: { path: "%LOCALAPPDATA%\\LocalTrace\\localtrace.db", exists: true },
      events: { recent_count: 1 },
      sources: {
        windows_probe: { last_observed_at: null, last_received_at: null },
        browser_extension: {
          last_observed_at: "2026-07-03T09:44:00.000Z",
          last_received_at: "2026-07-03T09:46:00.000Z"
        }
      },
      tracking: { paused: false }
    },
    events: [
      {
        id: 1,
        observed_at: "2026-07-03T09:44:00.000Z",
        received_at: "2026-07-03T09:46:00.000Z",
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "docs.example",
        title: "Latency notes",
        payload: { activity: "focus", browser: "chrome" }
      }
    ]
  });
  try {
    await page.addInitScript(() => {
      const fixedNow = new Date("2026-07-03T10:00:00.000Z").valueOf();
      const RealDate = Date;
      class FixedDate extends RealDate {
        constructor(...args) {
          super(...(args.length ? args : [fixedNow]));
        }
        static now() { return fixedNow; }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    await expect(page.locator("#commandBar")).toContainText("UI refreshed <1s ago");
    await expect(page.locator("#healthPills")).toContainText("winprobe not seen");
    await expect(page.locator("#healthPills")).toContainText("browser stale 16m ago");
    await expect(page.locator("#healthPills")).toContainText("lag 2m");
    await expect(page.locator("#flowList .flow-row").first()).toContainText(
      "receive lag 2m"
    );
  } finally {
    await server.close();
  }
});

test("metrics auto-refresh updates recent flow without overlapping requests", async ({
  page
}) => {
  const eventState = [];
  let eventRequests = 0;
  let eventDelayMs = 0;
  const server = await startWebUiServer({
    events: () => eventState,
    delay: (url) => (url.pathname === "/events" ? eventDelayMs : 0),
    onRequest: (url) => {
      if (url.pathname === "/events") eventRequests += 1;
    }
  });
  try {
    await page.goto(server.url);
    await expect(page.locator("#flowList .flow-row")).toHaveCount(0);

    eventState.push({
      id: 1,
      observed_at: new Date().toISOString(),
      received_at: new Date().toISOString(),
      source: "windows_probe",
      kind: "app_active",
      entity_type: "app",
      entity: "Code.exe",
      title: "LocalTrace",
      payload: { activity: "focus" }
    });

    await expect(page.locator("#flowList .flow-row").first()).toContainText(
      "Code.exe",
      { timeout: 4000 }
    );

    eventRequests = 0;
    eventDelayMs = 3200;
    await page.waitForTimeout(3000);
    expect(eventRequests).toBe(1);
  } finally {
    eventDelayMs = 0;
    await server.close();
  }
});

test("mobile dashboard has single-column bottom split", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(server.url);

    await expect(page.locator(".bottom-row")).toBeVisible();
    await expect(page.locator(".bottom-row")).toHaveCSS(
      "grid-template-columns",
      /^(?!.*\s).+$/
    );
  } finally {
    await server.close();
  }
});

test("timeline shows three lanes (focus / audio / events)", async ({ page }) => {
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: "2026-07-05T09:00:00.000Z",
        received_at: "2026-07-05T09:00:00.000Z",
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        title: "VS Code",
        payload: { activity: "focus" }
      },
      {
        id: 2,
        observed_at: "2026-07-05T10:00:00.000Z",
        received_at: "2026-07-05T10:00:00.000Z",
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        payload: { activity: "focus" }
      },
      {
        id: 3,
        observed_at: "2026-07-05T11:00:00.000Z",
        received_at: "2026-07-05T11:00:00.000Z",
        source: "browser_extension",
        kind: "tab_audio",
        entity_type: "domain",
        entity: "youtube.com",
        title: "Live set",
        payload: { activity: "audio", browser: "chrome" }
      }
    ]
  });
  try {
    await page.addInitScript(() => {
      const fixedNow = new Date("2026-07-05T12:00:00.000Z").valueOf();
      const RealDate = Date;
      class FixedDate extends RealDate {
        constructor(...args) {
          super(...(args.length ? args : [fixedNow]));
        }
        static now() { return fixedNow; }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    const lanes = page.locator("#timelineLanes .timeline-lane");
    await expect(lanes).toHaveCount(3);
    // lane 1: Focus, lane 2: Audio, lane 3: Events
    const labels = await lanes.locator(".timeline-lane-label").allTextContents();
    expect(labels.map((l) => l.trim().toLowerCase())).toEqual(["focus", "audio", "events"]);
    // Focus lane has 2 focus bars (the two app_active events)
    await expect(lanes.nth(0).locator(".timeline-bar-focus")).toHaveCount(2);
    // Audio lane has 1 audio bar
    await expect(lanes.nth(1).locator(".timeline-bar-audio")).toHaveCount(1);
  } finally {
    await server.close();
  }
});
