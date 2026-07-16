// Generic text utilities, ported verbatim from adventure_editor.py's vanilla
// JS. No DOM dependencies — kept pure so they stay trivially testable.

// Escapes text the same way `div.textContent = s; return div.innerHTML` did
// in the original: only &, <, > are encoded (quotes are never escaped inside
// a text node, only inside attribute values).
export function escapeHtml(s: string): string {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Join broken lines from PDF copy-paste into continuous paragraphs.
// - Lines ending with a hyphen: remove hyphen and join directly (e.g. "fac-\ning" -> "facing")
// - Blank lines: preserved as paragraph breaks
// - All other line breaks: replaced with a space
export function joinLines(text: string): string {
  const lines = text.split('\n')
  const parts: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.trim() === '') {
      parts.push('\n\n')
    } else if (line.endsWith('-') && i + 1 < lines.length && lines[i + 1].trim() !== '') {
      parts.push(line.slice(0, -1))
    } else {
      parts.push(line)
      if (i + 1 < lines.length && lines[i + 1].trim() !== '') {
        parts.push(' ')
      }
    }
  }
  return parts.join('').replace(/ +/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
}
