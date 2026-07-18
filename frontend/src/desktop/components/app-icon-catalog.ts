import type { Component } from 'vue'
import {
  AppWindow,
  Bot,
  BookOpen,
  Brain,
  Braces,
  Clock3,
  Compass,
  Database,
  FilePenLine,
  FileText,
  FolderOpen,
  Headphones,
  Image,
  Layers3,
  Mail,
  MessageCircle,
  Network,
  PenLine,
  Presentation,
  Route,
  ScanSearch,
  Search,
  Settings,
  Sparkles,
  SquareTerminal,
  Table2,
  Trash2,
  Video,
  WandSparkles,
  Wrench,
} from 'lucide-vue-next'

export type AppIconMaterial = 'glass' | 'metal' | 'paper' | 'plastic'

export interface AppIconProfile {
  key: string
  glyph: Component
  from: string
  to: string
  accent: string
  material?: AppIconMaterial
  depth?: string
}

const FALLBACK_PROFILE: AppIconProfile = {
  key: 'generic-app',
  glyph: AppWindow,
  from: '#64748b',
  to: '#334155',
  accent: '#dbeafe',
  material: 'plastic',
  depth: 'rgba(15,23,42,.28)',
}

const APP_PROFILES: Record<string, AppIconProfile> = {
  desktop: { key: 'finder', glyph: FolderOpen, from: '#5ec0ff', to: '#0a74e8', accent: '#eff8ff', material: 'glass', depth: 'rgba(8,70,150,.28)' },
  files: { key: 'files', glyph: FolderOpen, from: '#5ec0ff', to: '#0a74e8', accent: '#eff8ff', material: 'glass', depth: 'rgba(8,70,150,.28)' },
  recycle: { key: 'trash', glyph: Trash2, from: '#f8fafc', to: '#94a3b8', accent: '#ffffff', material: 'metal', depth: 'rgba(51,65,85,.25)' },
  agent: { key: 'ai-assistant', glyph: Bot, from: '#8b6cff', to: '#3b2bb5', accent: '#f0ecff', material: 'glass', depth: 'rgba(55,48,163,.32)' },
  ai: { key: 'ai-product', glyph: Bot, from: '#8b6cff', to: '#3b2bb5', accent: '#f0ecff', material: 'glass', depth: 'rgba(55,48,163,.32)' },
  knowledge: { key: 'knowledge', glyph: BookOpen, from: '#34d3aa', to: '#0b8f7d', accent: '#e7fff8', material: 'paper', depth: 'rgba(6,95,70,.28)' },
  memory: { key: 'memory', glyph: Brain, from: '#f472b6', to: '#9d174d', accent: '#ffe4f2', material: 'glass' },
  office: { key: 'office', glyph: FileText, from: '#60a5fa', to: '#1d4ed8', accent: '#eff6ff', material: 'paper', depth: 'rgba(30,64,175,.28)' },
  text: { key: 'text', glyph: FilePenLine, from: '#94a3b8', to: '#334155', accent: '#f8fafc', material: 'paper' },
  media: { key: 'media', glyph: Video, from: '#fb7185', to: '#7c3aed', accent: '#ffe4e6', material: 'glass' },
  messages: { key: 'messages-product', glyph: MessageCircle, from: '#4ade80', to: '#15803d', accent: '#ecfdf5', material: 'glass' },
  settings: { key: 'settings-product', glyph: Settings, from: '#cbd5e1', to: '#475569', accent: '#f8fafc', material: 'metal' },
  'content-studio': { key: 'content-studio-product', glyph: Layers3, from: '#38bdf8', to: '#4338ca', accent: '#e0f2fe', material: 'glass' },
  'model-router': { key: 'model-router', glyph: Route, from: '#27364b', to: '#111827', accent: '#67e8f9', material: 'metal' },
  'douyin-delivery': { key: 'content-studio', glyph: Video, from: '#ff416c', to: '#161a2c', accent: '#67e8f9', material: 'glass' },
  'image-viewer': { key: 'image-viewer', glyph: Image, from: '#38bdf8', to: '#2563eb', accent: '#e0f2fe', material: 'glass' },
  'image-vision': { key: 'image-vision', glyph: ScanSearch, from: '#2dd4bf', to: '#0f766e', accent: '#ccfbf1', material: 'glass' },
  'image-gen': { key: 'image-generation', glyph: WandSparkles, from: '#f472b6', to: '#7c3aed', accent: '#fce7f3', material: 'glass' },
  'pdf-viewer': { key: 'pdf-viewer', glyph: FileText, from: '#f87171', to: '#b91c1c', accent: '#fee2e2', material: 'paper' },
  'doc-viewer': { key: 'document-viewer', glyph: FileText, from: '#60a5fa', to: '#1d4ed8', accent: '#dbeafe', material: 'paper' },
  'text-editor': { key: 'text-editor', glyph: FilePenLine, from: '#94a3b8', to: '#334155', accent: '#f8fafc', material: 'paper' },
  'excel-engine': { key: 'spreadsheet', glyph: Table2, from: '#34d399', to: '#047857', accent: '#dcfce7', material: 'paper' },
  'ppt-viewer': { key: 'presentation', glyph: Presentation, from: '#fb923c', to: '#c2410c', accent: '#ffedd5', material: 'paper' },
  im: { key: 'messages', glyph: MessageCircle, from: '#4ade80', to: '#15803d', accent: '#dcfce7', material: 'glass' },
  'docs-open': { key: 'docs-open', glyph: Braces, from: '#22d3ee', to: '#155e75', accent: '#cffafe', material: 'metal' },
  'wechat-writer': { key: 'wechat-writer', glyph: PenLine, from: '#4ade80', to: '#047857', accent: '#dcfce7', material: 'paper' },
  'media-intelligence': { key: 'media-intelligence', glyph: Headphones, from: '#a78bfa', to: '#4338ca', accent: '#ede9fe', material: 'glass' },
  'media-asr': { key: 'media-asr', glyph: Headphones, from: '#818cf8', to: '#3730a3', accent: '#e0e7ff', material: 'glass' },
  'terminal-tools': { key: 'terminal', glyph: SquareTerminal, from: '#475569', to: '#0f172a', accent: '#a7f3d0', material: 'metal' },
  'browser-tools': { key: 'browser', glyph: Compass, from: '#38bdf8', to: '#0369a1', accent: '#e0f2fe', material: 'glass' },
  'web-tools': { key: 'web-search', glyph: Search, from: '#22d3ee', to: '#0e7490', accent: '#cffafe', material: 'glass' },
  'github-search': { key: 'code-search', glyph: Search, from: '#64748b', to: '#111827', accent: '#e2e8f0', material: 'metal' },
  scheduler: { key: 'scheduler', glyph: Clock3, from: '#fbbf24', to: '#b45309', accent: '#fef3c7', material: 'plastic' },
  codemap: { key: 'codemap', glyph: Network, from: '#818cf8', to: '#312e81', accent: '#e0e7ff', material: 'glass' },
  'desktop-tools': { key: 'desktop-tools', glyph: Wrench, from: '#94a3b8', to: '#334155', accent: '#f1f5f9', material: 'metal' },
  'email-parser': { key: 'email', glyph: Mail, from: '#38bdf8', to: '#1d4ed8', accent: '#dbeafe', material: 'paper' },
  'office-gen': { key: 'office-generator', glyph: Sparkles, from: '#38bdf8', to: '#4338ca', accent: '#e0f2fe', material: 'glass' },
  'structured-parser': { key: 'structured-data', glyph: Database, from: '#2dd4bf', to: '#0f766e', accent: '#ccfbf1', material: 'metal' },
  'desktop-settings': { key: 'settings', glyph: Settings, from: '#cbd5e1', to: '#475569', accent: '#f8fafc', material: 'metal' },
}

