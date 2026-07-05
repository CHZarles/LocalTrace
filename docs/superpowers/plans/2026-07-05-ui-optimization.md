# Editorial Web UI Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Web UI's two-card hero with a single editorial hero (#hero) and demote secondary sections, keeping all data flow and Settings behaviour unchanged.

**Architecture:** Token-driven CSS overhaul (no JS data model changes). Two structural DOM moves — `now-card` → `#rightNow` (side stack top), `summary-card` → `#hero` (above workbench). One new render function `renderHero(model)` that derives a headline from existing `model.focusSeconds / audioSeconds / focusSwitches / todayEvents.length`. Playwright tests guard DOM shape, mobile downsizing, and serif headline.

**Tech Stack:** Vanilla JS (`web/app.js`), CSS with custom properties (`web/styles.css`), Playwright (`tests/web-ui-pages.spec.mjs`), pytest (`tests/test_http_api.py`).

**User Verification:** YES — the implementation is visual; after task 5 a final task asks the user to confirm the result before declaring done.

---

## File Structure

| File | Responsibility | Touched in |
|---|---|---|
| `web/styles.css` | Token palette + serif stack + hero rhythm + demote secondary cards + Settings retune | Tasks 1, 3, 4 |
| `web/index.html` | Markup for `#hero`, `#rightNow`; remove old `now-card` / `summary-card` | Tasks 2, 3 |
| `web/app.js` | New `renderHero(model)`, `renderRightNow(model)`; derive `model.headline` in `buildTodayModel` | Tasks 2, 3 |
| `tests/web-ui-pages.spec.mjs` | Update existing assertions; add serif + mobile tests | Task 5 |
| `tests/test_http_api.py` | Update markup substring assertions for new DOM ids | Task 5 |

No new files. No backend / extension / Python source code changes.

---

## Task 1: Tokens + secondary card demotion

**Goal:** Replace palette, add serif + hero-rhythm tokens, drop shadows, soften borders, and visually demote Timeline / Recent flow / Today Top / Health cards.

**Files:**

- Modify: `web/styles.css`

**Acceptance Criteria:**

- [ ] `--bg0` resolves to `#fbfaf7`, `--text2` to `#7a7066`, `--border0` to `#ebe4d4`, `--shadow` to `none`.
- [ ] `--serif` and `--hero1..5` tokens exist.
- [ ] `.card` no longer carries a shadow.
- [ ] `.timeline-card`, `.flow-item`, `.top-item` have smaller padding / row height / numeric sizes per spec table.
- [ ] `.now-row` (right-now row component) does not change here; will be retuned in Task 2.

**Verify:** `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs` — existing tests still pass.

**Steps:**

- [ ] **Step 1: Update `:root` token block**

In `web/styles.css`, replace the `:root` block (lines 1–28) with:

```css
:root {
  color-scheme: light;
  --bg0: #fbfaf7;
  --bg1: #f6f3ec;
  --surface0: #fbfaf7;
  --surface1: #f2eee5;
  --surface2: #ebe4d4;
  --border0: #ebe4d4;
  --text0: #1a1a1a;
  --text1: #3b3530;
  --text2: #7a7066;
  --accent0: #1b5fd6;
  --accent1: #15469a;
  --accentContainer: #dfe8f6;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #38bdf8;
  --serif: ui-serif, Georgia, "Source Serif Pro", serif;
  --hero1: 14px;
  --hero2: 28px;
  --hero3: 40px;
  --hero4: 56px;
  --hero5: 80px;
  --radiusS: 8px;
  --radiusM: 12px;
  --space1: 4px;
  --space2: 8px;
  --space3: 12px;
  --space4: 16px;
  --space5: 20px;
  --space6: 24px;
  --shadow: none;
}
```

- [ ] **Step 2: Drop card shadow**

In `.card` (line ~302), remove `--shadow` reference so it reads:

```css
.card {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border0);
  border-radius: var(--radiusM);
  background: var(--surface0);
}
```

- [ ] **Step 3: Demote numeric sizes in `.metric-grid`**

In `.metric-grid strong` (line ~422), change the `font-size` from `24px` to `16px`:

```css
.metric-grid strong {
  display: block;
  margin-top: var(--space1);
  font-size: 16px;
  line-height: 22px;
}
```

- [ ] **Step 4: Demote timeline bar height**

In `.timeline-bar` (line ~626), change `top` to `22px` and `height` to `12px`:

```css
.timeline-bar {
  position: absolute;
  top: 22px;
  min-width: 3px;
  height: 12px;
  border-radius: 999px;
}
```

