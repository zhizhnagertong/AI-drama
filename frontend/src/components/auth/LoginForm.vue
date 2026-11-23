<script setup>
/** 登录表单：字段级错误回显 + 记住我 + 锁定/凭证错误提示。 */
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { loginRules } from '../../composables/useFormRules'

const props = defineProps({ prefill: { type: String, default: '' } })
const emit = defineEmits(['switch', 'forget'])

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref()
const loading = ref(false)
const fieldErrors = reactive({ username: '', password: '' })
const form = reactive({ username: '', password: '', remember: false })

watch(
  () => props.prefill,
  (v) => {
    if (v) form.username = v
  },
  { immediate: true }
)

const rules = loginRules()

async function submit() {
  // 防重复提交：表单级 @keyup.enter 不受按钮 disabled 约束，连续回车会并发多次登录
  if (loading.value) return
  fieldErrors.username = ''
  fieldErrors.password = ''
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password, form.remember)
    ElMessage.success('欢迎回来！')
    router.push(route.query.redirect || '/')
  } catch (err) {
    const biz = err?.bizCode
    const msg = err?.friendlyMessage || '登录失败，请重试'
    if (biz === 'ACCOUNT_LOCKED') {
      ElMessage({ type: 'warning', message: msg, duration: 5000 })
    } else if (biz === 'VALIDATION_ERROR' && err?.fieldErrors) {
      fieldErrors.username = err.fieldErrors.username || ''
      fieldErrors.password = err.fieldErrors.password || ''
      if (!fieldErrors.username && !fieldErrors.password) ElMessage.error(msg)
    } else {
      fieldErrors.password = msg
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
        placeholder="请输入用户名"
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
        placeholder="请输入密码"
        autocomplete="current-password"
        :prefix-icon="'Lock'"
      />
      <p v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</p>
    </el-form-item>

    <div class="row">
      <el-checkbox v-model="form.remember">记住我</el-checkbox>
      <button type="button" class="link-btn" @click="emit('forget')">忘记密码？</button>
    </div>

    <el-button
      class="submit"
      type="primary"
      size="large"
      round
      :loading="loading"
      :disabled="loading"
      @click="submit"
    >
      登录
    </el-button>

    <p class="switch-tip">
      还没有账号？
      <button type="button" class="link-btn" @click="emit('switch', 'register')">立即注册</button>
    </p>
  </el-form>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: calc(-1 * var(--space-2)) 0 var(--space-4);
}

.link-btn {
  border: none;
  background: none;
  padding: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary);
  cursor: pointer;
  transition: color var(--dur-base) var(--ease-smooth);
}

.link-btn:hover {
  color: var(--primary-hover);
  text-decoration: underline;
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

.field-error {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--danger);
}

:deep(.is-field-error .el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--danger) inset;
}
</style>
