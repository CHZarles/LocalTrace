# Web UI Optimization — Editorial Design

**Date:** 2026-07-05
**Status:** Approved (brainstorming complete)
**Scope:** `web/` only (no backend / extension / skill changes)

## Background

The current Web UI renders every section as the same white card with a soft
gradient. There is no visual difference between a primary metric and a
secondary list. The design feels repetitive and lacks hierarchy. This spec
applies an **editorial / magazine** treatment: a single serif hero with an
inline metrics row, with secondary sections visually demoted so the hero
reads as the page's anchor.

## Goals

1. Establish a clear primary → secondary → tertiary hierarchy.
2. Introduce a serif headline + caps-tag rhythm without shipping web fonts.
3. Replace the "Now" / "Today summary" two-card hero with a single editorial
   hero block ("Today, you focused 4h 12m.").
4. Keep data model, API contracts, and Settings functionality unchanged.

## Non-Goals

- Dark mode.
- Empty / loading / error state redesign.
- Browser extension popup rework.
- Touching backend (`apps/`), Python tests of HTTP routes beyond markup
  substring assertions, or the skill scripts.

## Visual Identity (CSS Tokens)

- **Body font:** unchanged — `ui-sans-serif, system-ui, ...`.
- **Serif stack:** `ui-serif, Georgia, "Source Serif Pro", serif`. Used only
  for hero numerals and the subtitle line.
- **Palette:**
  - `--bg0: #fbfaf7` (warm off-white, was `#ffffff`)
  - `--text0: #1a1a1a` (was `#0b0f1a`)
  - `--text2: #7a7066` (was `#6b7280`; warmer)
  - `--border0: #ebe4d4` (was `#e6e8ec`; paper hairline)
  - `--accent0: #1b5fd6` (unchanged, restricted to status signals)
  - Hero block uses `0` border radius (hard edges, magazine feel).
- **Hero rhythm scale (new):** `--hero1: 14px` `--hero2: 28px` `--hero3: 40px`
  `--hero4: 56px` `--hero5: 80px`. Used only inside `#hero`.
- **Base spacing ladder:** unchanged (8px).

## Hero Block Composition

Replaces current `.hero-grid > (.now-card + .summary-card)`.

```text
LOCALTRACE · 2026.07.05                              ← eyebrow (caps 11px, muted)
Today, you focused 4h 12m.                           ← serif 64px / 300 / lh 0.95
across 13 apps and 9 sites. 28 switches. 38m audio.
— a quieter Tuesday.                                 ← 14px muted, italic tail
─────────────────────────────────────────  ← 1px hairline
FOCUS     AUDIO      SWITCHES    EVENTS              ← caps tags, 10px, 0.14em
4h 12m    38m        28          412                 ← serif 22px numerals
```

- Sits in its own `#hero` `<article>`, full width of `.main-stack` + side rail
  above the `.workbench-grid`.
- No chips, no avatar, no background tint, no shadow, no border radius.
- Subhead generation rules:
  - `focusSeconds >= 1h` → `"Today, you focused Xh Ym."`
  - `1m <= focusSeconds < 1h` → `"Today so far — Xm focused."`
  - `focusSeconds < 1m` → `"Nothing tracked yet today."`
- Numeric row omits metrics that have no data (always shows at minimum
  Focus; other three only when value > 0).
- Eyebrow reads local date `YYYY.MM.DD` using `Intl.DateTimeFormat`.

### Responsive

- ≤ 980px (existing tablet breakpoint): hero numerals drop to 44px; hero
  block spans full width (workbench-grid already collapses to single column).
- ≤ 700px (existing mobile breakpoint): hero numerals drop to 32px; eyebrow
  hidden; sub line truncates to two lines with safe ellipsis.

## Secondary Section Demotion

Applied uniformly to the **Timeline**, **Recent flow**, **Today Top**, and
**Health** cards below the hero.

| Property              | Before     | After      |
|-----------------------|------------|------------|
| `card` padding        | 18px       | 14px       |
| Section heading       | `<h3>` 18px| caps 11px tag |
| Numeric strong        | 24-28px    | 16px       |
| Row min-height        | 54-58px    | 44-48px    |
| Card border           | `var(--border0)` | `#ebe4d4` |
| Card shadow           | yes        | none       |
| Corner radius         | 12px       | 12px (unchanged) |

