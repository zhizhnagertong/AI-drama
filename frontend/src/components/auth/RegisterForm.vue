<script setup>
/** 注册表单：用户名/密码/确认密码/邮箱/条款勾选 + 密码强度条。
 * 注册成功后不自动登录：提示并回填用户名切回登录（对齐注册业务流程图）。 */
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { unwrap } from '../../api'
import { registerRules, passwordStrength } from '../../composables/useFormRules'

const emit = defineEmits(['switch', 'registered'])

const formRef = ref()
const loading = ref(false)
const fieldErrors = reactive({ username: '', password: '', email: '', agree_terms: '' })

const form = reactive({
  username: '',
  password: '',
  confirm_password: '',
  email: '',
  agree_terms: false
})

const rules = registerRules(() => form.password)

const strength = computed(() => passwordStrength(form.password))
const strengthWidth = computed(() => `${Math.min(strength.value.score, 4) * 25}%`)

async function submit() {
  fieldErrors.username = ''
  fieldErrors.password = ''
  fieldErrors.email = ''
  fieldErrors.agree_terms = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const data = unwrap(
      await api.post('/auth/register', {
        username: form.username.trim(),
        password: form.password,
        confirm_password: form.confirm_password,
        email: form.email.trim() || undefined,
        agree_terms: true
      })
    )
    ElMessage.success('注册成功，请登录')
    emit('registered', data?.username || form.username)
  } catch (err) {
    const biz = err?.bizCode
    const msg = err?.friendlyMessage || '注册失败，请重试'
    if (biz === 'USERNAME_TAKEN') {
      fieldErrors.username = msg
    } else if (biz === 'EMAIL_TAKEN') {
      fieldErrors.email = msg
    } else if (biz === 'TERMS_NOT_AGREED') {
      fieldErrors.agree_terms = msg
    } else if (biz === 'VALIDATION_ERROR' && err?.fieldErrors) {
      fieldErrors.username = err.fieldErrors.username || ''
      fieldErrors.password = err.fieldErrors.password || ''
      fieldErrors.email = err.fieldErrors.email || ''
      if (!Object.values(fieldErrors).some(Boolean)) ElMessage.error(msg)
    } else {
      ElMessage.error(msg)
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    size="large"
    label-position="top"
    hide-required-asterisk
    @keyup.enter="submit"
  >
    <el-form-item prop="username" label="用户名">
      <el-input
        v-model="form.username"
        :class="{ 'is-field-error': fieldErrors.username }"
        placeholder="3-20 位字母或数字"
        autocomplete="username"
        spellcheck="false"
        :prefix-icon="'User'"
      />
      <p v-if="fieldErrors.username" class="field-error">{{ fieldErrors.username }}</p>
    </el-form-item>

    <el-form-item prop="password" label="密码">
      <el-input
        v-model="form.password"
        :class="{ 'is-field-error': fieldErrors.password }"
        type="password"
        show-password
        placeholder="8-20 位，含大小写字母和数字"
        autocomplete="new-password"
        :prefix-icon="'Lock'"
      />
      <div v-if="form.password" class="strength">
        <div class="strength-track">
          <div
            class="strength-bar"
            :style="{ width: strengthWidth, background: strength.color }"
          ></div>
        </div>
        <span class="strength-label" :style="{ color: strength.color }">{{ strength.label }}</span>
      </div>
      <p v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</p>
    </el-form-item>

    <el-form-item prop="confirm_password" label="确认密码">
      <el-input
        v-model="form.confirm_password"
        type="password"
        show-password
        placeholder="请再次输入密码"
        autocomplete="new-password"
        :prefix-icon="'Lock'"
      />
    </el-form-item>

    <el-form-item prop="email" label="邮箱（选填，用于找回密码）">
      <el-input
        v-model="form.email"
        :class="{ 'is-field-error': fieldErrors.email }"
        placeholder="name@example.com"
        autocomplete="email"
        spellcheck="false"
        :prefix-icon="'Message'"
      />
      <p v-if="fieldErrors.email" class="field-error">{{ fieldErrors.email }}</p>
    </el-form-item>

    <el-form-item prop="agree_terms" class="terms-item">
      <el-checkbox v-model="form.agree_terms">
        <span class="terms-text">我已阅读并同意</span>
      </el-checkbox>
      <span class="terms-link">《AI 生成内容使用规范》</span>
      <p v-if="fieldErrors.agree_terms" class="field-error">{{ fieldErrors.agree_terms }}</p>
    </el-form-item>

    <el-button
      class="submit"
      type="primary"
      size="large"
      round
      :loading="loading"
      :disabled="loading"
      @click="submit"
    >
      注册
    </el-button>

    <p class="switch-tip">
      已有账号？
      <button type="button" class="link-btn" @click="emit('switch', 'login')">返回登录</button>
    </p>
  </el-form>
</template>

<style scoped>
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

.terms-item {
  margin-bottom: var(--space-3);
}

.terms-item :deep(.el-form-item__content) {
  flex-wrap: wrap;
}

.terms-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.terms-link {
  font-size: var(--text-sm);
  color: var(--primary);
}

.submit {
  width: 100%;
  margin-top: var(--space-1);
}

.switch-tip {
  margin-top: var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.link-btn {
  border: none;
  background: none;
  padding: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
}

.link-btn:hover {
  color: var(--primary-hover);
  text-decoration: underline;
}

.field-error {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--danger);
}

:deep(.is-field-error .el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--danger) inset;
}
</style>
