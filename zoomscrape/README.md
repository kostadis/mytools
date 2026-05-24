# zoomscrape

Snippets for extracting the in-meeting **chat** out of a Zoom cloud-recording
playback page when:

- The recording owner did **not** publish a separate `chat.txt` download, and
- You only have viewer / "Shared with me" access (no Zoom API), and
- The right-hand chat panel is a **virtualized scroller** — dragging to select
  across messages breaks as soon as you scroll, so the usual
  click-and-drag-then-Ctrl+C trick only captures the currently visible window.

The trick: the chat panel is just HTML. Scroll it programmatically from the
DevTools console, harvest each batch of messages as the virtual list renders
them, dedupe, and dump the result into a normal `<textarea>` on the page so
you can copy it without fighting clipboard permissions.

## Quick start

1. Open the Zoom recording playback page in your browser. Make sure the right-hand
   panel is on **Audio Transcript** or **Chat Messages** — whichever one you want
   to capture. (The script works for both; it doesn't care about the tab name,
   only about the scroller you anchor to.)
2. **Right-click on one of the chat / transcript message bubbles** in that panel
   → **Inspect**. This selects the element in DevTools so it's available in the
   Console as `$0`.
3. Open the **Console** tab (don't click anywhere else first — you need `$0`
   to still be pointing at the message you inspected).
4. Paste the contents of [`scrape.js`](./scrape.js) and press Enter.
5. A **red-bordered textarea** will appear in the top-left of the page
   containing every message it collected. Click into it, `Ctrl+A`, `Ctrl+C`,
   and paste wherever you need.

If you'd rather get a file instead of using the clipboard, after running
`scrape.js` paste [`download.js`](./download.js) and it will trigger a normal
browser download of `zoom_chat.txt`.

## How it works

- Walks up from `$0` to find the row container (first ancestor with several
  similar siblings) — that's the virtual list.
- Walks further up to find the nearest scrollable ancestor (`overflow-y: auto`
  or `scroll`, with `scrollHeight > clientHeight`). That's the panel's scroller.
- Sets `scrollTop = 0`, then loops: scroll down ~one viewport, sleep ~350 ms
  so the virtualizer can render the next batch, harvest visible rows. Stops
  when scrolling stalls (already at the bottom).
- Dedupes by the first ~120 chars of each row's `innerText`.
- Dumps the joined result into `<textarea id="__chat_dump__">` overlaid on the
  page, and *also* tries `document.execCommand('copy')` as a best-effort
  clipboard write.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Right-click a chat message → Inspect first, then rerun.` | `$0` isn't pointing at the panel. | DevTools must be open; right-click *inside the panel* (on actual message text), then return to Console without clicking elsewhere. |
| `No scrollable ancestor found` | Anchored on a node that's outside the panel (e.g. a header/search box). | Right-click on the body of an actual message bubble, not the timestamp / search field. |
| Collected 0 messages | Row-parent walk-up landed on a wrapper with too few siblings. | Look at the `Row parent (list)` console log — confirm it's the list element. If not, click a different message and retry. |
| Far fewer messages than expected | Virtual list throttling, or scroll didn't reach bottom. | Re-run; or increase the sleep between scroll steps (`350` → `700` ms) inside `scrape.js`. |
| Nothing in clipboard but the textarea has the text | `execCommand('copy')` was blocked because DevTools had focus. | Just click into the red-bordered textarea on the page and `Ctrl+A` / `Ctrl+C` manually. That's the supported path. |

## Why not just use the Zoom API / download the chat file?

In most cases you should — Zoom cloud recordings normally save the in-meeting
chat as a separate `meeting_saved_chat.txt` next to the video, downloadable
from the recording's file listing. This scraper only exists for the cases
where:

- That file isn't offered (chat saving wasn't enabled, or the host stripped
  it before sharing), **and**
- You don't have API access to the host's Zoom account.

If either of those isn't true, prefer the official path.

## Publishing this folder to `nutanix-scratch/tools-scripts-docs`

This directory was authored locally at
`C:\Users\KostadisRoussos\Documents\zoomscrape`. To land it in the repo on the
`shadow-main` branch:

```bash
git clone --branch shadow-main \
  https://github.com/nutanix-scratch/tools-scripts-docs.git
cp -r /c/Users/KostadisRoussos/Documents/zoomscrape \
  tools-scripts-docs/zoomscrape
cd tools-scripts-docs
git checkout -b add-zoomscrape
git add zoomscrape
git commit -m "Add zoomscrape: extract chat from Zoom recordings via DevTools"
git push -u origin add-zoomscrape
gh pr create --base shadow-main --fill
```

Adjust the branch / PR style to whatever the repo conventions are.
