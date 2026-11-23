/**
 * v-reveal 滚动入场指令（对齐参考稿 app.html 的 .reveal + IntersectionObserver）
 * 用法：v-reveal 或 v-reveal="3"（3 = reveal-delay-3 级联延迟，1-6）
 */
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible')
        observer.unobserve(entry.target)
      }
    })
  },
  { threshold: 0.1 }
)

export const reveal = {
  mounted(el, binding) {
    el.classList.add('reveal')
    const delay = Number(binding.value)
    if (delay >= 1 && delay <= 6) {
      el.classList.add(`reveal-delay-${delay}`)
    }
    observer.observe(el)
  },
  unmounted(el) {
    observer.unobserve(el)
  },
}
