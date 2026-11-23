/**
 * 灵感文件导入：.txt/.md/.json/.csv 直接读文本；.docx 用 ZIP 中央目录 + inflate 手工解。
 *
 * 这段逻辑与框架完全无关，从 Vue 版 Create.vue 原样搬过来（只加了类型）。
 * 之所以不用库：只取 word/document.xml 一个条目，手写解析比引入 mammoth/jszip 更轻。
 */

const TEXT_EXT = /\.(txt|md|markdown|log|json|csv)$/i

/** 单文件与合并后的字符上限（超出截断） */
export const MAX_IMPORT_CHARS = 20_000
export const MAX_TOTAL_CHARS = 40_000

/** 从 document.xml 提取纯文本（独立导出以便单测实体解码顺序） */
export function xmlToPlainText(xml: string): string {
  return xml
    .replace(/<w:tab\b[^>]*\/>/g, '\t')
    .replace(/<\/w:p>/g, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d: string) => String.fromCodePoint(Number(d)))
    // &amp; 必须最后解：否则 "&amp;lt;"（字面 &lt;）会被二次解成 "<"
    .replace(/&amp;/g, '&')
}

/** 从 .docx（ZIP + deflate）中提取 word/document.xml 的纯文本 */
export async function extractDocxText(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer())
  const dv = new DataView(buf.buffer)

  // 反向扫描定位中央目录结尾记录 EOCD
  let eocd = -1
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('invalid zip')

  const count = dv.getUint16(eocd + 10, true)
  let off = dv.getUint32(eocd + 16, true)
  let target: { method: number; compSize: number; localHeader: number } | null = null

  for (let n = 0; n < count; n++) {
    if (dv.getUint32(off, true) !== 0x02014b50) break
    const method = dv.getUint16(off + 10, true)
    const compSize = dv.getUint32(off + 20, true)
    const nameLen = dv.getUint16(off + 28, true)
    const extraLen = dv.getUint16(off + 30, true)
    const commentLen = dv.getUint16(off + 32, true)
    const localHeader = dv.getUint32(off + 42, true)
    const name = new TextDecoder().decode(buf.subarray(off + 46, off + 46 + nameLen))
    if (name === 'word/document.xml') {
      target = { method, compSize, localHeader }
      break
    }
    off += 46 + nameLen + extraLen + commentLen
  }
  if (!target) throw new Error('document.xml not found')

  const lNameLen = dv.getUint16(target.localHeader + 26, true)
  const lExtraLen = dv.getUint16(target.localHeader + 28, true)
  const start = target.localHeader + 30 + lNameLen + lExtraLen
  const data = buf.subarray(start, start + target.compSize)

  let xmlBytes = data
  if (target.method === 8) {
    if (typeof DecompressionStream === 'undefined') throw new Error('no DecompressionStream')
    const stream = new Blob([data]).stream().pipeThrough(
      new DecompressionStream('deflate-raw' as CompressionFormat)
    )
    xmlBytes = new Uint8Array(await new Response(stream).arrayBuffer())
  } else if (target.method !== 0) {
    throw new Error('unsupported zip method')
  }

  const xml = new TextDecoder().decode(xmlBytes)
  return xmlToPlainText(xml)
}

/** 按文件类型提取文本，不支持的类型返回 null */
export async function extractText(file: File): Promise<string | null> {
  if (/\.docx$/i.test(file.name)) return extractDocxText(file)
  if (TEXT_EXT.test(file.name) || file.type.startsWith('text/')) return file.text()
  return null
}