In `.timeline-row` (line ~603), change `min-height` to `44px`:

```css
.timeline-row {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 44px;
}
```

In `.timeline-track` (line ~617), change `min-height` to `44px`.

- [ ] **Step 5: Demote flow-item + top-item**

In `.flow-item` (line ~648), change `min-height` to `48px` and `padding` to `var(--space3) var(--space3)`.

In `.top-item` (line ~455), change `min-height` to `48px`.

- [ ] **Step 6: Add caps-tag utility (used in Tasks 2/3/4)**

Append at end of `web/styles.css`:

```css
.caps-tag {
  display: block;
  color: var(--text2);
  font: 600 11px/1 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
```

- [ ] **Step 7: Run Playwright to confirm nothing regressed**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: 6 tests pass (no DOM changes yet; visual regression not asserted).

- [ ] **Step 8: Commit**

```bash
git add web/styles.css
git commit -m "style: editorial tokens + demote secondary cards

- warm off-white palette, paper hairline borders, no card shadows
- new --serif and --hero1..5 tokens for the upcoming hero block
- .card padding 18 -> 14, .timeline-bar height 18 -> 12,
  .timeline-row/.flow-item/.top-item min-height -> 44-48
- .metric-grid strong 24 -> 16 to defer visual weight to the new hero
- add .caps-tag utility for caps eyebrows / labels"
```

```json:metadata
{"files": ["web/styles.css"], "verifyCommand": "node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs", "acceptanceCriteria": ["palette swapped", "serif/hero tokens present", "no card shadow", "secondary card sizes per spec"], "requiresUserVerification": false}
```

---

## Task 2: Right-now card

**Goal:** Replace `.now-card` (which currently sits in `.hero-grid`) with a `#rightNow` block at the top of `.side-stack`. Drop the 3-row split into one card with simpler rows + footer.

**Files:**

- Modify: `web/index.html`
- Modify: `web/app.js`

**Acceptance Criteria:**

