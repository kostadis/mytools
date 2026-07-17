// {@tag content} -> styled HTML span, ported verbatim from adventure_editor.py's
// renderTags. Input must already be HTML-escaped (see textUtils.escapeHtml) —
// { and } and @ pass through escaping untouched, so tag markup is always
// literal here, never something a user could inject via node text.

export function renderTags(html: string): string {
  return html.replace(/\{@(\w+)\s*([^}]*)\}/g, (_match, tag: string, content: string) => {
    content = content.trim()
    const parts = content.split('|')
    const name = parts[0]
    const display = parts.length > 1 ? parts[1] : name

    switch (tag) {
      case 'b':
      case 'bold':
        return `<b>${display}</b>`
      case 'i':
      case 'italic':
        return `<i>${display}</i>`
      case 'spell':
        return `<i class="tag-spell">${display}</i>`
      case 'creature':
        return `<span class="tag-creature">${display}</span>`
      case 'condition':
        return `<span class="tag-condition">${display}</span>`
      case 'dc':
        return `<span class="tag-dc">DC ${name}</span>`
      case 'damage':
        return `<span class="tag-damage">${name}</span>`
      case 'hit':
        return `<span class="tag-hit">+${name}</span>`
      case 'h':
        return `<i>Hit:</i> `
      case 'item':
        return `<span class="tag-item">${display}</span>`
      case 'skill':
        return `<span class="tag-skill">${display}</span>`
      case 'atk':
        return `<i>[${name}]</i>`
      case 'recharge':
        return `(Recharge ${name})`
      case 'dice':
        return `${name}`
      case 'note':
        return `<i>(${display})</i>`
      case 'area':
        return `<b>${display}</b>`
      case 'adventure':
      case 'book':
        return `<i>${display}</i>`
      case 'sense':
        return display
      case 'chance':
        return `${name}%`
      case 'scaledice':
      case 'scaledamage':
        return display || name
      case 'filter':
        return display
      case 'action':
      case 'status':
        return `<span class="tag-condition">${display}</span>`
      default:
        return `<span title="{@${tag}}">${display || name}</span>`
    }
  })
}
