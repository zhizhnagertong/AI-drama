<script setup>
/** 忘记密码三步弹窗：校验用户 → 输入验证码（60s 重发倒计时）→ 重置密码。 */
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import api, { unwrap } from '../../api'
import { PASSWORD_PATTERN, resetRules, passwordStrength } from '../../composables/useFormRules'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'done'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const step = ref(1)
const loading = ref(false)
const error = ref('')

const form = reactive({ username: '', code: '', new_password: '', confirm_password: '' })
const contact = ref({ channel: null, masked_contact: null })
const codeHint = ref('')

const pwdFormRef = ref()
const rules = resetRules(() => form.new_password)
const strength = computed(() => passwordStrength(form.new_password))
const strengthWidth = computed(() => `${Math.min(strength.value.score, 4) * 25}%`)

/* -------- 验证码倒计时 -------- */
const countdown = ref(0)
let timer = null

function startCountdown(seconds) {
  countdown.value = seconds
  clearInterval(timer)
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(timer)
  }, 1000)
}

onBeforeUnmount(() => clearInterval(timer))

watch(visible, (v) => {
  if (!v) {
    // 关闭时完全重置
    step.value = 1
    error.value = ''
    codeHint.value = ''
    countdown.value = 0
    clearInterval(timer)
    Object.assign(form, { username: '', code: '', new_password: '', confirm_password: '' })
  }
})

/* -------- Step 1：校验用户 -------- */
async function nextFromUser() {
  error.value = ''
  const username = form.username.trim()
  if (!username) {
    error.value = '请输入用户名'
    return
  }
  loading.value = true
  try {
    const data = unwrap(await api.post('/auth/verify-user', { username }))
    if (!data?.exists) {
      error.value = '用户不存在，请检查用户名'
      return
    }
    contact.value = { channel: data.channel, masked_contact: data.masked_contact }
    await sendCode(true)
    step.value = 2
  } catch (err) {
    error.value = err?.friendlyMessage || '校验失败，请重试'
  } finally {
    loading.value = false
  }
}

/* -------- Step 2：验证码 -------- */
async function sendCode(silent = false) {
  error.value = ''
  try {
    const data = unwrap(await api.post('/auth/password/send-code', { username: form.username.trim() }))
    codeHint.value = data?.code_hint || ''
    startCountdown(data?.resend_interval || 60)
    if (!silent) ElMessage.success('验证码已发送')
  } catch (err) {
    const msg = err?.friendlyMessage || '发送失败'
    if (err?.bizCode === 'RESEND_TOO_FAST') ElMessage.warning(msg)
    else error.value = msg
  }
}

async function nextFromCode() {
  error.value = ''
  const code = form.code.trim()
  if (!/^\d{6}$/.test(code)) {
    error.value = '请输入 6 位数字验证码'
    return
  }
  loading.value = true
  try {
    await api.post('/auth/password/verify-code', { username: form.username.trim(), code })
    step.value = 3
  } catch (err) {
    error.value = err?.friendlyMessage || '验证码错误'
  } finally {
    loading.value = false
  }
}

