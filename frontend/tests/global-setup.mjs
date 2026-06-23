import { chromium } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const AUTH_DIR = path.resolve(__dirname, '.auth')

const ACCOUNTS = [
  { role: 'admin', username: '何焜华', password: '123rgE123', storageFile: 'admin.json' },
  { role: 'viewer', username: 'viewer', password: 'admin123', storageFile: 'viewer.json' },
]

async function globalSetup() {
  fs.mkdirSync(AUTH_DIR, { recursive: true })

  const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'

  for (const acct of ACCOUNTS) {
    const browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ baseURL })
    const page = await context.newPage()

    await page.goto('/')
    await page.waitForSelector('.login-page', { timeout: 10000 })
    await page.fill('input[placeholder="Username"]', acct.username)
    await page.fill('input[placeholder="Password"]', acct.password)
    await page.click('button:has-text("Login")')
    await page.waitForSelector('.desktop-shell-container', { timeout: 15000 })

    await context.storageState({ path: path.join(AUTH_DIR, acct.storageFile) })
    await browser.close()
  }
}

export default globalSetup
