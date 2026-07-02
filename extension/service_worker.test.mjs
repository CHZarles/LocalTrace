import assert from "node:assert/strict";
import test from "node:test";

function eventTarget() {
  return {
    addListener() {}
  };
}

async function waitForPostedEvents(posted, count) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (posted.length >= count) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

function installChromeMock({ focused, activeTab, audibleTabs }) {
  const storage = {};
  globalThis.self = {
    navigator: {
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"
    }
  };
  globalThis.chrome = {
    alarms: {
      create: async () => {},
      onAlarm: eventTarget()
    },
    runtime: {
      onInstalled: eventTarget(),
      onStartup: eventTarget(),
      onMessage: eventTarget()
    },
    storage: {
      local: {
        get: async (keys) => {
          if (keys === "localtraceExtensionState") return {};
          if (Array.isArray(keys)) {
            return Object.fromEntries(
              keys
                .filter((key) => storage[key] !== undefined)
                .map((key) => [key, storage[key]])
            );
          }
          if (keys && typeof keys === "object") {
            return { ...keys, ...storage };
          }
          return { ...storage };
        },
        set: async (values) => {
          Object.assign(storage, values);
        }
      },
      onChanged: eventTarget()
    },
    tabs: {
      query: async (query) => {
        if (query?.audible === true) return audibleTabs;
        if (query?.active === true) return activeTab ? [activeTab] : [];
        return [];
      },
      onActivated: eventTarget(),
      onUpdated: eventTarget(),
      onRemoved: eventTarget()
    },
    windows: {
      getLastFocused: (_options, callback) => callback({ focused }),
      onFocusChanged: eventTarget()
    }
  };
}

test("service worker reports audible web tabs even when the browser is focused", async () => {
  const posted = [];
  const tab = {
    id: 7,
    windowId: 3,
    title: "Playing",
    url: "https://music.example/watch",
    audible: true,
    lastAccessed: 1000
  };

  installChromeMock({ focused: true, activeTab: tab, audibleTabs: [tab] });
  globalThis.fetch = async (_url, options) => {
    posted.push(JSON.parse(options.body));
    return { ok: true };
  };

  await import(`./service_worker.js?foreground-audio=${Date.now()}`);
  await waitForPostedEvents(posted, 2);

  assert.deepEqual(
    posted.map((event) => event.payload?.activity),
    ["focus", "audio"]
  );
  assert.equal(
    posted.some((event) => event.kind === "tab_audio_stop"),
    false
  );
});
