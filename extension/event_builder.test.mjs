import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_SETTINGS,
  buildTabActiveEvent,
  buildTabAudioStopEvent,
  endpointFromSettings,
  reserveSeq,
  safeHostname
} from "./event_builder.mjs";

test("endpointFromSettings always targets LocalTrace loopback events", () => {
  assert.equal(endpointFromSettings({}), "http://127.0.0.1:8765/events");
  assert.equal(endpointFromSettings({ port: 9000 }), "http://127.0.0.1:9000/events");
  assert.equal(endpointFromSettings({ port: "9001" }), "http://127.0.0.1:9001/events");
  assert.equal(endpointFromSettings({ port: "http://10.0.0.2:8765" }), "http://127.0.0.1:8765/events");
});

test("safeHostname keeps only http and https hostnames", () => {
  assert.equal(safeHostname("https://github.com/CHZarles/LocalTrace?x=1"), "github.com");
  assert.equal(safeHostname("http://example.test/path"), "example.test");
  assert.equal(safeHostname("chrome://extensions"), null);
  assert.equal(safeHostname("file:///tmp/example.html"), null);
  assert.equal(safeHostname("not a url"), null);
});

test("buildTabActiveEvent records tab title by default", () => {
  const event = buildTabActiveEvent({
    observedAt: "2026-07-01T10:33:00.000Z",
    seq: 20,
    activity: "focus",
    browser: "edge",
    tab: {
      id: 100,
      windowId: 1,
      title: "Secret title",
      url: "https://github.com/CHZarles/LocalTrace?private=true"
    },
    settings: DEFAULT_SETTINGS
  });

  assert.deepEqual(event, {
    observed_at: "2026-07-01T10:33:00.000Z",
    source: "browser_extension",
    seq: 20,
    kind: "tab_active",
    entity_type: "domain",
    entity: "github.com",
    title: "Secret title",
    payload: {
      activity: "focus",
      browser: "edge",
      window_id: 1,
      tab_id: 100
    }
  });
});

test("buildTabActiveEvent records tab title when sendTitle is omitted", () => {
  const event = buildTabActiveEvent({
    observedAt: "2026-07-01T10:33:30.000Z",
    seq: 21,
    activity: "focus",
    browser: "chrome",
    tab: {
      id: 101,
      windowId: 1,
      title: "Default title",
      url: "https://example.com/article"
    },
    settings: {}
  });

  assert.equal(event.title, "Default title");
});

test("buildTabActiveEvent can omit tab title when explicitly disabled", () => {
  const event = buildTabActiveEvent({
    observedAt: "2026-07-01T10:34:00.000Z",
    seq: 22,
    activity: "audio",
    browser: "chrome",
    tab: {
      id: 102,
      windowId: 2,
      title: "Music title",
      url: "https://youtube.com/watch?v=secret"
    },
    settings: { ...DEFAULT_SETTINGS, sendTitle: false }
  });

  assert.equal(event.kind, "tab_active");
  assert.equal(event.entity, "youtube.com");
  assert.equal(event.title, null);
  assert.equal(event.payload.activity, "audio");
  assert.equal(event.payload.title, undefined);
  assert.equal(event.payload.url, undefined);
});

test("buildTabAudioStopEvent creates LocalTrace stop events", () => {
  const event = buildTabAudioStopEvent({
    observedAt: "2026-07-01T10:35:00.000Z",
    seq: 22,
    browser: "edge",
    domain: "youtube.com",
    tabId: 101,
    windowId: 2,
    reason: "audible_tab_stopped"
  });

  assert.deepEqual(event, {
    observed_at: "2026-07-01T10:35:00.000Z",
    source: "browser_extension",
    seq: 22,
    kind: "tab_audio_stop",
    entity_type: "domain",
    entity: "youtube.com",
    title: null,
    payload: {
      activity: "audio",
      browser: "edge",
      reason: "audible_tab_stopped",
      window_id: 2,
      tab_id: 101
    }
  });
});

test("reserveSeq is monotonic and stable for matching pending keys", () => {
  const state = {};

  assert.equal(reserveSeq(state, "focus:github.com:1:100"), 1);
  assert.equal(reserveSeq(state, "focus:github.com:1:100"), 1);
  assert.equal(reserveSeq(state, "audio:youtube.com:2:101"), 2);
  assert.equal(reserveSeq(state, "audio:youtube.com:2:101"), 2);
});