- [ ] `index.html` no longer contains `class="now-card"` or `#nowFocus #nowTab #nowAudio` rows.
- [ ] `index.html` contains `<aside class="card right-now" id="rightNow">`.
- [ ] `app.js` has `renderRightNow(model)` that renders 3 rows + footer.
- [ ] Playwright: stale-audio tests still pass against `#rightNow` (or `#nowAudio`-equivalent assertion updated to rightNow's data-testid).

**Verify:** `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs` — 8 tests pass (6 existing + 2 audio-stale tests rewritten to target `#rightNow`).

**Steps:**

- [ ] **Step 1: Update existing audio-stale Playwright tests**

In `tests/web-ui-pages.spec.mjs`, update the two audio-stale tests. In both, change the assertion from `#nowAudio` to `#rightNow`:

```js
await expect(page.locator("#rightNow")).toContainText("No audio activity");
await expect(page.locator("#rightNow")).not.toContainText(staleTitle);
```

- [ ] **Step 2: Run tests; expect 2 failures with `#nowAudio` not found**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: 2 failures: "no element #nowAudio".

- [ ] **Step 3: Restructure markup in `web/index.html`**

In `web/index.html`:

Replace the `<section id="metricsView" class="view active">` opening + the entire `.hero-grid > (.now-card + .summary-card)` block with:

```html
<section id="metricsView" class="view active">
  <article id="hero" class="card hero-block">
    <!-- populated by renderHero -->
  </article>

  <div class="workbench-grid">
    <div class="main-stack">
```

Then above the existing `<aside class="side-stack">`, insert a placeholder for the Right-now block by adding this to the top of `.side-stack`:

```html
      <article class="card right-now" id="rightNow">
        <!-- populated by renderRightNow -->
      </article>
```

(Do not yet wire JS — that happens in step 4.)

- [ ] **Step 4: Re-run; expect audio-stale tests to fail with `#rightNow` empty**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: 2 audio-stale tests fail with `#rightNow contains "No audio activity"` matching "". (Because rightNow is empty until JS runs.)

- [ ] **Step 5: Add `renderRightNow(model)` and call it**

In `web/app.js`, replace `renderNow(model)` (lines ~238–257) with:

```js
function renderNow(model) {
  renderRightNow(model);
}

function renderRightNow(model) {
  const root = $("rightNow");
  if (!root) return;
  const rows = [
    { label: "Focus app", event: model.latestFocus, fallback: "No focus activity" },
    { label: "Using tab", event: model.latestTab, fallback: "No browser activity" },
    {
      label: "Background audio",
      event: model.latestAudio,
      fallback: "No audio activity"
    }
  ];

  const list = document.createElement("div");
  list.className = "right-now-list";
  for (const row of rows) list.append(rightNowRow(row));

  const footer = document.createElement("p");
  footer.className = "right-now-footer";
  const latestAt =
    model.latestAudio?.observed_at ||
    model.latestTab?.observed_at ||
    model.latestFocus?.observed_at;
  footer.textContent = latestAt ? `Updated ${formatTime(latestAt)}` : "Waiting for activity";

  root.replaceChildren(
    sectionHeading("Right now"),
    list,
    footer
  );
}

function rightNowRow({ label, event, fallback }) {
  const row = document.createElement("div");
  row.className = "right-now-row";
  const meta = document.createElement("span");
  meta.className = "caps-tag";
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
  row.append(meta, value);
  return row;
}

function sectionHeading(title) {
  const h = document.createElement("h3");
  h.className = "caps-tag";
  h.textContent = title;
  return h;
}
```

Wire it into `renderToday()`:

```js
function renderToday() {
  const model = buildTodayModel(state.events, state.settings);
  renderRightNow(model);
  renderSummary(model);
  renderTop(model);
  renderTimeline(model);
}
```

- [ ] **Step 6: Add right-now styles**

Append to `web/styles.css`:

```css
.right-now {
  padding: var(--space4);
}

.right-now-list {
  display: grid;
  gap: var(--space3);
  margin-top: var(--space3);
}

.right-now-row {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  align-items: start;
  gap: var(--space2);
  min-width: 0;
  min-height: 64px;
  padding: var(--space3);
  border: 1px solid var(--border0);
  border-radius: var(--radiusM);
  background: var(--surface1);
}

.right-now-footer {
  margin-top: var(--space3);
  padding-top: var(--space3);
  border-top: 1px solid var(--border0);
  color: var(--text2);
  font-size: 12px;
}

.right-now-row .entity-avatar {
  width: 24px;
  height: 24px;
  border-radius: 6px;
}

.right-now-row .entity-avatar[data-kind="domain"] {
  border-radius: 999px;
}

.right-now-row .entity-icon {
  width: 14px;
  height: 14px;
}
```

- [ ] **Step 7: Run Playwright; expect all 6 tests to pass**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: all 6 pass.

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/app.js web/styles.css tests/web-ui-pages.spec.mjs
git commit -m "refactor: move now-card out of hero into right-now block

- rightNow lives at the top of the side stack, demoted weight
- rightNow rows use a 24px avatar + caps-tag labels
- now-card + summary-card removed from .hero-grid
- update two audio-stale Playwright tests to assert #rightNow"
```

```json:metadata
{"files": ["web/index.html", "web/app.js", "web/styles.css", "tests/web-ui-pages.spec.mjs"], "verifyCommand": "node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs", "acceptanceCriteria": ["now-card removed", "rightNow wired", "audio-stale tests pass"], "requiresUserVerification": false}
```

---

## Task 3: Editorial hero block

**Goal:** Replace `.hero-grid` body with `#hero` populated from a new `renderHero(model)` showing eyebrow / serif headline / sub / 4 inline numerals. Mobile-downsizing responsive. Widen side rail.

**Files:**

- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/styles.css`

**Acceptance Criteria:**

- [ ] `#hero` exists in `web/index.html` and is populated on load.
- [ ] Headline uses serif (computed `font-family` includes `serif`).
- [ ] 4 numerals row visible: FOCUS / AUDIO / SWITCHES / EVENTS with non-empty values (when data present).
- [ ] At ≤ 700px viewport, hero h1 font-size is ≤ 32px.
- [ ] `.workbench-grid` columns changed to `1.4fr / 1fr`.

**Verify:** `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs` — all 8 tests pass (6 existing + 2 new).

**Steps:**

- [ ] **Step 1: Add failing Playwright test for hero**

Append to `tests/web-ui-pages.spec.mjs`:

```js
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
    await expect(numerals).toHaveText(/Focus/i);
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
```

- [ ] **Step 2: Run; expect new tests to fail with `#hero` empty**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs -g "hero"`
Expected: 2 failures.

- [ ] **Step 3: Widen side rail**

In `web/styles.css`, change `.workbench-grid` (line ~289):

```css
.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr);
  gap: var(--space4);
  align-items: start;
}
```

- [ ] **Step 4: Add hero styles**

Append to `web/styles.css`:

```css
.hero-block {
  padding: var(--hero4) var(--hero4) var(--hero3);
  border-radius: 0;
  border-left: 0;
  border-right: 0;
  background: var(--bg0);
}