const ICON_PROFILES: Record<string, AppIconProfile> = {
  Files: APP_PROFILES.desktop,
  FolderOpened: APP_PROFILES.desktop,
  Delete: APP_PROFILES.recycle,
  ChatDotRound: APP_PROFILES.agent,
  Collection: APP_PROFILES.knowledge,
  Connection: APP_PROFILES['model-router'],
  VideoPlay: APP_PROFILES['douyin-delivery'],
  Grid: APP_PROFILES['excel-engine'],
  Document: APP_PROFILES['doc-viewer'],
  DocumentCopy: { key: 'documents', glyph: Layers3, from: '#3b82f6', to: '#3730a3', accent: '#dbeafe' },
  View: APP_PROFILES['image-viewer'],
  EditPen: APP_PROFILES['wechat-writer'],
  Message: APP_PROFILES['email-parser'],
  Monitor: APP_PROFILES['terminal-tools'],
  Globe: APP_PROFILES['browser-tools'],
  Search: APP_PROFILES['web-tools'],
  Timer: APP_PROFILES.scheduler,
  DataBoard: APP_PROFILES.codemap,
  Setting: APP_PROFILES['desktop-settings'],
}

export function getAppIconProfile(appKey?: string, icon?: string): AppIconProfile {
  if (appKey && APP_PROFILES[appKey]) {
    const profile = APP_PROFILES[appKey]
    return { material: 'plastic', depth: 'rgba(15,23,42,.22)', ...profile }
  }
  if (icon && ICON_PROFILES[icon]) {
    const profile = ICON_PROFILES[icon]
    return { material: 'plastic', depth: 'rgba(15,23,42,.22)', ...profile }
  }
  return FALLBACK_PROFILE
}
