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

export interface AppIconProfile {
  key: string
  glyph: Component
  from: string
  to: string
  accent: string
}

const FALLBACK_PROFILE: AppIconProfile = {
  key: 'generic-app',
  glyph: AppWindow,
  from: '#64748b',
  to: '#334155',
  accent: '#dbeafe',
}

const APP_PROFILES: Record<string, AppIconProfile> = {
  desktop: { key: 'finder', glyph: FolderOpen, from: '#36a9ff', to: '#0877e6', accent: '#e5f5ff' },
  recycle: { key: 'trash', glyph: Trash2, from: '#f5f7fa', to: '#aab4c2', accent: '#ffffff' },
  agent: { key: 'ai-assistant', glyph: Bot, from: '#7758f6', to: '#3730a3', accent: '#e9e5ff' },
  knowledge: { key: 'knowledge', glyph: BookOpen, from: '#20b996', to: '#087d70', accent: '#ddfff6' },
  memory: { key: 'memory', glyph: Brain, from: '#ec4899', to: '#9d174d', accent: '#ffe4f2' },
  'model-router': { key: 'model-router', glyph: Route, from: '#27364b', to: '#111827', accent: '#67e8f9' },
  'douyin-delivery': { key: 'content-studio', glyph: Video, from: '#ff416c', to: '#161a2c', accent: '#67e8f9' },
  'image-viewer': { key: 'image-viewer', glyph: Image, from: '#0ea5e9', to: '#2563eb', accent: '#e0f2fe' },
  'image-vision': { key: 'image-vision', glyph: ScanSearch, from: '#14b8a6', to: '#0f766e', accent: '#ccfbf1' },
  'image-gen': { key: 'image-generation', glyph: WandSparkles, from: '#f472b6', to: '#7c3aed', accent: '#fce7f3' },
  'pdf-viewer': { key: 'pdf-viewer', glyph: FileText, from: '#ef4444', to: '#b91c1c', accent: '#fee2e2' },
  'doc-viewer': { key: 'document-viewer', glyph: FileText, from: '#3b82f6', to: '#1d4ed8', accent: '#dbeafe' },
  'text-editor': { key: 'text-editor', glyph: FilePenLine, from: '#738195', to: '#39475b', accent: '#f8fafc' },
  'excel-engine': { key: 'spreadsheet', glyph: Table2, from: '#22a86b', to: '#087443', accent: '#dcfce7' },
  'ppt-viewer': { key: 'presentation', glyph: Presentation, from: '#f97316', to: '#c2410c', accent: '#ffedd5' },
  im: { key: 'messages', glyph: MessageCircle, from: '#30c66b', to: '#138a46', accent: '#dcfce7' },
  'docs-open': { key: 'docs-open', glyph: Braces, from: '#0891b2', to: '#155e75', accent: '#cffafe' },
  'wechat-writer': { key: 'wechat-writer', glyph: PenLine, from: '#22c55e', to: '#047857', accent: '#dcfce7' },
  'media-intelligence': { key: 'media-intelligence', glyph: Headphones, from: '#8b5cf6', to: '#4338ca', accent: '#ede9fe' },
  'media-asr': { key: 'media-asr', glyph: Headphones, from: '#6366f1', to: '#3730a3', accent: '#e0e7ff' },
  'terminal-tools': { key: 'terminal', glyph: SquareTerminal, from: '#334155', to: '#0f172a', accent: '#a7f3d0' },
  'browser-tools': { key: 'browser', glyph: Compass, from: '#38bdf8', to: '#0369a1', accent: '#e0f2fe' },
  'web-tools': { key: 'web-search', glyph: Search, from: '#06b6d4', to: '#0e7490', accent: '#cffafe' },
  'github-search': { key: 'code-search', glyph: Search, from: '#475569', to: '#111827', accent: '#e2e8f0' },
  scheduler: { key: 'scheduler', glyph: Clock3, from: '#f59e0b', to: '#b45309', accent: '#fef3c7' },
  codemap: { key: 'codemap', glyph: Network, from: '#6366f1', to: '#312e81', accent: '#e0e7ff' },
  'desktop-tools': { key: 'desktop-tools', glyph: Wrench, from: '#64748b', to: '#334155', accent: '#f1f5f9' },
  'email-parser': { key: 'email', glyph: Mail, from: '#0ea5e9', to: '#1d4ed8', accent: '#dbeafe' },
  'office-gen': { key: 'office-generator', glyph: Sparkles, from: '#0ea5e9', to: '#4338ca', accent: '#e0f2fe' },
  'structured-parser': { key: 'structured-data', glyph: Database, from: '#14b8a6', to: '#0f766e', accent: '#ccfbf1' },
  'desktop-settings': { key: 'settings', glyph: Settings, from: '#94a3b8', to: '#475569', accent: '#f8fafc' },
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
  if (appKey && APP_PROFILES[appKey]) return APP_PROFILES[appKey]
  if (icon && ICON_PROFILES[icon]) return ICON_PROFILES[icon]
  return FALLBACK_PROFILE
}
