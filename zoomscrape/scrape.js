// zoomscrape/scrape.js
//
// Paste this into the DevTools Console on a Zoom cloud-recording playback page
// AFTER right-clicking a message in the chat / transcript panel and choosing
// "Inspect". That makes $0 point at the message, which this script uses as an
// anchor to discover the virtual-list row container and its scrollable parent.
//
// On completion you'll see a red-bordered <textarea id="__chat_dump__"> at the
// top-left of the page containing every message it collected (deduped). Click
// into it and Ctrl+A / Ctrl+C to copy. The script also attempts
// document.execCommand('copy') as a best-effort write to the clipboard.

(async () => {
  if (typeof $0 === 'undefined' || !$0) {
    console.error('Right-click a chat message → Inspect first, then rerun.');
    return;
  }

  // 1. Find the row container: walk up until the parent has multiple siblings
  //    (i.e. the parent looks like a list of rows, not a single wrapper).
  let row = $0;
  while (row.parentElement && row.parentElement.children.length < 3) {
    row = row.parentElement;
  }
  const rowParent = row.parentElement;
  console.log('Row sample:', row);
  console.log('Row parent (list):', rowParent);

  // 2. Find the scrollable ancestor.
  let scroller = rowParent;
  while (scroller && scroller !== document.body) {
    const s = getComputedStyle(scroller);
    if (/auto|scroll/.test(s.overflowY) && scroller.scrollHeight > scroller.clientHeight + 20) {
      break;
    }
    scroller = scroller.parentElement;
  }
  if (!scroller || scroller === document.body) {
    console.error('No scrollable ancestor found — try right-clicking a different message.');
    return;
  }
  console.log('Scroller:', scroller, 'scrollHeight=', scroller.scrollHeight);

  // 3. Harvest loop. Dedupe by a prefix of the row's innerText so the same
  //    message rendered twice (as the virtual list recycles nodes) collapses.
  const seen = new Map();
  const harvest = () => {
    for (const el of rowParent.children) {
      const text = (el.innerText || '').trim();
      if (!text) continue;
      const key = text.slice(0, 120);
      if (!seen.has(key)) seen.set(key, text);
    }
  };

  scroller.scrollTop = 0;
  await new Promise(r => setTimeout(r, 500));
  harvest();

  let last = -1;
  let stalls = 0;
  while (stalls < 3) {
    const before = scroller.scrollTop;
    scroller.scrollTop = before + Math.max(100, scroller.clientHeight - 40);
    await new Promise(r => setTimeout(r, 350));
    harvest();
    if (scroller.scrollTop === before) stalls++; else stalls = 0;
    if (scroller.scrollTop === last) break;
    last = scroller.scrollTop;
  }
  scroller.scrollTop = scroller.scrollHeight;
  await new Promise(r => setTimeout(r, 400));
  harvest();

  const out = [...seen.values()].join('\n\n----\n\n');
  console.log(`Collected ${seen.size} messages, ${out.length} chars.`);

  // 4. Drop the result into a textarea on the page so you can copy manually.
  let ta = document.getElementById('__chat_dump__');
  if (!ta) {
    ta = document.createElement('textarea');
    ta.id = '__chat_dump__';
    Object.assign(ta.style, {
      position: 'fixed',
      top: '10px',
      left: '10px',
      width: '600px',
      height: '400px',
      zIndex: 999999,
      background: 'white',
      color: 'black',
      border: '2px solid red',
      padding: '8px',
      fontFamily: 'monospace',
      fontSize: '12px',
    });
    document.body.appendChild(ta);
  }
  ta.value = out;
  ta.focus();
  ta.select();
  try {
    document.execCommand('copy');
    console.log('Copied via execCommand. If your clipboard is empty, just Ctrl+A/Ctrl+C inside the red textarea.');
  } catch (e) {
    console.log('Auto-copy failed — select the textarea on the page and Ctrl+C.');
  }
  return out;
})();
