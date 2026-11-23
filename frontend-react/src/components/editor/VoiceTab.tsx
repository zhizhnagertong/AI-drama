/**
 * 配音分区（对应 Editor.vue 第 1392–1440 行 + 第 804–811 行逻辑）。
 * 已有音频直接给原生 <audio controls>，没有则给「生成配音」按钮（无台词时禁用）。
 */
import { AudioMutedOutlined } from '@ant-design/icons'
import { Button, Empty, Tag } from 'antd'
import { useState } from 'react'

import { editorApi } from '@/api/editor'
import { toast } from '@/lib/feedback'
import { audioOfSb, fmtDuration, gradVarOf, firstCharOf, voiceLabel } from '@/lib/entities'
import type { Asset, Character, Storyboard } from '@/types'

interface VoiceTabProps {
  storyboards: Storyboard[]
  characters: Character[]
  assets: Asset[]
}

export function VoiceTab({ storyboards, characters, assets }: VoiceTabProps) {
  const [loadingId, setLoadingId] = useState<number | null>(null)

  /** 分镜 → 角色：先按 character_id，再按角色名匹配（与原版 charOf 一致） */
  function charOf(sb: Storyboard): Character | undefined {
    return (
      characters.find((c) => c.id === sb.character_id) ||
      characters.find((c) => !!c.name && c.name === sb.character_name)
    )
  }

  async function genVoice(sb: Storyboard) {
    const c = charOf(sb)
    const id = sb.id as number
    setLoadingId(id)
    try {
      await editorApi.generateVoice(id, { character_id: c?.id as number | undefined, voice: c?.voice as string | undefined })
      toast.success('已提交配音任务')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setLoadingId(null)
    }
  }

  if (!storyboards.length) {
    return (
      <section className="ed-section">
        <div className="g-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先生成剧本，再为台词配音" />
        </div>
      </section>
    )
  }

  return (
    <section className="ed-section">
      <div className="ed-step-header">
        <div className="ed-step-badge">
          <span className="ed-step-sub">{storyboards.length} 幕台词</span>
        </div>
      </div>

      <div className="dub-list">
        {storyboards.map((sb, i) => {
          const c = charOf(sb)
          const audioUrl = audioOfSb(assets, sb.id as number)
          const hasDialogue = !!(sb.dialogue as string)?.trim()
          return (
            <div key={String(sb.id ?? i)} className="dub-row">
              <div
                className="dub-avatar"
                style={{ background: gradVarOf((c?.id as number) ?? (sb.id as number) ?? i) }}
                aria-hidden="true"
              >
                {firstCharOf((sb.character_name as string) || (sb.dialogue as string))}
              </div>

              <div className="dub-meta">
                <b>{(sb.character_name as string) || `第 ${i + 1} 幕`}</b>
                <span className={hasDialogue ? undefined : 'none'}>
                  {(sb.dialogue as string) || '（无台词）'}
                </span>
                <em className="dub-duration">{fmtDuration(sb.duration as number)}</em>
              </div>

              <div className="dub-tags">
                {!!sb.emotion && <Tag>{sb.emotion as string}</Tag>}
                <Tag>{voiceLabel(c?.voice)}</Tag>
              </div>

              {audioUrl ? (
                <div className="dub-audio">
                  <audio src={audioUrl} controls preload="none" />
                </div>
              ) : (
                <Button
                  size="small"
                  type="primary"
                  ghost
                  icon={<AudioMutedOutlined />}
                  disabled={!hasDialogue}
                  loading={loadingId === (sb.id as number)}
                  onClick={() => void genVoice(sb)}
                >
                  生成配音
                </Button>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}