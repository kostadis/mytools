// zoomscrape/download.js
//
// Run this in the DevTools Console *after* scrape.js. It reads the dump
// textarea that scrape.js created and triggers a normal browser download of
// zoom_chat.txt — useful when clipboard copy is awkward or the dump is large.

(() => {
  const ta = document.getElementById('__chat_dump__');
  if (!ta) {
    console.error('No __chat_dump__ textarea found. Run scrape.js first.');
    return;
  }
  const blob = new Blob([ta.value], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'zoom_chat.txt';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
})();
