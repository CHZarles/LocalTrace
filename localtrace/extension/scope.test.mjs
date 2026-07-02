import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const serviceWorker = await readFile(
  new URL("./service_worker.js", import.meta.url),
  "utf8"
);
const popup = await readFile(new URL("./popup.js", import.meta.url), "utf8");
const cloudSyncedStorage = ["chrome", "storage", "sync"].join(".");
const manualEmitMessage = ["force", "Emit"].join("");
const manualResetMessage = ["rep", "air"].join("");

test("extension settings stay in local storage", () => {
  assert.equal(serviceWorker.includes(cloudSyncedStorage), false);
  assert.equal(popup.includes(cloudSyncedStorage), false);
  assert.equal(serviceWorker.includes("chrome.storage.local"), true);
  assert.equal(popup.includes("chrome.storage.local"), true);
});

test("popup load does not force event capture", () => {
  assert.equal(popup.includes(`  ${manualEmitMessage}();`), false);
});

test("popup does not expose event-generating controls", async () => {
  const popupHtml = await readFile(new URL("./popup.html", import.meta.url), "utf8");
  assert.equal(popupHtml.includes(manualEmitMessage), false);
  assert.equal(popupHtml.includes(manualResetMessage), false);
  assert.equal(popup.includes(manualEmitMessage), false);
  assert.equal(popup.includes(manualResetMessage), false);
});

test("runtime messages do not expose manual event generation", () => {
  assert.equal(serviceWorker.includes(`"${manualEmitMessage}"`), false);
  assert.equal(serviceWorker.includes(`"${manualResetMessage}"`), false);
});
