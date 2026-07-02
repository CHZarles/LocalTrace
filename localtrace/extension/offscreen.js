function ping() {
  try {
    chrome.runtime.sendMessage({ type: "keepAlivePing", ts: Date.now() }).catch(() => {});
  } catch {
    // Ignore wake-up failures.
  }
}

setTimeout(ping, 500);
setInterval(ping, 25_000);