.hero-eyebrow {
  display: block;
  margin: 0 0 var(--hero2);
  color: var(--text2);
  font: 700 11px/1 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero-headline {
  margin: 0 0 var(--hero2);
  color: var(--text0);
  font: 300 64px/0.95 var(--serif);
  letter-spacing: -0.02em;
  max-width: 16ch;
}

.hero-sub {
  margin: 0 0 var(--hero3);
  color: var(--text2);
  font: 400 14px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  max-width: 60ch;
}

.hero-sub em {
  font-style: italic;
  color: var(--text1);
}

.hero-numerals {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--hero3);
  margin: 0;
  padding: var(--hero2) 0 0;
  border-top: 1px solid var(--border0);
}

.hero-numerals div {
  min-width: 0;
  padding-top: var(--space2);
}

.hero-numerals dt {
  margin: 0 0 var(--space2);
  color: var(--text2);
  font: 700 10px/1 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero-numerals dd {
  margin: 0;
  color: var(--text0);
  font: 500 22px/1.1 var(--serif);
}

@media (max-width: 980px) {
  .hero-block {
    padding: var(--hero3) var(--space4);
  }
  .hero-headline {
    font-size: 44px;
  }
}

@media (max-width: 700px) {
  .hero-eyebrow { display: none; }
  .hero-headline {
    font-size: 32px;
  }
  .hero-numerals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
```

- [ ] **Step 5: Wire `renderHero` and `model.headline`**

In `web/app.js`:

Add at end of `buildTodayModel` (before the `return`):

```js
  const headline = buildHeadline(model);
```

(where `model` is `const { now, todayEvents, focusSegments, audioSegments, segments, topItems, latestFocus, latestTab, latestAudio, focusSeconds, audioSeconds, focusSwitches }`.) Insert `headline` into the returned object:

```js
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
    focusSwitches: focusSegments.length,
    headline
  };
```

Then add (above `function buildTodayModel`):

```js
function buildHeadline(model) {
  const focus = model.focusSeconds || 0;
  const audio = model.audioSeconds || 0;
  const switches = model.focusSwitches || 0;
  const events = (model.todayEvents || []).length;
  const fmt = (sec) => {
    if (sec < 60) return `${sec}s`;
    const total = Math.round(sec / 60);
    if (total < 60) return `${total}m`;
    const h = Math.floor(total / 60);
    const m = total % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  };
  const focusLabel = focus >= 3600
    ? fmt(focus)
    : focus >= 60
      ? fmt(focus)
      : "";
  const sentence =
    focus >= 3600
      ? `Today, you focused ${fmt(focus)}.`
      : focus >= 60
        ? `Today so far — ${fmt(focus)} focused.`
        : "Nothing tracked yet today.";
  const tallyApps = new Set(
    (model.todayEvents || [])
      .filter(isFocusEvent)
      .map((e) => `${e.source}:${e.entity}`)
  );
  const tallySites = new Set(
    (model.todayEvents || [])
      .filter((e) => e.source === "browser_extension" && isFocusEvent(e))
      .map((e) => e.entity)
  );
  const sub = focus <= 0
    ? "Once activity starts, it will appear here."
    : `across ${tallyApps.size} apps and ${tallySites.size} sites. ${switches} focus switches. ${fmt(audio)} of background audio. — a quieter day.`;

  const date = new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit"
  }).format(model.now).replace(/[^0-9]/g, (m, i, s) => i === 4 ? "." : i === 7 ? "." : m);

  const numerals = [
    { tag: "Focus", value: focusLabel || "—" },
    ...(audio > 0 ? [{ tag: "Audio", value: fmt(audio) }] : []),
    { tag: "Switches", value: String(switches) },
    { tag: "Events", value: String(events) }
  ];
  // Ensure at least 4 (or pad by repeating 'Events' = 0)
  while (numerals.length < 4) numerals.push({ tag: "Events", value: "0" });

  return { eyebrow: `LOCALTRACE · ${date}`, sentence, sub, numerals };
}
```

Note the date formatter is intentionally hand-built: it produces `YYYY.MM.DD` from "numeric" `YYYY/MM/DD`. If `Intl` returns a different locale form, the eye test will catch it and we'll fix inline.

Add `renderHero`:

```js
function renderHero(model) {
  const root = $("hero");
  if (!root) return;
  const h = model.headline || {
    eyebrow: "LOCALTRACE",
    sentence: model.focusSeconds >= 3600 ? "Today, you focused." : "Nothing tracked yet today.",
    sub: "",
    numerals: [
      { tag: "Focus", value: "—" },
      { tag: "Switches", value: "0" },
      { tag: "Events", value: "0" },
      { tag: "Events", value: "0" }
    ]
  };
  const eyebrow = document.createElement("p");
  eyebrow.className = "hero-eyebrow";
  eyebrow.textContent = h.eyebrow;
  const headline = document.createElement("h1");
  headline.className = "hero-headline";
  headline.textContent = h.sentence;
  const sub = document.createElement("p");
  sub.className = "hero-sub";
  const [plain, tail] = h.sub.split("—");
  sub.append(document.createTextNode(plain.trim() + " "));
  if (tail) {
    const em = document.createElement("em");
    em.textContent = "— " + tail.trim();
    sub.append(em);
  }
  const numerals = document.createElement("dl");
  numerals.className = "hero-numerals";
  for (const item of h.numerals) {
    const cell = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = item.tag;
    dd.textContent = item.value;
    cell.append(dt, dd);
    numerals.append(cell);
  }
  root.replaceChildren(eyebrow, headline, sub, numerals);
}
```

Wire into `renderToday`:

```js
function renderToday() {
  const model = buildTodayModel(state.events, state.settings);
  renderHero(model);
  renderRightNow(model);
  renderSummary(model);
  renderTop(model);
  renderTimeline(model);
}
```

- [ ] **Step 6: Run Playwright; expect all 8 tests pass**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add web/app.js web/styles.css tests/web-ui-pages.spec.mjs
git commit -m "feat: editorial hero block with serif headline

- #hero replaces the previous two-card hero grid; sits above
  the workbench grid at full width
- headline = 'Today, you focused Xh Ym.' for >=1h, ...so far - Xm
  for >=1m, 'Nothing tracked yet today.' otherwise
- 4-cell numeric row with FOCUS / AUDIO / SWITCHES / EVENTS
- serif type stack (ui-serif, Georgia, Source Serif Pro), no web fonts
- responsive: 64px -> 44px at <=980px, 32px + 2-col numerals at <=700px
- widen side rail 1.65/0.9 -> 1.4/1 so right-now card breathes"
```

