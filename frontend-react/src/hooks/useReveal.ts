/**
 * 滚动入场动效：替代 Vue 的 v-reveal 自定义指令。
 * 观察器全局共享一份（与指令实现一致），进入视口后加 .visible 并停止观察。
 */
import { useEffect, type RefObject } from 'react'

let observer: IntersectionObserver | null = null

function getObserver(): IntersectionObserver | null {
  if (typeof IntersectionObserver === 'undefined') return null
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
            observer?.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.1 }
    )
  }
  return observer
}

export function useReveal<T extends HTMLElement>(ref: RefObject<T>, delay = 0): void {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ob = getObserver()
    if (!ob) {
      el.classList.add('reveal', 'visible')
      return
    }
    el.classList.add('reveal')
    if (delay >= 1 && delay <= 6) el.classList.add(`reveal-delay-${delay}`)
    ob.observe(el)
    return () => ob.unobserve(el)
  }, [ref, delay])
}