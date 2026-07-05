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

async function startWebUiServer({ events = [], settings = null } = {}) {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
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
      json(response, {
        ok: true,
        service: "localtrace",
        bind: { host: "127.0.0.1", port: 8765 },
        database: { path: "%LOCALAPPDATA%\\LocalTrace\\localtrace.db", exists: true },
        events: { recent_count: 0 },
        sources: {
          windows_probe: { last_observed_at: null },
          browser_extension: { last_observed_at: null }
        },
        tracking: { paused: false }
      });
      return;
    }
    if (url.pathname === "/events") {
      json(response, { ok: true, events });
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

test("dashboard and settings are separated by the rail", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.goto(server.url);

    await expect(page.locator("#dashboardView")).toBeVisible();
    await expect(page.locator("#settingsView")).toBeHidden();
    await expect(page.locator(".icon-rail")).toBeVisible();
    await expect(page.locator(".icon-rail-btn[data-rail='settings']")).toBeVisible();

    await page.locator(".icon-rail-btn[data-rail='settings']").click();

    await expect(page.locator("#settingsView")).toBeVisible();
    await expect(page.locator("#dashboardView")).toBeHidden();

    await page.locator("#backToDashboard").click();
    await expect(page.locator("#dashboardView")).toBeVisible();
    await expect(page.locator("#settingsView")).toBeHidden();
  } finally {
    await server.close();
  }
});

test("icon rail collapses nav to icons", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.goto(server.url);
    await expect(page.locator(".icon-rail")).toBeVisible();
    const railWidth = await page.locator(".icon-rail").evaluate(
      (el) => el.getBoundingClientRect().width
    );
    expect(railWidth).toBe(48);
    const iconButtons = await page.locator(".icon-rail-btn").count();
    expect(iconButtons).toBeGreaterThanOrEqual(4);
  } finally {
    await server.close();
  }
});

test("KPI tiles render with mono numbers", async ({ page }) => {
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
    await expect(page.locator(".kpi-row")).toBeVisible();
    const tiles = page.locator(".kpi-card");
    await expect(tiles).toHaveCount(4);
    const labels = await page.locator(".kpi-card .label.kpi-label").allTextContents();
    expect(labels.map((l) => l.trim().toLowerCase())).toEqual([
      "focused",
      "audio playback",
      "app switches",
      "events logged"
    ]);

    const focusNum = page.locator("#kpiFocusNum");
    await expect(focusNum).toBeVisible();
    const focusFamily = await focusNum.evaluate(
      (el) => getComputedStyle(el).fontFamily
    );
    expect(focusFamily.toLowerCase()).toContain("mono");
  } finally {
    await server.close();
  }
});

test("status bar shows last sync", async ({ page }) => {
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
    const bar = page.locator(".status-bar");
    await expect(bar).toBeVisible();
    await expect(bar).toContainText(/Updated/);
    await expect(bar).toContainText(/events?/);
    await expect(bar).toContainText(/focused/);
    const dots = await page.locator(".status-bar .dot").count();
    expect(dots).toBe(3);
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

        static now() {
          return fixedNow;
        }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    await expect(page.locator("#nowList")).toContainText("No audio activity");
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

        static now() {
          return fixedNow;
        }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    await expect(page.locator("#nowList")).toContainText("No audio activity");
    await expect(page.locator("#nowList")).not.toContainText(staleTitle);
  } finally {
    await server.close();
  }
});

test("recent flow renders latest events in descending order", async ({ page }) => {
  const server = await startWebUiServer({
    events: [
      {
        id: 1,
        observed_at: "2026-07-03T09:00:00.000Z",
        received_at: "2026-07-03T09:00:00.000Z",
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        title: "LocalTrace - Visual Studio Code",
        payload: { activity: "focus" }
      },
      {
        id: 3,
        observed_at: "2026-07-03T09:07:00.000Z",
        received_at: "2026-07-03T09:07:00.000Z",
        source: "windows_probe",
        kind: "app_audio_stop",
        entity_type: "app",
        entity: "Spotify.exe",
        title: "",
        payload: { activity: "audio", reason: "session_ended" }
      },
      {
        id: 2,
        observed_at: "2026-07-03T09:05:00.000Z",
        received_at: "2026-07-03T09:05:00.000Z",
        source: "browser_extension",
        kind: "tab_active",
        entity_type: "domain",
        entity: "docs.python.org",
        title: "datetime - Basic date and time types",
        payload: { activity: "focus", browser: "chrome" }
      },
      {
        id: 4,
        observed_at: "2026-07-03T09:09:00.000Z",
        received_at: "2026-07-03T09:09:00.000Z",
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

    const rows = page.locator("#flowBody .flow-row");
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

test("mobile dashboard has single-column bottom split", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(server.url);

    await expect(page.locator("#dashboardView")).toBeVisible();
    await expect(page.locator(".bottom-split")).toHaveCSS(
      "grid-template-columns",
      /^(?!.*\s).+$/
    );
  } finally {
    await server.close();
  }
});

test("timeline shows 24 hourly buckets", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.goto(server.url);
    await expect(page.locator("#timelineBars")).toBeVisible();
    const bars = await page.locator(".timeline-bar").count();
    expect(bars).toBe(24);
  } finally {
    await server.close();
  }
});
