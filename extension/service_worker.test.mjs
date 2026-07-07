import assert from "node:assert/strict";
import test from "node:test";

function eventTarget() {
  const listeners = [];
  return {
    addListener(listener) {
      listeners.push(listener);
    },
    async emit(...args) {
      for (const listener of listeners) {
        await listener(...args);
      }
    }
  };
}

async function waitForPostedEvents(posted, count) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (posted.length >= count) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

function installChromeMock({ focused, activeTab, audibleTabs, initialStorage = {} }) {
  const storage = { ...initialStorage };
  const alarmsOnAlarm = eventTarget();
  const runtimeOnInstalled = eventTarget();
  const runtimeOnStartup = eventTarget();
  const runtimeOnMessage = eventTarget();
  const storageOnChanged = eventTarget();
  const tabsOnActivated = eventTarget();
  const tabsOnUpdated = eventTarget();
  const tabsOnRemoved = eventTarget();
  const windowsOnFocusChanged = eventTarget();
  globalThis.self = {
    navigator: {
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0"
    }
  };
  globalThis.chrome = {
    alarms: {
      create: async () => {},
      onAlarm: alarmsOnAlarm
    },
    runtime: {
      onInstalled: runtimeOnInstalled,
      onStartup: runtimeOnStartup,
      onMessage: runtimeOnMessage
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
      onChanged: storageOnChanged
    },
    tabs: {
      query: async (query) => {
        if (query?.audible === true) return audibleTabs;
        if (query?.active === true) return activeTab ? [activeTab] : [];
        return [];
      },
      onActivated: tabsOnActivated,
      onUpdated: tabsOnUpdated,
      onRemoved: tabsOnRemoved
    },
    windows: {
      getLastFocused: (_options, callback) => callback({ focused }),
      onFocusChanged: windowsOnFocusChanged
    }
  };
  return {
    alarmsOnAlarm,
    runtimeOnInstalled,
    runtimeOnStartup,
    runtimeOnMessage,
    storageOnChanged,
    tabsOnActivated,
    tabsOnUpdated,
    tabsOnRemoved,
    windowsOnFocusChanged
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
  assert.deepEqual(
    posted.map((event) => event.title),
    ["Playing", "Playing"]
  );
  assert.equal(
    posted.some((event) => event.kind === "tab_audio_stop"),
    false
  );
});

test("service worker migrates the old sendTitle default to enabled", async () => {
  const posted = [];
  const tab = {
    id: 8,
    windowId: 4,
    title: "Research title",
    url: "https://docs.example/article",
    audible: false,
    lastAccessed: 2000
  };

  installChromeMock({
    focused: true,
    activeTab: tab,
    audibleTabs: [],
    initialStorage: { sendTitle: false }
  });
  globalThis.fetch = async (_url, options) => {
    posted.push(JSON.parse(options.body));
    return { ok: true };
  };

  await import(`./service_worker.js?legacy-title-default=${Date.now()}`);
  await waitForPostedEvents(posted, 1);

  assert.equal(posted[0].title, "Research title");
});

test("service worker emits same-tab title changes for focus without waiting for heartbeat", async () => {
  const posted = [];
  const tab = {
    id: 9,
    windowId: 5,
    title: "Original title",
    url: "https://notes.example/page",
    audible: false,
    lastAccessed: 3000
  };

  const events = installChromeMock({
    focused: true,
    activeTab: tab,
    audibleTabs: [],
    initialStorage: { heartbeatSeconds: 60 }
  });
  globalThis.fetch = async (_url, options) => {
    posted.push(JSON.parse(options.body));
    return { ok: true };
  };

  await import(`./service_worker.js?title-change-focus=${Date.now()}`);
  await waitForPostedEvents(posted, 1);

  tab.title = "Updated title";
  await events.tabsOnUpdated.emit(tab.id, { title: tab.title });
  await waitForPostedEvents(posted, 2);

  assert.deepEqual(
    posted.map((event) => event.title),
    ["Original title", "Updated title"]
  );
});

test("service worker ignores unchanged same-tab title before heartbeat", async () => {
  const posted = [];
  const tab = {
    id: 10,
    windowId: 6,
    title: "Stable title",
    url: "https://notes.example/page",
    audible: false,
    lastAccessed: 4000
  };

  const events = installChromeMock({
    focused: true,
    activeTab: tab,
    audibleTabs: [],
    initialStorage: { heartbeatSeconds: 60 }
  });
  globalThis.fetch = async (_url, options) => {
    posted.push(JSON.parse(options.body));
    return { ok: true };
  };

  await import(`./service_worker.js?title-unchanged-focus=${Date.now()}`);
  await waitForPostedEvents(posted, 1);

  await events.tabsOnUpdated.emit(tab.id, { title: tab.title });
  await new Promise((resolve) => setTimeout(resolve, 50));

  assert.equal(posted.length, 1);
});

test("service worker emits title changes for focus and audio state separately", async () => {
  const posted = [];
  const tab = {
    id: 11,
    windowId: 7,
    title: "Playing original",
    url: "https://music.example/watch",
    audible: true,
    lastAccessed: 5000
  };

  const events = installChromeMock({
    focused: true,
    activeTab: tab,
    audibleTabs: [tab],
    initialStorage: { heartbeatSeconds: 60 }
  });
  globalThis.fetch = async (_url, options) => {
    posted.push(JSON.parse(options.body));
    return { ok: true };
  };

  await import(`./service_worker.js?title-change-audio=${Date.now()}`);
  await waitForPostedEvents(posted, 2);

  tab.title = "Playing updated";
  await events.tabsOnUpdated.emit(tab.id, { title: tab.title });
  await waitForPostedEvents(posted, 4);

  assert.deepEqual(
    posted.slice(2).map((event) => [event.payload.activity, event.title]),
    [
      ["focus", "Playing updated"],
      ["audio", "Playing updated"]
    ]
  );
});
