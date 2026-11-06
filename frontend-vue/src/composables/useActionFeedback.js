const ACTION_SELECTOR = 'button, [role="button"], [data-action]'
const CLICK_CLASS = 'is-action-clicked'
const timers = new WeakMap()

function findAction(target) {
  return target instanceof Element ? target.closest(ACTION_SELECTOR) : null
}

function isDisabled(action) {
  return (
    action.matches(':disabled') ||
    action.getAttribute('aria-disabled') === 'true' ||
    action.hasAttribute('data-no-click-animation')
  )
}

function animateClick(event) {
  const action = findAction(event.target)
  if (!action || isDisabled(action)) return

  const rect = action.getBoundingClientRect()
  const x = event.clientX > 0 ? event.clientX - rect.left : rect.width / 2
  const y = event.clientY > 0 ? event.clientY - rect.top : rect.height / 2
  action.style.setProperty('--action-x', `${x}px`)
  action.style.setProperty('--action-y', `${y}px`)

  window.clearTimeout(timers.get(action))
  action.classList.remove(CLICK_CLASS)
  void action.offsetWidth
  action.classList.add(CLICK_CLASS)
  timers.set(
    action,
    window.setTimeout(() => {
      action.classList.remove(CLICK_CLASS)
      timers.delete(action)
    }, 520),
  )
}

export function useActionFeedback() {
  function start() {
    document.addEventListener('click', animateClick, true)
  }

  function stop() {
    document.removeEventListener('click', animateClick, true)
  }

  return { start, stop }
}