`.workbench-grid` columns change from `1.65fr / 0.9fr` to `1.4fr / 1fr` —
side rail widens to host the new "Right now" card.

Timeline bar height drops from `18px` (top 18, height 18) to `12px` (top 22,
height 12) for visual subordination to the hero.

## Right Now Card (new, replaces 3-row `now-card`)

- Lives at the **top of the side rail**, above "Today Top".
- Contains up to three rows (Focus app / Using tab / Background audio) using
  a 24px avatar + 1 strong label + 1 muted sub line each.
- Footer: `Updated Xs ago` using `lastFocus.observed_at` (or
  `audio.observed_at`).
- Falls back gracefully if any of the three are missing.

## Settings Page

- Markup and behaviour unchanged.
- Token updates only: warm palette, serif off (this is utilitarian).
- Label `<span>` text becomes `font-size: 11px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--text2)` (caps tag style).
- Native checkbox retained; only the `.toggle` background, border, and
  inside padding are retuned to the new palette.

## Data Flow

- No API change.
- `loadAll()` keeps its `Promise.all` of `/health`, `/events`,
  `/settings`, `/privacy/rules`, `/tracking/status`.
- `buildTodayModel()` adds one derived field:
  `headline = { eyebrow, sentence, sub_tail, numerals: [{tag, value}, ...] }`
  derived from `model.focusSeconds`, `model.audioSeconds`,
  `model.focusSwitches`, `model.todayEvents.length`.
- New function `renderHero(headline)` writes into the `#hero` element.
- `renderNow` (now `renderRightNow`) keeps the same data dependencies but
  moves its target to inside the side rail and uses the smaller avatar.

## Component Inventory

Single render unit per concept, no premature abstraction:

- `#hero` — editorial hero block (state-derived).
- `.right-now` card — top of side rail.
- `.timeline-card`, `.flow-list`, `.top-list`, `.health-card` — demoted
  versions of existing cards.
- Settings cards inherit demoted style with utilitarian label styles.

## Errors & Edge Cases

- If `state.events` is empty, hero shows `"Nothing tracked yet today."` with
  the four inline numerals hidden except `EVENTS 0` (so the row never
  collapses to a single column that looks broken).
- If `Intl.DateTimeFormat` returns the system's locale-only format, eyebrow
  falls back to the locale's calendar using `{ year: 'numeric', month:
  '2-digit', day: '2-digit' }` joined with `.`.
- Server unreachable: `setStatus(error.message)` continues to surface in
  the nav-rail status line (not the hero). Hero is allowed to render with
  whatever data was last cached.

## Testing

### `tests/web-ui-pages.spec.mjs`

- Replace `metrics and settings are separate pages` assertions for the hero
  area: look for `#hero`, expect it visible on Metrics view, hidden on
  Settings.
- Update `stale browser audio is not shown as current background audio`
  and `stale browser audio is hidden even when idle cutoff is long` to
  assert against the new `.right-now` block.
- Add `hero renders serif headline and inline numerals`:
  start the test server, navigate, assert `#hero h1` exists with non-empty
  textContent and that `getComputedStyle(it).fontFamily` contains
  `serif` (case-insensitive).
- Add `mobile hero downsizes below 700px`: viewport 390x844, assert
  computed `font-size` of the `#hero h1` numeric row is `<= 32px`.
- `recent flow renders latest events in descending order`: keep as-is
  (the demoted `.flow-item` keeps the same shape and id).

### `tests/test_http_api.py`

- `test_http_routes_expose_web_settings_and_local_json_apis` already
  asserts a few substring families. Update:
  - Replace `"Recent flow" in html` with `"flow-list"` (class-based check
    is stable across copy edits).
  - Add `assert 'id="hero"' in html`.
  - Add `assert "renderHero" in script`.
- All other tests in this file unchanged.

### What stays untouched

- Python `test_config.py`, `test_skill_scripts.py` — out of scope.
- Extension service worker tests — out of scope.

## Rollout / Rollback

- Single PR; no migrations.
- The skill `lint:md` already covers markdown; no CSS lint in repo, so
  manual review for the stylesheet diff.
- Rollback = `git revert`; no schema or persisted-state effects.

## Open Questions

None at time of approval.
