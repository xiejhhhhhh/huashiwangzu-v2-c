import { friendlyErrorMessage } from '@/shared/composables/use-friendly-error'
import { ElMessage } from 'element-plus'

export interface ApiErrorInfo {
  success: false
  data: null
  error: string
  http_status?: number
  httpStatus?: number
  code?: string
  backendMessage?: string
  userMessage: string
  raw?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringField(record: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = record?.[key]
  return typeof value === 'string' && value.trim() ? value : undefined
}

function numberField(record: Record<string, unknown> | undefined, key: string): number | undefined {
  const value = record?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function dataMessage(data: unknown): string | undefined {
  if (!isRecord(data)) return undefined
  const direct = stringField(data, 'error') || stringField(data, 'message') || stringField(data, 'detail')
  if (direct) return direct
  const errors = summarizeErrors(data.errors)
  if (errors) return errors
  const detail = summarizeDetail(data.detail)
  if (detail) return detail
  const nestedError = data.error
  if (isRecord(nestedError)) {
    return stringField(nestedError, 'message') || stringField(nestedError, 'detail') || stringField(nestedError, 'code')
  }
  return undefined
}

function summarizeErrors(errors: unknown): string | undefined {
  if (Array.isArray(errors)) {
    const parts = errors
      .map((item) => {
        if (!isRecord(item)) return ''
        const field = stringField(item, 'field')
        const message = stringField(item, 'message')
        return message ? (field ? `${field}: ${message}` : message) : ''
      })
      .filter(Boolean)
    return parts.length ? parts.slice(0, 3).join('；') : undefined
  }
  if (isRecord(errors)) {
    const parts = Object.entries(errors)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].trim().length > 0)
      .map(([field, message]) => `${field}: ${message}`)
    return parts.length ? parts.slice(0, 3).join('；') : undefined
  }
  return undefined
}

function summarizeDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (!Array.isArray(detail)) return undefined
  const parts = detail
    .map((item) => {
      if (!isRecord(item)) return ''
      const message = stringField(item, 'msg') || stringField(item, 'message')
      const location = Array.isArray(item.loc) ? item.loc.map(String).join('.') : ''
      return message ? (location ? `${location}: ${message}` : message) : ''
    })
    .filter(Boolean)
  return parts.length ? parts.slice(0, 3).join('；') : undefined
}

function dataCode(data: unknown): string | undefined {
  if (!isRecord(data)) return undefined
  return stringField(data, 'code') || stringField(data, 'error_code')
}

function existingApiError(error: unknown): ApiErrorInfo | null {
  if (!isRecord(error)) return null
  const userMessage = stringField(error, 'userMessage') || stringField(error, 'error')
  if (!userMessage) return null
  const httpStatus = numberField(error, 'httpStatus') ?? numberField(error, 'http_status')
  return {
    success: false,
    data: null,
    error: userMessage,
    userMessage,
    http_status: httpStatus,
    httpStatus,
    code: stringField(error, 'code'),
    backendMessage: stringField(error, 'backendMessage'),
    raw: error.raw ?? error,
  }
}

function buildApiErrorInfo(params: {
  userMessage: string
  httpStatus?: number
  code?: string
  backendMessage?: string
  raw?: unknown
}): ApiErrorInfo {
  return {
    success: false,
    data: null,
    error: params.userMessage,
    userMessage: params.userMessage,
    http_status: params.httpStatus,
    httpStatus: params.httpStatus,
    code: params.code,
    backendMessage: params.backendMessage,
    raw: params.raw,
  }
}

export function toApiErrorInfo(error: unknown, fallbackMessage = '请求失败，请稍后重试'): ApiErrorInfo {
  const existing = existingApiError(error)
  if (existing) return existing

  const errorRecord = isRecord(error) ? error : undefined
  const responseRecord = isRecord(errorRecord?.response) ? errorRecord.response : undefined
  const responseData = responseRecord?.data
  const configRecord = isRecord(errorRecord?.config) ? errorRecord.config : undefined
  const statusCode = numberField(responseRecord, 'status')
  const isLoginRequest = stringField(configRecord, 'url')?.endsWith('/login') === true
  const backendMessage = dataMessage(responseData)
  const code = dataCode(responseData)

  if (!responseRecord) {
    return buildApiErrorInfo({
      userMessage: '网络连接异常，请检查公司网络',
      httpStatus: 0,
      backendMessage,
      code,
      raw: error,
    })
  }

  let errorMessage = ''
  if (statusCode === 401 && isLoginRequest) {
    errorMessage = friendlyErrorMessage(backendMessage || '用户名或密码错误')
  } else if (statusCode === 401) {
    errorMessage = '登录已过期，请重新登录'
  } else if (statusCode === 403) {
    errorMessage = '你没有权限操作这个内容'
  } else if (statusCode === 404) {
    errorMessage = '内容不存在或已被删除'
  } else if (statusCode === 502) {
    errorMessage = '后端服务暂时不可用，请检查 scripts/start_backend.sh 是否已运行'
  } else if (statusCode && statusCode >= 500) {
    errorMessage = '系统开小差了，请联系管理员'
  } else {
    errorMessage = friendlyErrorMessage(backendMessage || fallbackMessage)
  }
  return buildApiErrorInfo({
    userMessage: errorMessage,
    httpStatus: statusCode,
    code,
    backendMessage,
    raw: error,
  })
}

export function displayApiError(error: unknown, fallbackMessage = '请求失败，请稍后重试'): ApiErrorInfo {
  const info = toApiErrorInfo(error, fallbackMessage)
  ElMessage.error(info.userMessage)
  return info
}

export function getErrorInfo(error: unknown): ApiErrorInfo {
  return toApiErrorInfo(error)
}