```json:metadata
{"files": ["web/app.js", "web/styles.css", "tests/web-ui-pages.spec.mjs"], "verifyCommand": "node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs", "acceptanceCriteria": ["hero renders serif headline", "4-cell numerals row present", "mobile downsizes <=32px", "workbench columns 1.4/1"], "requiresUserVerification": false}
```

---

## Task 4: Settings visual treatment

**Goal:** Inherit new tokens (warm palette, paper hairlines). Caps-tag label style. Retune `.toggle` to new palette. No markup or behaviour changes.

**Files:**

- Modify: `web/styles.css`

**Acceptance Criteria:**

- [ ] `<label><span>` in settings form renders in caps-tag style (computed `text-transform: uppercase`, `letter-spacing > 0`).
- [ ] `.toggle` uses new surface colors and respects toggle background, but has the same behaviour.
- [ ] Settings tests still pass (no behaviour assertions affected).

**Verify:** `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs` — all 8 still pass (none of these tests inspect label caps; they assert visibility & section separation only).

**Steps:**

- [ ] **Step 1: Update `label span` rule**

In `web/styles.css`, replace the existing `label span` rule (line ~799):

```css
label span {
  display: block;
  margin-bottom: var(--space1);
  color: var(--text2);
  font: 600 11px/1 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
```

- [ ] **Step 2: Retune `.toggle`**

Replace the `.toggle` and `.toggle input` rules (lines ~806–825):

```css
.toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space3);
  min-height: 38px;
  padding: 0 var(--space3);
  border: 1px solid var(--border0);
  border-radius: var(--radiusM);
  background: var(--surface1);
  color: var(--text0);
}

.toggle span {
  margin: 0;
}

.toggle input {
  width: 18px;
  height: 18px;
  accent-color: var(--accent0);
}
```

- [ ] **Step 3: Pull settings panel spacing tighter**

In `.settings-grid` and `.rule-form` already use `var(--space3)`. Add a small top gap between cards:

```css
.settings-layout {
  display: grid;
  gap: var(--space4);
}
```

(Already exists at line ~755; verify it still uses `var(--space4)`. If so, skip this step.)