/* -------- Step 3：重置密码 -------- */
async function doReset() {
  error.value = ''
  if (!PASSWORD_PATTERN.test(form.new_password)) {
    error.value = '密码须为 8-20 位，包含大写、小写字母和数字，不含空格'
    return
  }
  try {
    await pwdFormRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await api.post('/auth/password/reset', {
      username: form.username.trim(),
      code: form.code.trim(),
      new_password: form.new_password,
      confirm_password: form.confirm_password
    })
    ElMessage.success('密码重置成功，请使用新密码登录')
    visible.value = false
    emit('done', form.username.trim())
  } catch (err) {
    const msg = err?.friendlyMessage || '重置失败'
    if (err?.bizCode === 'CODE_EXPIRED') {
      error.value = msg
      step.value = 2
    } else {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="找回密码"
    width="440px"
    align-center
    :close-on-click-modal="false"
    class="forget-dialog"
  >
    <!-- 步骤指示器 -->
    <div class="steps">
      <div v-for="i in 3" :key="i" class="step" :class="{ active: step >= i, current: step === i }">
        <span class="step-dot">{{ i }}</span>
        <span class="step-name">{{ ['验证身份', '输入验证码', '重置密码'][i - 1] }}</span>
        <span v-if="i < 3" class="step-line"></span>
      </div>
    </div>

    <!-- Step 1 -->
    <div v-if="step === 1" class="pane">
      <p class="hint">输入你的用户名，我们将向你绑定的邮箱发送验证码。</p>
      <el-input
        v-model="form.username"
        size="large"
        placeholder="请输入用户名"
        :prefix-icon="'User'"
        @keyup.enter="nextFromUser"
      />
      <p v-if="error" class="error">{{ error }}</p>
      <el-button class="submit" type="primary" round :loading="loading" @click="nextFromUser">
        下一步
      </el-button>
    </div>

    <!-- Step 2 -->
    <div v-else-if="step === 2" class="pane">
      <p class="hint">
        验证码已发送至
        <strong>{{ contact.masked_contact || '你的邮箱（开发模式直接回显）' }}</strong>
      </p>
      <p v-if="codeHint" class="dev-hint">开发模式验证码：<code>{{ codeHint }}</code></p>
      <el-input
        v-model="form.code"
        size="large"
        maxlength="6"
        placeholder="6 位数字验证码"
        :prefix-icon="'Key'"
        @keyup.enter="nextFromCode"
      />
      <p v-if="error" class="error">{{ error }}</p>
      <div class="code-row">
        <el-button link type="primary" :disabled="countdown > 0 || loading" @click="sendCode()">
          {{ countdown > 0 ? `${countdown}s 后重发` : '重新发送' }}
        </el-button>
        <el-button link @click="step = 1">返回上一步</el-button>
      </div>
      <el-button class="submit" type="primary" round :loading="loading" @click="nextFromCode">
        下一步
      </el-button>
    </div>

    <!-- Step 3 -->
    <div v-else class="pane">
      <el-form ref="pwdFormRef" :model="form" :rules="rules" label-position="top" hide-required-asterisk>
        <el-form-item prop="new_password" label="新密码">
          <el-input
            v-model="form.new_password"
            type="password"
            size="large"
            show-password
            placeholder="8-20 位，含大小写字母和数字"
            :prefix-icon="'Lock'"
          />
          <div v-if="form.new_password" class="strength">
            <div class="strength-track">
              <div class="strength-bar" :style="{ width: strengthWidth, background: strength.color }"></div>
            </div>
            <span class="strength-label" :style="{ color: strength.color }">{{ strength.label }}</span>
          </div>
        </el-form-item>
        <el-form-item prop="confirm_password" label="确认新密码">
          <el-input
            v-model="form.confirm_password"
            type="password"
            size="large"
            show-password
            placeholder="请再次输入新密码"
            :prefix-icon="'Lock'"
            @keyup.enter="doReset"
          />
        </el-form-item>
      </el-form>
      <p v-if="error" class="error">{{ error }}</p>
      <el-button class="submit" type="primary" round :loading="loading" @click="doReset">
        重置密码
      </el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}

.step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.step.active {
  color: var(--text-secondary);
}

.step.current {
  color: var(--primary);
}

.step-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  background: var(--surface-hover);
  border: 1px solid var(--border);
  transition: all var(--dur-base) var(--ease-smooth);
}

.step.current .step-dot {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.step.active:not(.current) .step-dot {
  background: var(--primary-soft);
  border-color: var(--primary);
  color: var(--primary);
}

.step-line {
  width: 28px;
  height: 1px;
  margin-left: var(--space-2);
  background: var(--border-strong);
}

.pane {
  animation: fadeUp 0.3s var(--ease-out);
}

.hint {
  margin: 0 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

.hint strong {
  color: var(--text-primary);
}

.dev-hint {
  margin: calc(-1 * var(--space-2)) 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--warning);
}

.dev-hint code {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 2px;
}

.error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  color: var(--danger);
}

.code-row {
  display: flex;
  justify-content: space-between;
  margin-top: var(--space-2);
}

.submit {
  width: 100%;
  margin-top: var(--space-5);
}

.strength {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  margin-top: var(--space-2);
}

.strength-track {
  flex: 1;
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--surface-hover);
  overflow: hidden;
}

.strength-bar {
  height: 100%;
  border-radius: var(--radius-pill);
  transition: width var(--dur-slow) var(--ease-smooth),
    background var(--dur-slow) var(--ease-smooth);
}

.strength-label {
  flex: none;
  font-size: var(--text-xs);
  font-weight: 600;
}
</style>

<style>
/* 弹窗外观对齐设计规范 17.1：遮罩 60% 黑 + 毛玻璃 + 24px 圆角 */
.forget-dialog {
  --el-dialog-bg-color: var(--surface);
  --el-dialog-title-font-size: var(--text-md);
  border-radius: var(--radius-xl) !important;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-xl);
  max-width: calc(100vw - 48px);
}

.forget-dialog .el-dialog__title {
  font-weight: 700;
  color: var(--text-primary);
}

.el-overlay:has(.forget-dialog) {
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
}
</style>
