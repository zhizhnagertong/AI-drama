import { describe, expect, it } from 'vitest'

import { xmlToPlainText } from '@/lib/importText'

describe('xmlToPlainText', () => {
  it('段落转换为换行、制表符与标签被剥离', () => {
    const xml =
      '<w:p><w:r><w:t>甲</w:t><w:tab/><w:t>乙</w:t></w:r></w:p><w:p><w:t>丙</w:t></w:p>'
    expect(xmlToPlainText(xml)).toBe('甲\t乙\n丙\n')
  })

  it('&amp; 最后解码，&amp;lt; 只解一层为字面 &lt;，不被二次解成 <', () => {
    // 文档里想表达字面的 "&lt;tag&gt;"，OOXML 写成 &amp;lt;tag&amp;gt;
    expect(xmlToPlainText('<w:t>A &amp;lt;tag&amp;gt; B</w:t>')).toBe('A &lt;tag&gt; B')
  })

  it('常见命名实体与数字实体都只解一次', () => {
    expect(xmlToPlainText('<w:t>&lt;x&gt; &quot;q&quot; &apos;a&apos; &#20320;&#22909;</w:t>')).toBe(
      '<x> "q" \'a\' 你好'
    )
  })
})
