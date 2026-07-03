# LocalTrace Browser Extension

Manifest V3 extension for LocalTrace browser activity capture.

## Behavior

- Sends domain-level browser activity to LocalTrace core.
- Posts only to `http://127.0.0.1:<port>/events`.
- Uses port `8765` by default.
- Emits `tab_active` with `payload.activity = focus` for the focused browser tab.
- Emits `tab_active` with `payload.activity = audio` for audible background tabs.
- Emits `tab_audio_stop` when a previously tracked audible tab stops.
- Sends tab titles by default; clear `Send tab title` to omit them.
- Does not send full URLs, page content, screenshots, or keyboard input.

## Install For Local Smoke Testing

1. Start LocalTrace core on `127.0.0.1:8765`.
2. Open the browser extension page:
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
3. Enable developer mode.
4. Load this directory as an unpacked extension: `extension/`.
5. Open the LocalTrace extension popup and confirm tracking is enabled.
6. Click `Test Health`; it should show `OK` when LocalTrace core is running.

## Manual Smoke

1. Open a normal `http` or `https` tab and focus it.
2. Query `GET /events?source=browser_extension&kind=tab_active`.
3. Confirm the focus event has:
   - `source = browser_extension`
   - `kind = tab_active`
   - `entity_type = domain`
   - `payload.activity = focus`
   - no full URL in the event or payload
   - `title` contains the tab title by default
4. Play audio from a browser tab while the browser is not focused.
5. Query `GET /events?source=browser_extension&kind=tab_active`.
6. Confirm an audio event has `payload.activity = audio`.
7. Stop the browser audio or close the audible tab.
8. Query `GET /events?source=browser_extension&kind=tab_audio_stop`.
9. Confirm the stop event has `payload.activity = audio` and a stop `reason`.
10. Disable tracking in the popup and confirm no new browser events are sent.

## Scope Boundaries

- No Native Messaging.
- No token, login, pairing, LAN, or cloud behavior.
- No full URL capture by default.
- No page body, screenshot, or keyboard capture.
