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

test("metrics and settings are separate pages", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.goto(server.url);

    await expect(page.locator("#metricsView")).toBeVisible();
    await expect(page.locator("#settingsPanel")).toBeHidden();
    await expect(page.locator("#metricsView #healthMetrics")).toHaveCount(1);

    await page.getByRole("button", { name: "Settings" }).click();

    await expect(page.locator("#settingsPanel")).toBeVisible();
    await expect(page.locator("#metricsView")).toBeHidden();
    await expect(page.locator("#settingsPanel #healthMetrics")).toHaveCount(0);
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

    await expect(page.locator("#rightNow")).toContainText("No audio activity");
    await expect(page.locator("#rightNow")).not.toContainText(staleTitle);
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

    await expect(page.locator("#rightNow")).toContainText("No audio activity");
    await expect(page.locator("#rightNow")).not.toContainText(staleTitle);
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

    const rows = page.locator("#flowList .flow-item");
    await expect(rows).toHaveCount(4);
    await expect(rows.nth(0)).toContainText("youtube.com");
    await expect(rows.nth(0)).toContainText("Tab audio");
    await expect(rows.nth(1)).toContainText("Spotify.exe");
    await expect(rows.nth(1)).toContainText("Audio stopped");
    await expect(rows.nth(1)).toContainText("windows_probe");
    await expect(rows.nth(2)).toContainText("docs.python.org");
    await expect(rows.nth(3)).toContainText("Code.exe");
  } finally {
    await server.close();
  }
});

test("mobile metrics use a single-column layout", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(server.url);

    await expect(page.locator("#metricsView")).toBeVisible();
    await expect(page.locator(".right-now-list")).toHaveCSS(
      "grid-template-columns",
      /^(?!.*\s).+$/
    );
    await expect(page.locator(".workbench-grid")).toHaveCSS(
      "grid-template-columns",
      /^(?!.*\s).+$/
    );
  } finally {
    await server.close();
  }
});

test("mobile timeline keeps axis labels readable", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(server.url);

    await expect(page.locator("#metricsView")).toBeVisible();
    const hasOverlap = await page.locator(".timeline-axis span").evaluateAll(
      (ticks) => ticks.some((tick, index) => {
        if (index === 0) return false;
        const previous = ticks[index - 1].getBoundingClientRect();
        const current = tick.getBoundingClientRect();
        return current.left < previous.right + 2;
      })
    );
    expect(hasOverlap).toBe(false);
  } finally {
    await server.close();
  }
});

test("hero renders serif headline and inline numerals", async ({ page }) => {
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
        title: "LocalTrace",
        payload: { activity: "focus" }
      },
      {
        id: 2,
        observed_at: "2026-07-03T10:00:00.000Z",
        received_at: "2026-07-03T10:00:00.000Z",
        source: "windows_probe",
        kind: "app_active",
        entity_type: "app",
        entity: "Code.exe",
        payload: { activity: "focus" }
      }
    ]
  });
  try {
    await page.addInitScript(() => {
      const fixedNow = new Date("2026-07-03T17:00:00.000Z").valueOf();
      const RealDate = Date;
      class FixedDate extends RealDate {
        constructor(...args) { super(...(args.length ? args : [fixedNow])); }
        static now() { return fixedNow; }
      }
      FixedDate.UTC = RealDate.UTC;
      FixedDate.parse = RealDate.parse;
      globalThis.Date = FixedDate;
    });
    await page.goto(server.url);

    const hero = page.locator("#hero");
    await expect(hero).toBeVisible();
    const heroH1 = hero.locator("h1");
    await expect(heroH1).toBeVisible();
    const headline = (await heroH1.textContent()).trim();
    expect(headline.length).toBeGreaterThan(0);
    const family = await heroH1.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family.toLowerCase()).toContain("serif");

    await expect(hero.locator(".hero-numerals")).toHaveCount(1);
    const numerals = hero.locator(".hero-numerals dt");
    await expect(numerals.first()).toHaveText(/Focus/i);
    const numeralTexts = await numerals.allTextContents();
    expect(numeralTexts.length).toBe(4);
    expect(numeralTexts.map((t) => t.trim().toLowerCase())).toEqual(
      expect.arrayContaining(["focus", "events"])
    );
  } finally {
    await server.close();
  }
});

test("mobile hero downsizes below 700px", async ({ page }) => {
  const server = await startWebUiServer();
  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(server.url);

    const hero = page.locator("#hero");
    await expect(hero).toBeVisible();
    const heroH1 = hero.locator("h1");
    const heroSize = await heroH1.evaluate((el) =>
      parseFloat(getComputedStyle(el).fontSize)
    );
    expect(heroSize).toBeLessThanOrEqual(32);
  } finally {
    await server.close();
  }
});
