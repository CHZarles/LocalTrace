import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("manifest defines a LocalTrace MV3 extension with loopback-only access", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("./manifest.json", import.meta.url), "utf8")
  );

  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.name, "LocalTrace Extension");
  assert.equal(manifest.action.default_title, "LocalTrace");
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:*/*"]);
  assert.equal(manifest.background.service_worker, "service_worker.js");
  assert.equal(manifest.background.type, "module");
  assert.equal(manifest.permissions.includes("nativeMessaging"), false);
});
