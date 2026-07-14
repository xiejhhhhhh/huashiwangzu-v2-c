#!/usr/bin/env node
// Checks module runtime SDK copies against the shared template.
//
// Exact template copies are expected for modules that do not need custom
// runtime APIs. Known variants are allowed, but every other drift is reported
// so platform runtime changes do not silently fork across modules.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..', '..')
const MODULES_DIR = path.join(ROOT, 'modules')
const TEMPLATE_PATH = path.join(MODULES_DIR, '_template', 'runtime', 'index.ts')

const KNOWN_VARIANTS = new Set([
  'agent',
  'doc-viewer',
  'docs-open',
  'douyin-delivery', // exports apiPut/apiDelete for CRUD panels
  'image-viewer',
  'knowledge',
  'media-intelligence', // minimal sandbox-compatible modules.call runtime
  'memory',
  'model-router',   // minimal runtime, only exposes apiGet/apiPost/apiPut/apiDelete + platform.modules.call
  'office-gen',     // has content namespace + apiPut (content pipeline helpers beyond template)
  'pdf-viewer',
  'ppt-viewer',
  'scheduler',
  'terminal-tools',
  'text-editor',
  'web-tools',
  'wechat-writer',  // exports apiDelete for draft/prompt management
])

const MINIMAL_VARIANTS = new Set([
  'media-intelligence', // deliberately exposes only RuntimeConfig/initRuntime/platform.modules.call
  'model-router',       // deliberately exposes only RuntimeConfig/initRuntime/platform.modules.call (+ CRUD apiGet/apiPost/apiPut/apiDelete)
])

const REQUIRED_FULL_EXPORTS = [
  'RuntimeConfig',
  'initRuntime',
  'initFrameworkRuntime',
  'getApiUrl',
  'getMode',
  'hasPermission',
  'getModuleSetting',
  'getRuntimeConfig',
  'authHeaders',
  'apiGet',
  'apiPost',
  'auth',
  'files',
  'office',
  'gateway',
  'tasks',
  'notifications',
  'logs',
  'settings',
  'modules',
  'platform',
]

const REQUIRED_RUNTIME_CONFIG_FIELDS = [
  'mode',
  'api_base_url',
  'permissions',
  'module_settings',
]

function normalizeRuntimeSource(source) {
  return source.replace(/\r\n/g, '\n').trimEnd()
}

function exportedNames(source) {
  return new Set(
    [...source.matchAll(/export\s+(?:const|function|async function|interface|type)\s+([A-Za-z0-9_]+)/g)]
      .map((match) => match[1]),
  )
}

function missingRuntimeConfigFields(source) {
  const interfaceMatch = source.match(/export\s+interface\s+RuntimeConfig\s*{([\s\S]*?)\n}/)
  const body = interfaceMatch ? interfaceMatch[1] : ''
  return REQUIRED_RUNTIME_CONFIG_FIELDS.filter((field) => !new RegExp(`\\b${field}\\b`).test(body))
}

function validateRuntimeContract(moduleName, source) {
  const exports = exportedNames(source)
  const missingFields = missingRuntimeConfigFields(source)
  const issues = []

  if (MINIMAL_VARIANTS.has(moduleName)) {
    for (const name of ['RuntimeConfig', 'initRuntime', 'platform']) {
      if (!exports.has(name)) issues.push(`missing export ${name}`)
    }
    if (!/modules\s*:\s*{[\s\S]*call\s*</.test(source)) {
      issues.push('missing platform.modules.call')
    }
  } else {
    const missingExports = REQUIRED_FULL_EXPORTS.filter((name) => !exports.has(name))
    if (missingExports.length > 0) {
      issues.push(`missing exports ${missingExports.join(', ')}`)
    }
    if (!/function\s+platformApiBridge\s*\(\)/.test(source)) {
      issues.push('missing platformApiBridge')
    }
    if (!/bridge\?\.get/.test(source) || !/bridge\?\.post/.test(source)) {
      issues.push('apiGet/apiPost do not delegate to window.platform.api in framework mode')
    }
    if (/export\s+async\s+function\s+apiPut/.test(source) && !/bridge\?\.put/.test(source)) {
      issues.push('apiPut does not delegate to window.platform.api.put')
    }
    if (/export\s+async\s+function\s+apiDelete/.test(source) && !/bridge\?\.delete/.test(source)) {
      issues.push('apiDelete does not delegate to window.platform.api.delete')
    }
    if (!/\bparent_folder_id\b/.test(source) || !/normalizeFilePage/.test(source)) {
      issues.push('file list/search responses are not normalized to parent_folder_id')
    }
    if (/__HSWZ_WINDOW_MANAGER__/.test(source)) {
      issues.push('runtime must not call legacy __HSWZ_WINDOW_MANAGER__ fallback')
    }
  }

  if (missingFields.length > 0) {
    issues.push(`RuntimeConfig missing fields ${missingFields.join(', ')}`)
  }
  return issues
}

if (!fs.existsSync(TEMPLATE_PATH)) {
  console.error(`[runtime-drift] Missing template runtime: ${TEMPLATE_PATH}`)
  process.exit(1)
}

const template = normalizeRuntimeSource(fs.readFileSync(TEMPLATE_PATH, 'utf-8'))
const exact = []
const variants = []
const unexpected = []
const contractIssues = []

for (const moduleName of fs.readdirSync(MODULES_DIR).sort()) {
  if (moduleName.startsWith('.') || moduleName === '_template') continue
  const runtimePath = path.join(MODULES_DIR, moduleName, 'runtime', 'index.ts')
  if (!fs.existsSync(runtimePath)) continue

  const source = normalizeRuntimeSource(fs.readFileSync(runtimePath, 'utf-8'))
  if (source === template) {
    exact.push(moduleName)
  } else if (KNOWN_VARIANTS.has(moduleName)) {
    variants.push(moduleName)
  } else {
    unexpected.push(moduleName)
  }
  const issues = validateRuntimeContract(moduleName, source)
  if (issues.length > 0) {
    contractIssues.push(`${moduleName}: ${issues.join('; ')}`)
  }
}

const missingKnownVariants = [...KNOWN_VARIANTS].filter((moduleName) => {
  return !fs.existsSync(path.join(MODULES_DIR, moduleName, 'runtime', 'index.ts'))
})

console.log(`[runtime-drift] exact template copies: ${exact.length}`)
console.log(`[runtime-drift] known runtime variants: ${variants.length}`)

if (missingKnownVariants.length > 0) {
  console.error(`[runtime-drift] Known variants missing runtime/index.ts: ${missingKnownVariants.join(', ')}`)
  process.exit(1)
}

if (unexpected.length > 0) {
  console.error(`[runtime-drift] Unexpected runtime drift: ${unexpected.join(', ')}`)
  console.error('[runtime-drift] Either sync these modules from modules/_template/runtime/index.ts or add intentional variants to KNOWN_VARIANTS.')
  process.exit(1)
}

if (contractIssues.length > 0) {
  console.error('[runtime-drift] Runtime contract issues:')
  for (const issue of contractIssues) {
    console.error(`  - ${issue}`)
  }
  process.exit(1)
}

console.log('[runtime-drift] OK')
