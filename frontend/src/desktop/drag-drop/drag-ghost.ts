let ghostEl: HTMLElement | null = null

function getPrimaryEl(key: string): HTMLElement | null {
  return document.querySelector(`[data-selection-key="${key}"]`) as HTMLElement | null
}

function buildGhost(ids: string[]): HTMLElement {
  const ghost = document.createElement('div')
  ghost.id = 'drag-ghost-el'
  ghost.style.cssText =
    'position:fixed;z-index:2147483647;pointer-events:none;opacity:0.7;transition:none;'

  const primaryEl = getPrimaryEl(ids[0])
  if (primaryEl) {
    const cloned = primaryEl.cloneNode(true) as HTMLElement
    cloned.style.cssText = 'margin:0;opacity:1;transform:none;width:' + primaryEl.offsetWidth + 'px;'
    cloned.querySelectorAll('.desktop-icon-item, .fm-entry').forEach(el => {
      const htmlEl = el as HTMLElement
      htmlEl.style.opacity = '1'
      htmlEl.style.pointerEvents = ''
      htmlEl.style.transform = ''
    })
    ghost.appendChild(cloned)
  }

  if (ids.length > 1) {
    const badge = document.createElement('span')
    badge.textContent = `${ids.length}项`
    badge.style.cssText =
      'position:absolute;top:-6px;right:-6px;font-size:11px;color:#fff;background:#2395bc;' +
      'border-radius:10px;padding:1px 7px;line-height:18px;min-width:18px;text-align:center;' +
      'box-shadow:0 2px 4px rgba(0,0,0,0.2);'
    ghost.appendChild(badge)
  }

  return ghost
}

export function createDragGhost(ids: string[], x: number, y: number, grabOffsetX = 16, grabOffsetY = 16): void {
  removeDragGhost()
  ghostEl = buildGhost(ids)
  ghostEl.style.left = `${x - grabOffsetX}px`
  ghostEl.style.top = `${y - grabOffsetY}px`
  document.body.appendChild(ghostEl)
}

export function updateDragGhostPosition(x: number, y: number, grabOffsetX = 16, grabOffsetY = 16): void {
  if (!ghostEl) return
  ghostEl.style.left = `${x - grabOffsetX}px`
  ghostEl.style.top = `${y - grabOffsetY}px`
}

export function removeDragGhost(): void {
  if (ghostEl) {
    ghostEl.remove()
    ghostEl = null
  }
}