- [ ] **Step 4: Run tests; expect all 8 still pass**

Run: `node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs`
Expected: 8 pass.

- [ ] **Step 5: Commit**

```bash
git add web/styles.css
git commit -m "style: editorial tokens propagate to Settings

- label <span> now uses caps-tag style (11px, 0.06em letter-spacing)
- .toggle uses surface1 background and accent0 checkbox colour
- no markup or behaviour change"
```

```json:metadata
{"files": ["web/styles.css"], "verifyCommand": "node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs", "acceptanceCriteria": ["label caps style applied", "toggle palette retuned", "no markup change"], "requiresUserVerification": false}
```

---

## Task 5: Update HTTP API tests + verify with user

**Goal:** Update `tests/test_http_api.py` substring assertions to match new DOM. Add a final user verification checkpoint confirming the visual result.

**Files:**

- Modify: `tests/test_http_api.py`

**Acceptance Criteria:**

- [ ] `pytest tests/test_http_api.py` passes.
- [ ] `pytest tests/` (entire suite) passes.
- [ ] User confirms the visual result matches the editorial direction (or requests iteration).

**Verify:** `.venv/bin/python -m pytest tests/ -x --tb=short` passes; user confirms via AskUserQuestion.

**Steps:**

- [ ] **Step 1: Update `test_http_routes_expose_web_settings_and_local_json_apis`**

In `tests/test_http_api.py`, in the function `test_http_routes_expose_web_settings_and_local_json_apis`, locate the block (line ~320) with `assert "Recent flow" in html` and `assert "flowList" in html`. Replace those two assertions with:

```python
        assert 'id="hero"' in html
        assert 'id="rightNow"' in html
        assert "flow-list" in html
```

Also locate the assertion block with `assert "renderToday" in script` (around line ~347) and add:

```python
        assert "renderHero" in script
        assert "renderRightNow" in script
```

And in the styles assertion block (around line ~360) keep `.timeline-grid`, but also add:

```python
        assert ".hero-block" in styles
        assert ".hero-headline" in styles
```

- [ ] **Step 2: Run pytest; expect passing**

Run: `.venv/bin/python -m pytest tests/test_http_api.py -x --tb=short`
Expected: all 22 tests pass.

- [ ] **Step 3: Run full pytest suite**

Run: `.venv/bin/python -m pytest tests/ --ignore=tests/web-ui-pages.spec.mjs -x --tb=short`
Expected: 80 tests pass (58 config + 22 http_api + skill_scripts).

- [ ] **Step 4: Run Playwright + node:test for completeness**

Run:

```bash
node_modules/.bin/playwright test tests/web-ui-pages.spec.mjs && \
  node --test extension/service_worker.test.mjs
```

Expected: 8 Playwright + 2 node tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_http_api.py
git commit -m "test: align http API assertions with editorial hero DOM

- assert 'id=hero' and 'id=rightNow' instead of recent-flow labels
- assert renderHero + renderRightNow in client script
- assert hero CSS (.hero-block, .hero-headline) in styles"
```

- [ ] **Step 6: Ask user to verify visual result**

Run the LocalTrace web UI locally and ask the user to open it. Then call:

```yaml
AskUserQuestion:
  question: "Web UI changes are implemented. Open 127.0.0.1:8765 (or restart the service) and confirm — does it match the editorial direction we discussed (one serif hero + demoted secondary cards)?"
  header: "Verify"
  options:
    - label: "Looks right, ship it"
      description: "Editorial direction reads correctly; merge as-is"
    - label: "Needs iteration"
      description: "Something doesn't feel right — describe what to change"
```

**If the user selects "Needs iteration":** the task is NOT complete. Investigate, push a follow-up commit on the same branch, and re-verify.

```json:metadata
{"files": ["tests/test_http_api.py"], "verifyCommand": ".venv/bin/python -m pytest tests/ --ignore=tests/web-ui-pages.spec.mjs -x --tb=short", "acceptanceCriteria": ["http_api tests pass", "full pytest passes", "Playwright + node tests pass", "user confirms visual result"], "requiresUserVerification": true, "userVerificationPrompt": "Open the LocalTrace Web UI and confirm the editorial direction reads correctly (one serif hero + demoted secondary cards)?"}
```

---

## Open Questions

None at plan time. The hand-built `YYYY.MM.DD` formatter in `buildHeadline` is a known risk — if a locale returns a non-numeric format, the eyebrow will look wrong; a 5-minute fix lands inline in Task 3 if discovered during execution.
