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
  'memory',
  'office-gen',     // has content namespace + apiPut (content pipeline helpers beyond template)
  'pdf-viewer',
  'ppt-viewer',
  'scheduler',
  'terminal-tools',
  'text-editor',
  'web-tools',
  'wechat-writer',  // exports apiDelete for draft/prompt management
])

function normalizeRuntimeSource(source) {
  return source.replace(/\r\n/g, '\n').trimEnd()
}

if (!fs.existsSync(TEMPLATE_PATH)) {
  console.error(`[runtime-drift] Missing template runtime: ${TEMPLATE_PATH}`)
  process.exit(1)
}

const template = normalizeRuntimeSource(fs.readFileSync(TEMPLATE_PATH, 'utf-8'))
const exact = []
const variants = []
const unexpected = []

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

console.log('[runtime-drift] OK')
